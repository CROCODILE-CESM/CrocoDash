from pathlib import Path
from typing import List, Dict
from abc import ABC, abstractmethod
from visualCaseGen.custom_widget_types.case_tools import (
    xmlchange,
    append_user_nl,
)
from CrocoDash.logging import setup_logger
import inspect
from typing import Optional, Any
import copy
import subprocess
import json

logger = setup_logger(__name__)


def is_serializable(v):
    """
    Check if a value can be serialized to JSON.

    Parameters
    ----------
    v : Any
        Value to check for serializability.

    Returns
    -------
    bool
        True if the value is a JSON-serializable type, False otherwise.
    """
    return isinstance(v, (str, int, float, bool, type(None), Path, list, dict))


class ForcingConfigRegistry:
    registered_types: List[type] = []

    @classmethod
    def register(cls, configurator_cls: type):
        """
        Register a configurator class with the registry.

        Parameters
        ----------
        configurator_cls : type
            The configurator class to register.

        Returns
        -------
        None
        """
        cls.registered_types.append(configurator_cls)

    def __getitem__(self, key: str):
        return self.active_configurators[key.lower()]

    def __init__(self, compset, inputs: dict, case=None):
        self.compset = compset
        self.active_configurators = {}
        if case is not None:
            self.case_info = {
                f"case_{k}": v
                for k, v in case.__dict__.items()
                if not k.startswith("_")
            }
            inputs = inputs | self.case_info
        inputs["compset"] = compset
        self.find_active_configurators(self.compset, inputs)

    @classmethod
    def deserialize(cls, obj_dict):
        """
        Deserialize a configurator from a dictionary representation.

        Parameters
        ----------
        obj_dict : dict
            Dictionary containing the configurator name and data.

        Returns
        -------
        BaseConfigurator
            An instance of the configurator class.

        Raises
        ------
        ValueError
            If the configurator name is not found in registered types.
        """
        name = obj_dict["name"]
        for thing in cls.registered_types:
            if name == thing.name:
                return thing.deserialize(obj_dict)
        raise ValueError(f"Unknown configurator name: {name}")

    @classmethod
    def find_valid_configurators(cls, compset):
        """
        Find all configurators valid for a given compset.

        Parameters
        ----------
        compset : str
            The component set string.

        Returns
        -------
        list of type
            List of configurator classes that are compatible with the compset.
        """
        valid_configs = []
        for configurator_cls in cls.registered_types:
            if configurator_cls.validate_compset_compatibility(compset):
                valid_configs.append(configurator_cls)
        return valid_configs

    @classmethod
    def find_required_configurators(cls, compset):
        """
        Find all configurators required for a given compset.

        Parameters
        ----------
        compset : str
            The component set string.

        Returns
        -------
        list of type
            List of configurator classes that are required for the compset.
        """
        required_configs = []
        for configurator_cls in cls.registered_types:
            if configurator_cls.is_required(compset):
                required_configs.append(configurator_cls)
        return required_configs

    @classmethod
    def get_ctor_signature(cls, configurator_cls):
        """
        Extract constructor signature information from a configurator class.

        Parameters
        ----------
        configurator_cls : type
            The configurator class to inspect.

        Returns
        -------
        tuple of (list, list)
            First list contains all argument names, second list contains only required argument names.
        """
        sig = inspect.signature(configurator_cls.__init__)
        args = [p.name for p in sig.parameters.values() if p.name != "self"]
        required_args = [
            p.name
            for p in sig.parameters.values()
            if p.name != "self" and p.default is inspect._empty
        ]

        return args, required_args

    @classmethod
    def get_user_args(cls, configurator_cls):
        """
        Get user-provided argument names for a configurator class.

        Parameters
        ----------
        configurator_cls : type
            The configurator class to inspect.

        Returns
        -------
        list of str
            Required argument names that don't start with 'case_'.
        """
        args, required_args = cls.get_ctor_signature(configurator_cls)
        user_args = [arg for arg in required_args if not arg.startswith("case_")]
        return user_args

    @classmethod
    def return_missing_inputs(cls, configurator_cls, inputs):
        """
        Identify missing required inputs for a configurator class.

        Parameters
        ----------
        configurator_cls : type
            The configurator class to check.
        inputs : dict
            Dictionary of provided inputs.

        Returns
        -------
        list of str
            Names of required inputs that are missing.
        """
        _, required_args = cls.get_ctor_signature(configurator_cls)
        missing = [arg for arg in required_args if arg not in inputs]
        return missing

    @classmethod
    def instantiate_configurator(cls, configurator_cls, inputs):
        """
        Instantiate a configurator class with provided inputs.

        Parameters
        ----------
        configurator_cls : type
            The configurator class to instantiate.
        inputs : dict
            Dictionary of inputs to pass to the constructor.

        Returns
        -------
        BaseConfigurator
            An instance of the configurator class.
        """
        args, _ = cls.get_ctor_signature(configurator_cls)
        ctor_kwargs = {arg: inputs[arg] for arg in args if arg in inputs}
        return configurator_cls(**ctor_kwargs)

    def find_active_configurators(self, compset, inputs: dict):
        """
        Find and instantiate active configurators for a given compset and inputs.

        Parameters
        ----------
        compset : str
            The component set string.
        inputs : dict
            Dictionary of input values for configurators.

        Returns
        -------
        None
            Updates self.active_configurators in place.

        Raises
        ------
        ValueError
            If a required configurator is missing required arguments.
        """
        required = self.find_required_configurators(compset)
        valid = self.find_valid_configurators(compset)

        for configurator_cls in self.registered_types:
            name = configurator_cls.name
            lname = name.lower()
            if configurator_cls in required:
                missing = self.return_missing_inputs(configurator_cls, inputs)
                if missing:
                    raise ValueError(
                        f"[ERROR] Required configurator {name} missing args: {missing}"
                    )
                logger.info(f"[REQUIRED] Activating {name}")
                self.active_configurators[lname] = self.instantiate_configurator(
                    configurator_cls, inputs
                )
                continue  # We do not want to to be added twice with the valid configs

            # --- OPTIONAL CONFIGURATORS ---
            if configurator_cls not in valid:
                logger.info(f"[SKIP] {name} incompatible with compset")
                continue

            missing = self.return_missing_inputs(configurator_cls, inputs)
            if missing:
                logger.info(f"[SKIP] {name} missing args: {missing}")
                continue

            logger.info(f"[OPTIONAL] Activating {name}")
            self.active_configurators[lname] = self.instantiate_configurator(
                configurator_cls, inputs
            )

    def run_configurators(self, config_path):
        """
        Execute all active configurators and save their configurations.

        Parameters
        ----------
        config_path : str or Path or None
            Path to save the configuration JSON file. If None, configurations are not saved.

        Returns
        -------
        dict
            Dictionary containing serialized configuration data for all active configurators.
        """
        if config_path is not None:
            with open(config_path) as f:
                general_config = json.load(f)
        else:
            general_config = {}

        # Run Configurators
        for configurator in self.active_configurators.values():
            logger.info(f"Configuring {configurator.name}")
            configurator.configure()
            general_config[configurator.name.lower()] = configurator.serialize()

        if config_path is not None:
            with open(config_path, "w") as f:
                json.dump(general_config, f, indent=4)
        return general_config

    def get_active_configurators(self):
        """
        Get names of all active configurators.

        Returns
        -------
        dict_keys
            Keys of active configurators.
        """
        return self.active_configurators.keys()

    def is_active(self, name: str) -> bool:
        """Return True if a configurator with this name is active."""
        return name.lower() in self.active_configurators


class Param(ABC):
    """
    Base class for a single parameter in forcing configurations.

    Parameters are either inputs (values provided by users) or outputs (configurations to apply).
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        """
        Initialize a parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        comment : str, optional
            Comment to include when applying configuration.
        """
        self.name = name
        self.comment = comment

    @abstractmethod
    def set_item(self, item: Any):
        """
        Bind a runtime value to this parameter.

        Parameters
        ----------
        item : Any
            The value to bind to the parameter.

        Returns
        -------
        None
        """
        pass
    
    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name!r})"


class InputParam(Param):
    """
    Base class for input parameters in forcing configurations.

    Input parameters represent values provided by users that drive the configuration process.
    """
    pass


class InputValueParam(InputParam):
    """
    Parameter representing a single user-provided value.

    Attributes
    ----------
    value : str or None
        The bound value of the parameter.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        """
        Initialize an input value parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        comment : str, optional
            Optional comment.
        """
        super().__init__(name, comment)
        self.value: Optional[str] = None

    def set_item(self, item):
        """
        Bind a value to this parameter.

        Parameters
        ----------
        item : Any
            The value to bind.

        Returns
        -------
        None
        """
        self.value = item


class InputFileParam(InputParam):
    """
    Parameter representing a file path provided by the user.

    Attributes
    ----------
    value : str or None
        The bound file path.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        """
        Initialize an input file parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        comment : str, optional
            Optional comment.
        """
        super().__init__(name, comment)
        self.value: Optional[str] = None

    def set_item(self, filepath: str):
        """
        Bind a file path to this parameter.

        Parameters
        ----------
        filepath : str
            The file path to bind.

        Returns
        -------
        None
        """
        self.value = filepath


class OutputParam(Param):
    """
    Base class for configuration parameters applied to a CESM/MOM6 case.

    Output parameters represent configurations that must be applied to the case.

    Attributes
    ----------
    value : Any
        The configuration value to apply.
    executed : bool
        Whether the configuration has been applied.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        """
        Initialize an output parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        comment : str, optional
            Optional comment.
        """
        super().__init__(name, comment)
        self.value: Any = None
        self.executed: bool = False

    def set_item(self, value: Any):
        """
        Set the value of this parameter.

        Parameters
        ----------
        value : Any
            The value to set.

        Returns
        -------
        None
        """
        self.value = value

    @abstractmethod
    def apply(self):
        """
        Apply the configuration change to the case.

        Returns
        -------
        None
        """
        pass

    @abstractmethod
    def inspect(cls, caseroot):
        """
        Inspect the current value of this parameter in the case.

        Parameters
        ----------
        caseroot : str or Path
            Path to the case root directory.

        Returns
        -------
        None
        """
        pass


class UserNLConfigParam(OutputParam):
    """
    Parameter written to a user_nl_<component> file (default: user_nl_mom).

    Attributes
    ----------
    user_nl_name : str
        Component name for the user_nl file (default: 'mom').
    """

    def __init__(
        self,
        name: str,
        user_nl_name: str = "mom",
        comment: Optional[str] = None,
    ):
        """
        Initialize a user_nl configuration parameter.

        Parameters
        ----------
        name : str
            Name of the parameter.
        user_nl_name : str, optional
            Component name for the user_nl file (default: 'mom').
        comment : str, optional
            Optional comment.
        """
        super().__init__(name, comment)
        self.user_nl_name = user_nl_name

    def apply(self):
        """
        Apply the parameter to the user_nl file.

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If the parameter value has not been set.
        """
        if self.value is None:
            raise ValueError(f"Value for parameter {self.name} has not been set.")

        param = [(self.name, self.value)]
        append_user_nl(
            self.user_nl_name,
            param,
            do_exec=True,
            comment=self.comment,
        )
        self.executed = True

    def inspect(self, caseroot):
        """
        Inspect and extract parameter value from the user_nl file in the case.

        Parameters
        ----------
        caseroot : str or Path
            Path to the case root directory.

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If the parameter value has already been set.
        FileNotFoundError
            If the user_nl file does not exist.
        KeyError
            If the parameter is not found in the user_nl file.
        """
        if self.value is not None:
            raise ValueError(f"Value for parameter {self.name} has already been set.")
        # Using caseroot, get to user_nl
        user_nl_path = Path(caseroot) / f"user_nl_{self.user_nl_name}"
        if not user_nl_path.exists():
            raise FileNotFoundError(f"{user_nl_path} does not exist.")
        # parse user_nl to find the parameter value
        with open(user_nl_path, "r") as f:
            for line in f:
                if line.strip().startswith(self.name):
                    # extract the value
                    _, value = line.split("=", 1)
                    self.executed = True
                    self.value = value.strip()
                    return
        raise KeyError(f"Parameter {self.name} not found in {user_nl_path }")


class XMLConfigParam(OutputParam):
    """
    Parameter applied via xmlchange command.

    XML changes are permanent and do not save previous state.

    Attributes
    ----------
    is_non_local : bool
        Whether the xmlchange is non-local.
    """

    def __init__(
        self,
        name: str,
        is_non_local: bool = False,
        comment: Optional[str] = None,
    ):
        """
        Initialize an XML configuration parameter.

        Parameters
        ----------
        name : str
            Name of the XML parameter.
        is_non_local : bool, optional
            Whether the xmlchange is non-local (default: False).
        comment : str, optional
            Optional comment.
        """
        super().__init__(name, comment)
        self.is_non_local = is_non_local

    def apply(self):
        """
        Apply the XML parameter change via xmlchange.

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If the parameter value has not been set.
        """
        if self.value is None:
            raise ValueError(f"Value for parameter {self.name} has not been set.")

        xmlchange(
            self.name,
            str(self.value),
            is_non_local=self.is_non_local,
        )
        self.executed = True

    def inspect(self, caseroot):
        """
        Inspect and extract XML parameter value from the case.

        Parameters
        ----------
        caseroot : str or Path
            Path to the case root directory.

        Returns
        -------
        None
        """
        if self.value is not None:
            raise ValueError(f"Value for parameter {self.name} has already been set.")
        # Using caseroot, query xml
        cmd = f"./xmlquery {self.name}"
        if self.is_non_local is True:
            cmd += " --non-local"

        runout = subprocess.run(cmd, shell=True, capture_output=True, cwd=caseroot)
        self.set_item(runout.stdout.decode().strip())


class BaseConfigurator(ABC):
    """
    Base class for all CrocoDash forcing configurators.

    Configurators manage input parameters and output parameters that control
    how forcing data is processed and applied to a case.

    Class Attributes
    ----------------
    name : str
        Name of the configurator.
    required_for_compsets : list of str
        List of compset substrings that require this configurator.
    allowed_compsets : list of str
        List of compset substrings for which this configurator is allowed.
    forbidden_compsets : list of str
        List of compset substrings for which this configurator is forbidden.
    input_params : list of Param
        List of input parameters for this configurator.
    output_params : list of OutputParam
        List of output parameters for this configurator.
    """

    def __eq__(self, other):
        """
        Compare two configurator instances for equality.

        Two configurators are equal if all their output parameter values match.

        Parameters
        ----------
        other : BaseConfigurator
            Another configurator instance to compare.

        Returns
        -------
        bool
            True if all output parameters match, False otherwise.
        """
        if not isinstance(other, BaseConfigurator):
            return NotImplemented
        for param in self.output_params:
            other_param = other.get_output_param_object(param.name)
            if str(param.value) != str(other_param.value):
                return False
        return True

    def __getattr__(self, name):
        """
        Allow accessing input parameter values as attributes.

        Enables accessing input parameters via self.param_name instead of
        self.get_input_param("param_name").

        Parameters
        ----------
        name : str
            The parameter name to access.

        Returns
        -------
        Any
            The value of the input parameter.

        Raises
        ------
        AttributeError
            If the parameter name does not correspond to an input parameter.
        """
        try:
            param = self.get_input_param(name)
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__} has no attribute '{name}'"
            ) from None
        return param

    def __init__(self, **kwargs):
        """
        Initialize a configurator with input arguments.

        Parameters
        ----------
        **kwargs
            Keyword arguments matching the input parameters of this configurator.

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If required inputs are missing or unexpected inputs are provided.
        """
        # Clone declared params for this instance
        self.input_params = [copy.copy(p) for p in self.__class__.input_params]
        self.output_params = [copy.copy(p) for p in self.__class__.output_params]

        self.validate_args(**kwargs)

        # Bind input values to parameters
        for param in self.input_params:
            param.set_item(kwargs[param.name])

    @classmethod
    def check_output_params_exist(cls):
        """
        Verify that output_params are defined on the class.

        Returns
        -------
        None

        Raises
        ------
        AssertionError
            If output_params is not defined.
        """
        assert hasattr(
            cls, "output_params"
        ), f"{cls.__name__} has no output_params defined."

    @classmethod
    def check_input_params_synced(cls):
        """
        Verify that __init__ arguments match input_params declaration.

        This check ensures consistency between the constructor signature and
        the declared input parameters.

        Returns
        -------
        None

        Raises
        ------
        AssertionError
            If there are missing or extra arguments.
        """
        sig = inspect.signature(cls.__init__)
        params = sig.parameters

        init_args = {name for name in params if name != "self"}

        input_param_names = {p.name for p in cls.input_params}

        missing = input_param_names - init_args
        extra = init_args - input_param_names

        assert not (missing), (
            f"{cls.__name__} init/input mismatch:\n"
            f"  Missing init args for input_params: {sorted(missing)}\n"
            f"  Extra init args not declared as input_params (which is okay and won't fail): {sorted(extra)}"
        )

    def validate_args(self, **kwargs):
        """
        Validate provided inputs against declared input_params.

        Parameters
        ----------
        **kwargs
            Keyword arguments to validate.

        Returns
        -------
        None

        Raises
        ------
        ValueError
            If required inputs are missing or unexpected inputs are provided.
        """
        expected = {p.name for p in self.input_params}
        provided = set(kwargs.keys())

        missing = expected - provided
        extra = provided - expected

        if missing:
            raise ValueError(f"Missing required inputs: {missing}")
        if extra:
            raise ValueError(f"Unexpected inputs: {extra}")

    @abstractmethod
    def configure(self):
        """
        Apply the configuration to the case.

        This abstract method must bind input values to output parameters
        and then apply them.

        Returns
        -------
        None
        """
        for p in self.output_params:
            p.apply()
        pass

    @classmethod
    def inspect(cls, caseroot):
        """
        Inspect case configuration and return a configurator instance.

        Creates a configurator with placeholder input values and output
        parameters extracted from the case.

        Parameters
        ----------
        caseroot : str or Path
            Path to the case root directory.

        Returns
        -------
        BaseConfigurator
            A configurator instance with values from the case.
        """
        placeholder_args = {}
        for param in cls.input_params:
            placeholder_args[param.name] = f""
        obj = cls(**placeholder_args)
        for param in obj.output_params:
            param.inspect(caseroot)
        return obj

    @classmethod
    def deserialize(cls, data: Dict[str, Any]):
        """
        Deserialize a configurator from a dictionary representation.

        Parameters
        ----------
        data : dict
            Dictionary with 'inputs' and 'outputs' keys containing parameter data.

        Returns
        -------
        BaseConfigurator
            A new configurator instance with restored state.

        Raises
        ------
        KeyError
            If required input or output parameters are missing.
        """
        input_kwargs = {}
        for param in cls.input_params:
            if param.name not in data["inputs"]:
                raise KeyError(f"Input param '{param.name}' not found in data")
            input_kwargs[param.name] = data["inputs"][param.name]

        obj = cls(**input_kwargs)
        for param in cls.output_params:
            if param.name not in data["outputs"]:
                raise KeyError(f"Output param '{param.name}' not found in data")
            obj.set_output_param(param.name, data["outputs"][param.name])
        return obj

    def make_serializable(self, obj):
        """
        Convert an object to a JSON-serializable form.

        Parameters
        ----------
        obj : Any
            Object to convert.

        Returns
        -------
        Any
            A serializable representation of the object.
        """
        if isinstance(obj, Path):
            return str(obj)
        return obj

    def serialize(self) -> Dict[str, Any]:
        """
        Serialize the configurator to a dictionary.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Dictionary with 'name', 'inputs', and 'outputs' keys.
        """
        output_dict = {"name": self.name, "inputs": {}, "outputs": {}}
        for param in self.input_params:
            output_dict["inputs"][param.name] = self.make_serializable(param.value)
        for param in self.output_params:
            output_dict["outputs"][param.name] = self.make_serializable(param.value)
        return output_dict

    def get_input_param(self, name: str) -> OutputParam:
        """
        Get the value of an input parameter.

        Parameters
        ----------
        name : str
            Name of the input parameter.

        Returns
        -------
        Any
            The value of the input parameter.

        Raises
        ------
        KeyError
            If the parameter name does not exist.
        """
        return self.get_input_param_object(name).value

    def get_input_param_object(self, name: str) -> OutputParam:
        """
        Get an input parameter object by name.

        Parameters
        ----------
        name : str
            Name of the input parameter.

        Returns
        -------
        Param
            The input parameter object.

        Raises
        ------
        KeyError
            If the parameter name does not exist.
        """
        try:
            return next(p for p in self.input_params if p.name == name)
        except StopIteration:
            raise KeyError(f"Input param '{name}' not found")

    def get_output_param(self, name: str) -> OutputParam:
        """
        Get the value of an output parameter.

        Parameters
        ----------
        name : str
            Name of the output parameter.

        Returns
        -------
        Any
            The value of the output parameter.

        Raises
        ------
        KeyError
            If the parameter name does not exist.
        """
        return self.get_output_param_object(name).value

    def get_output_param_object(self, name: str) -> OutputParam:
        """
        Get an output parameter object by name.

        Parameters
        ----------
        name : str
            Name of the output parameter.

        Returns
        -------
        OutputParam
            The output parameter object.

        Raises
        ------
        KeyError
            If the parameter name does not exist.
        """
        try:
            return next(p for p in self.output_params if p.name == name)
        except StopIteration:
            raise KeyError(f"Output param '{name}' not found")

    def set_output_param(self, name: str, value, is_non_local=None):
        """
        Set an output parameter value.

        Parameters
        ----------
        name : str
            Name of the output parameter.
        value : Any
            Value to set.
        is_non_local : bool, optional
            If provided and the parameter is XMLConfigParam, set is_non_local.

        Returns
        -------
        None

        Raises
        ------
        AssertionError
            If is_non_local is provided but the parameter is not XMLConfigParam.
        KeyError
            If the parameter name does not exist.
        """
        if is_non_local is not None:
            param = self.get_output_param_object(name)
            assert isinstance(
                param, XMLConfigParam
            ), f"Expected XMLConfigParam, got {type(param)}"
            param.is_non_local = is_non_local
        self.get_output_param_object(name).set_item(value)

    def set_input_param(self, name: str, value):
        """
        Set an input parameter value.

        Parameters
        ----------
        name : str
            Name of the input parameter.
        value : Any
            Value to set.

        Returns
        -------
        None

        Raises
        ------
        KeyError
            If the parameter name does not exist.
        """
        self.get_input_param_object(name).set_item(value)

    # ---- compset logic ----

    @classmethod
    def is_required(cls, compset: str) -> bool:
        """
        Check if this configurator is required for a given compset.

        Parameters
        ----------
        compset : str
            The component set string.

        Returns
        -------
        bool
            True if any required_for_compsets substring is found in the compset.
        """
        return any(sub in compset for sub in cls.required_for_compsets)

    @classmethod
    def validate_compset_compatibility(cls, compset: str) -> bool:
        """
        Check if this configurator is compatible with a given compset.

        A configurator is compatible if all allowed_compsets substrings are present
        and no forbidden_compsets substrings are present.

        Parameters
        ----------
        compset : str
            The component set string.

        Returns
        -------
        bool
            True if the configurator is compatible with the compset.
        """
        return all(sub in compset for sub in cls.allowed_compsets) and all(
            sub not in compset for sub in cls.forbidden_compsets
        )
