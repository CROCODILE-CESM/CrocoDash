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
from CrocoDash.forcing_configurations import *

logger = setup_logger(__name__)


def is_serializable(v):
    return isinstance(v, (str, int, float, bool, type(None), Path, list, dict))


class ForcingConfigRegistry:
    registered_types: List[type] = []

    @classmethod
    def register(cls, configurator_cls: type):

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
    def get_configurator_from_name(cls, name):
        for thing in cls.registered_types:
            if name.lower() == thing.name.lower():
                return thing
        raise ValueError("Configurator Not Found")

    @classmethod
    def get_configurator(cls, obj_dict):
        return cls.get_configurator_from_name(obj_dict["name"]).deserialize(obj_dict)

    @classmethod
    def find_valid_configurators(cls, compset):
        """Returns the valid configurations based on the compset in a list"""
        valid_configs = []
        for configurator_cls in cls.registered_types:
            if configurator_cls.validate_compset_compatibility(compset):
                valid_configs.append(configurator_cls)
        return valid_configs

    @classmethod
    def find_required_configurators(cls, compset):
        """Returns the required configurations based on the compset in a list"""
        required_configs = []
        for configurator_cls in cls.registered_types:
            if configurator_cls.is_required(compset):
                required_configs.append(configurator_cls)
        return required_configs

    @classmethod
    def get_ctor_signature(cls, configurator_cls):
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
        args, required_args = cls.get_ctor_signature(configurator_cls)
        user_args = [arg for arg in required_args if not arg.startswith("case_")]
        return user_args

    @classmethod
    def return_missing_inputs(cls, configurator_cls, inputs):
        _, required_args = cls.get_ctor_signature(configurator_cls)
        missing = [arg for arg in required_args if arg not in inputs]
        return missing

    @classmethod
    def instantiate_configurator(cls, configurator_cls, inputs):
        args, _ = cls.get_ctor_signature(configurator_cls)
        ctor_kwargs = {arg: inputs[arg] for arg in args if arg in inputs}
        return configurator_cls(**ctor_kwargs)

    def find_active_configurators(self, compset, inputs: dict):

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
        return self.active_configurators.keys()

    def is_active(self, name: str) -> bool:
        """Return True if a configurator with this name is active."""
        return name.lower() in self.active_configurators


class Param(ABC):
    """
    Base class for a single parameter in our forcing configurations.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        self.name = name
        self.comment = comment

    @abstractmethod
    def set_item(self, item: Any):
        """Bind a runtime value to this parameter."""
        pass


class InputParam(Param):
    pass


class InputValueParam(InputParam):
    """
    Base class for a single value parameter in our forcing configurations.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        super().__init__(name, comment)
        self.value: Optional[str] = None

    def set_item(self, item):
        self.value = item


class InputFileParam(InputParam):
    """
    Base class for a single file parameter in our forcing configurations.
    """

    def __init__(self, name: str, comment: Optional[str] = None):
        super().__init__(name, comment)
        self.value: Optional[str] = None

    def set_item(self, filepath: str):
        self.value = filepath


class OutputParam(Param):
    """
    Base class for a single configuration parameter applied to a CESM/MOM6 case.
    """

    def __init__(self, name: str, comment: Optional[str] = None, is_file: bool = False):
        super().__init__(name, comment)
        self.value: Any = None
        self.executed: bool = False
        self.is_file = is_file

    def set_item(self, value: Any):
        self.value = value

    @abstractmethod
    def apply(self):
        """Apply the configuration change."""
        pass

    @abstractmethod
    def inspect(cls, caseroot):
        """Inspect the current value of this parameter in the case located at caseroot."""
        pass


class UserNLConfigParam(OutputParam):
    """
    Parameter written to a `user_nl_<component>` file (default: user_nl_mom).
    """

    def __init__(
        self,
        name: str,
        user_nl_name: str = "mom",
        comment: Optional[str] = None,
        is_file: bool = False,
    ):
        super().__init__(name, comment, is_file=is_file)
        self.user_nl_name = user_nl_name

    def apply(self):
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
    Parameter applied via xmlchange.

    XML changes are permanent and do not save previous state.
    """

    def __init__(
        self,
        name: str,
        is_non_local: bool = False,
        comment: Optional[str] = None,
        is_file: bool = False,
    ):
        super().__init__(name, comment, is_file=is_file)
        self.is_non_local = is_non_local

    def apply(self):
        if self.value is None:
            raise ValueError(f"Value for parameter {self.name} has not been set.")

        xmlchange(
            self.name,
            str(self.value),
            is_non_local=self.is_non_local,
        )
        self.executed = True

    def inspect(self, caseroot):
        if self.value is not None:
            raise ValueError(f"Value for parameter {self.name} has already been set.")
        # Using caseroot, query xml
        cmd = f"./xmlquery {self.name}"
        if self.is_non_local is True:
            cmd += " --non-local"

        runout = subprocess.run(cmd, shell=True, capture_output=True, cwd=caseroot)
        self.set_item(runout.stdout.decode().strip())


class BaseConfigurator(ABC):
    """Base class for all CrocoDash configurators."""

    # ---- class-level declarative metadata ----
    name: str = ""

    required_for_compsets: List[str] = []
    allowed_compsets: List[str] = []
    forbidden_compsets: List[str] = []

    input_params: List[Param]
    output_params: List[OutputParam]

    def __eq__(self, other):
        if not isinstance(other, BaseConfigurator):
            return NotImplemented
        for param in self.output_params:
            other_param = other.get_output_param_object(param.name)
            if str(param.value) != str(other_param.value):
                return False
        return True

    def __getattr__(self, name):
        """
        Allow input params to be accessed as attributes:
        self.date_range -> self.get_input_param("date_range").value
        """
        try:
            param = self.get_input_param(name)
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__} has no attribute '{name}'"
            ) from None
        return param

    def __init__(self, **kwargs):
        # Clone declared params for this instance
        self.input_params = [copy.copy(p) for p in self.__class__.input_params]
        self.output_params = [copy.copy(p) for p in self.__class__.output_params]

        self.validate_args(**kwargs)

        # Bind input values to parameters
        for param in self.input_params:
            param.set_item(kwargs[param.name])

    @classmethod
    def check_output_params_exist(cls):
        assert hasattr(
            cls, "output_params"
        ), f"{cls.__name__} has no output_params defined."

    @classmethod
    def check_input_params_synced(cls):
        """Make sure the init args exactly match the input param names. This check is only run in testing"""
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
        """Validate provided inputs against declared input_params."""
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
        """Bind input values to parameters and files."""
        for p in self.output_params:
            p.apply()
        pass

    @classmethod
    def inspect(cls, caseroot):
        """Return an instance of the configurator with placeholder values for input and correct output params from case"""

        placeholder_args = {}
        for param in cls.input_params:
            placeholder_args[param.name] = f""
        obj = cls(**placeholder_args)
        for param in obj.output_params:
            param.inspect(caseroot)
        return obj

    @classmethod
    def deserialize(cls, data: Dict[str, Any]):
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
        if isinstance(obj, Path):
            return str(obj)
        return obj

    def serialize(self) -> Dict[str, Any]:
        output_dict = {"name": self.name, "inputs": {}, "outputs": {}}
        for param in self.input_params:
            output_dict["inputs"][param.name] = self.make_serializable(param.value)
        for param in self.output_params:
            output_dict["outputs"][param.name] = self.make_serializable(param.value)
        return output_dict

    def get_input_param(self, name: str) -> OutputParam:
        return self.get_input_param_object(name).value

    def get_input_param_object(self, name: str) -> OutputParam:
        try:
            return next(p for p in self.input_params if p.name == name)
        except StopIteration:
            raise KeyError(f"Input param '{name}' not found")

    def get_output_param(self, name: str) -> OutputParam:
        return self.get_output_param_object(name).value

    def get_output_param_object(self, name: str) -> OutputParam:
        try:
            return next(p for p in self.output_params if p.name == name)
        except StopIteration:
            raise KeyError(f"Output param '{name}' not found")

    def set_output_param(self, name: str, value, is_non_local=None):
        if is_non_local is not None:
            param = self.get_output_param_object(name)
            assert isinstance(
                param, XMLConfigParam
            ), f"Expected XMLConfigParam, got {type(param)}"
            param.is_non_local = is_non_local
        self.get_output_param_object(name).set_item(value)

    def set_input_param(self, name: str, value):
        self.get_input_param_object(name).set_item(value)

    # ---- compset logic ----

    @classmethod
    def is_required(cls, compset: str) -> bool:
        return any(sub in compset for sub in cls.required_for_compsets)

    @classmethod
    def validate_compset_compatibility(cls, compset: str) -> bool:
        return all(sub in compset for sub in cls.allowed_compsets) and all(
            sub not in compset for sub in cls.forbidden_compsets
        )

    def get_output_filepaths(self, ocn_ice_directory):
        """Get output files from the output parameters"""
        potential_output_paths = []
        for output in self.output_params:
            if output.is_file:
                potential_file_path = Path(ocn_ice_directory) / str(output.value)
                if potential_file_path.exists():
                    potential_output_paths.append(potential_file_path)
        return potential_output_paths
