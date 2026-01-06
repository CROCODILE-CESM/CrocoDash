from pathlib import Path
from typing import List, Dict
from abc import ABC, abstractmethod
from dataclasses import dataclass
from visualCaseGen.custom_widget_types.case_tools import (
    xmlchange,
    append_user_nl,
)
from CrocoDash.logging import setup_logger
import inspect
from ProConPy.config_var import ConfigVar, cvars
from mom6_bathy import mapping
from typing import Optional, Any
import copy
import subprocess

logger = setup_logger(__name__)


# START FRAMEWORK


def register(cls):
    ForcingConfigRegistry.register(cls)
    return cls


def is_serializable(v):
    return isinstance(v, (str, int, float, bool, type(None), Path, list, dict))


class ForcingConfigRegistry:
    registered_types: List[type] = []

    @classmethod
    def register(cls, configurator_cls: type):

        cls.registered_types.append(configurator_cls)

    def __getitem__(self, key: str):
        return self.active_configurators[key.lower()]

    def __init__(self, compset, inputs: dict, case):
        self.compset = compset
        self.active_configurators = {}

        self.case_info = {
            f"case_{k}": v
            for k, v in self.__dict__.items()
            if not k.startswith("_") and is_serializable(v)
        }
        inputs = inputs | self.case_info
        self.find_active_configurators(self.compset, inputs)

    @classmethod
    def deserialize(cls, obj_dict):
        name = obj_dict["name"]
        for thing in cls.registered_types:
            if name == thing.name:
                return thing.deserialize(obj_dict)
        raise ValueError(f"Unknown configurator name: {name}")

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

    def run_configurators(self):
        # Run Configurators
        for configurator in self.active_configurators.values():
            logger.info(f"Configuring {configurator.name}")
            configurator.configure()

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

    def __init__(self, name: str, comment: Optional[str] = None):
        super().__init__(name, comment)
        self.value: Any = None
        self.executed: bool = False

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
    ):
        super().__init__(name, comment)
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
            raise FileNotFoundError(f"{user_nls_path} does not exist.")
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
    ):
        super().__init__(name, comment)
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

        assert not (missing or extra), (
            f"{self.__class__.__name__} init/input mismatch:\n"
            f"  Missing init args for input_params: {sorted(missing)}\n"
            f"  Extra init args not declared as input_params: {sorted(extra)}"
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

    def serialize(self) -> Dict[str, Any]:
        output_dict = {"name": self.name, "inputs": {}, "outputs": {}}
        for param in self.input_params:
            output_dict["inputs"][param.name] = param.value
        for param in self.output_params:
            output_dict["outputs"][param.name] = param.value
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

    def set_output_param(self, name: str, value):
        self.get_output_param_object(name).set_item(value)

    # ---- compset logic ----

    @classmethod
    def is_required(cls, compset: str) -> bool:
        return any(sub in compset for sub in cls.required_for_compsets)

    @classmethod
    def validate_compset_compatibility(cls, compset: str) -> bool:
        return all(sub in compset for sub in cls.allowed_compsets) and all(
            sub not in compset for sub in cls.forbidden_compsets
        )


# END FRAMEWORK


@register
class TidesConfigurator(BaseConfigurator):
    name = "tides"
    input_params = [
        InputFileParam(
            "tpxo_elevation_filepath",
            comment="NetCDF file containing tidal elevation data",
        ),
        InputFileParam(
            "tpxo_velocity_filepath",
            comment="NetCDF file containing tidal velocity data",
        ),
        InputValueParam(
            "tidal_constituents",
            comment="List of tidal constituents to include",
        ),
        InputValueParam(
            "date_range",
            comment="date_range for the simulation",
        ),
        InputValueParam(
            "boundaries",
            comment="boundaries to apply tidal forcing (e.g., ['N', 'S', 'E', 'W'])",
        ),
    ]
    output_params = [
        UserNLConfigParam("TIDES", comment="Enable tidal forcing in MOM6"),
        UserNLConfigParam("TIDE_M2", comment="Enable M2 tidal constituent"),
        UserNLConfigParam("CD_TIDES", comment="Drag coefficient for tidal forcing"),
        UserNLConfigParam(
            "TIDE_USE_EQ_PHASE", comment="Use equilibrium phase for tides"
        ),
        UserNLConfigParam("TIDE_REF_DATE", comment="Reference date for tidal forcing"),
        UserNLConfigParam(
            "OBC_TIDE_ADD_EQ_PHASE", comment="Add equilibrium phase to OBC tides"
        ),
        UserNLConfigParam(
            "OBC_TIDE_N_CONSTITUENTS", comment="Number of tidal constituents"
        ),
        UserNLConfigParam(
            "OBC_TIDE_CONSTITUENTS", comment="List of tidal constituents"
        ),
        UserNLConfigParam(
            "OBC_TIDE_REF_DATE", comment="Reference date for OBC tidal forcing"
        ),
    ]

    def __init__(
        self,
        tpxo_elevation_filepath,
        tpxo_velocity_filepath,
        tidal_constituents,
        date_range,
        boundaries,
    ):

        # Set the input params
        super().__init__(
            tpxo_elevation_filepath=tpxo_elevation_filepath,
            tpxo_velocity_filepath=tpxo_velocity_filepath,
            tidal_constituents=tidal_constituents,
            date_range=date_range,
            boundaries=boundaries,
        )

    def tidal_data_str(self, seg_ix):
        return (
            f",Uamp=file:tu_segment_{seg_ix}.nc(uamp),"
            f"Uphase=file:tu_segment_{seg_ix}.nc(uphase),"
            f"Vamp=file:tu_segment_{seg_ix}.nc(vamp),"
            f"Vphase=file:tu_segment_{seg_ix}.nc(vphase),"
            f"SSHamp=file:tz_segment_{seg_ix}.nc(zamp),"
            f"SSHphase=file:tz_segment_{seg_ix}.nc(zphase)"
        )

    def configure(self):
        # Set the output params
        self.set_output_param("TIDES", "True")
        self.set_output_param("TIDE_M2", "True")
        self.set_output_param("CD_TIDES", 0.0018)
        self.set_output_param("TIDE_USE_EQ_PHASE", "True")
        date_range = self.get_input_param("date_range")
        self.set_output_param(
            "TIDE_REF_DATE",
            f"{date_range[0].year}, {date_range[0].month}, {date_range[0].day}",
        )
        self.set_output_param("OBC_TIDE_ADD_EQ_PHASE", "True")
        self.set_output_param(
            "OBC_TIDE_N_CONSTITUENTS",
            len(self.get_input_param("tidal_constituents")),
        )
        self.set_output_param(
            "OBC_TIDE_CONSTITUENTS",
            '"' + ", ".join(self.get_input_param("tidal_constituents")) + '"',
        )
        self.set_output_param(
            "OBC_TIDE_REF_DATE",
            f"{date_range[0].year}, {date_range[0].month}, {date_range[0].day}",
        )
        super().configure()
        # You also need to add the files to the OBC string, which is handled in the main case unfortunately


@register
class BGCConfigurator(BaseConfigurator):
    name = "BGC"
    required_for_compsets = ["MARBL"]
    allowed_compsets = ["MARBL"]
    input_params = []
    output_params = [
        UserNLConfigParam(
            "MAX_FIELDS",
            comment="Maximum number of tracer fields, bumped to accomodate MARBL tracers",
        )
    ]

    def __init__(
        self,
    ):
        super().__init__()

    def configure(self):
        self.set_output_param("MAX_FIELDS", 200)
        super().configure()


@register
class CICEConfigurator(BaseConfigurator):
    name = "CICE"
    required_for_compsets = ["CICE"]
    allowed_compsets = ["CICE"]
    input_params = []
    output_params = [
        UserNLConfigParam("ice_ic", user_nl_name="cice"),
        UserNLConfigParam("ns_boundary_type", user_nl_name="cice"),
        UserNLConfigParam("ew_boundary_type", user_nl_name="cice"),
        UserNLConfigParam("close_boundaries", user_nl_name="cice"),
    ]

    def __init__(
        self,
    ):
        super().__init__()

    def configure(self):
        self.set_output_param("ice_ic", "'UNSET'")
        self.set_output_param("ns_boundary_type", "'open'")
        self.set_output_param("ew_boundary_type", "'cyclic'")
        self.set_output_param("close_boundaries", ".false.")
        super().configure()


@register
class BGCICConfigurator(BaseConfigurator):
    name = "BGCIC"
    required_for_compsets = ["MARBL"]
    allowed_compsets = ["MARBL"]
    input_params = [
        InputFileParam(
            "marbl_ic_filepath",
            comment="NetCDF file containing MARBL initial conditions",
        )
    ]
    output_params = [
        UserNLConfigParam(
            "MARBL_TRACERS_IC_FILE",
            comment="MARBL initial conditions file",
            user_nl_name="mom",
        )
    ]

    def __init__(self, marbl_ic_filepath):
        super().__init__(marbl_ic_filepath=marbl_ic_filepath)
        self.marbl_ic_filename = Path(marbl_ic_filepath).name

    def configure(self):
        self.set_output_param(
            "MARBL_TRACERS_IC_FILE", self.get_input_param("marbl_ic_filepath")
        )
        super().configure()


@register
class BGCIronForcingConfigurator(BaseConfigurator):
    name = "BGCIronForcing"
    required_for_compsets = ["MARBL"]
    allowed_compsets = ["MARBL"]
    input_params = [
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam("case_grid_name", comment="Case grid name"),
    ]
    output_params = [
        UserNLConfigParam(
            "MARBL_FESEDFLUX_FILE",
            comment="MARBL sedimentary iron flux file",
            user_nl_name="mom",
        ),
        UserNLConfigParam(
            "MARBL_FEVENTFLUX_FILE",
            comment="MARBL event iron flux file",
            user_nl_name="mom",
        ),
    ]

    def __init__(self, case_session_id, case_grid_name):
        super().__init__(case_session_id=case_session_id, case_grid_name=case_grid_name)

    def configure(self):
        feventflux_filepath = f"feventflux_5gmol_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}.nc"
        fesedflux_filepath = f"fesedflux_total_reduce_oxic_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}.nc"
        self.set_output_param("MARBL_FESEDFLUX_FILE", fesedflux_filepath)
        self.set_output_param("MARBL_FEVENTFLUX_FILE", feventflux_filepath)
        super().configure()


@register
class BGCRiverNutrientsConfigurator(BaseConfigurator):
    name = "BGCRiverNutrients"
    allowed_compsets = ["MARBL", "DROF"]
    input_params = [
        InputFileParam(
            "global_river_nutrients_filepath",
            comment="NetCDF file containing global river nutrients data",
        ),
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam("case_grid_name", comment="Case grid name"),
    ]
    output_params = [
        UserNLConfigParam(
            "READ_RIV_FLUXES",
            comment="Enable river nutrient fluxes in MOM6",
            user_nl_name="mom",
        ),
        UserNLConfigParam(
            "RIV_FLUX_FILE",
            comment="River nutrient flux file",
            user_nl_name="mom",
        ),
    ]

    def __init__(
        self, global_river_nutrients_filepath, case_session_id, case_grid_name
    ):
        super().__init__(
            global_river_nutrients_filepath=global_river_nutrients_filepath,
            case_session_id=case_session_id,
            case_grid_name=case_grid_name,
        )

    def validate_args(self, **kwargs):
        if not Path(kwargs["global_river_nutrients_filepath"]).exists():
            raise FileNotFoundError(
                f"River Nutrients file {kwargs['global_river_nutrients_filepath']} does not exist."
            )

    def configure(self):
        river_nutrients_nnsm_filepath = f"river_nutrients_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}_nnsm.nc"
        self.set_output_param("READ_RIV_FLUXES", "True")
        self.set_output_param("RIV_FLUX_FILE", river_nutrients_nnsm_filepath)

        super().configure()


@register
class RunoffConfigurator(BaseConfigurator):
    name = "Runoff"
    required_for_compsets = {"DROF"}
    allowed_compsets = {"DROF"}
    input_params = [
        InputFileParam(
            "runoff_esmf_mesh_filepath",
            comment="ESMF mesh file for runoff mapping",
        ),
        InputValueParam("case_grid_name", comment="Case grid name"),
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam("compset", comment="Case compset"),
        InputValueParam("case_inputdir", comment="Case input directory"),
        InputValueParam(
            "rmax", comment="Smoothing radius (in meters) for runoff mapping generation"
        ),
        InputValueParam(
            "fold", comment="Smoothing fold parameter for runoff mapping generation"
        ),
    ]
    output_params = [
        XMLConfigParam(
            "ROF2OCN_LIQ_RMAPNAME", comment="Runoff to ocean liquid runoff mapping file"
        ),
        XMLConfigParam(
            "ROF2OCN_ICE_RMAPNAME", comment="Runoff to ocean ice runoff mapping file"
        ),
    ]

    def __init__(
        self,
        runoff_esmf_mesh_filepath,
        case_grid_name,
        case_session_id,
        compset,
        case_inputdir,
        rmax=None,
        fold=None,
    ):
        """
        rmax : float, optional
            If passed, specifies the smoothing radius (in meters) for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        fold : float, optional
            If passed, specifies the smoothing fold parameter for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        """
        super().__init__(
            runoff_esmf_mesh_filepath=runoff_esmf_mesh_filepath,
            case_grid_name=case_grid_name,
            case_session_id=case_session_id,
            case_inputdir=case_inputdir,
            rmax=rmax,
            fold=fold,
            compset=compset,
        )

    def configure(self):
        runoff_mapping_file_nnsm = f"glofas_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}_nnsm.nc"
        rof_case_grid_name = cvars["CUSTOM_ROF_GRID"].value
        mapping_file_prefix = (
            f"{rof_case_grid_name}_to_{self.get_input_param('case_grid_name')}_map"
        )
        mapping_dir = Path(self.get_input_param("case_inputdir")) / "mapping"
        mapping_dir.mkdir(exist_ok=False)
        if self.get_input_param("rmax") is None:
            rmax, fold = mapping.get_suggested_smoothing_params(
                self.get_input_param("runoff_esmf_mesh_filepath")
            )
            self.set_output_param("rmax", rmax)
            self.set_output_param("fold", fold)
        self.runoff_mapping_file_nnsm = mapping.get_smoothed_map_filepath(
            mapping_file_prefix=mapping_file_prefix,
            output_dir=mapping_dir,
            rmax=self.get_input_param("rmax"),
            fold=self.get_input_param("fold"),
        )
        self.set_output_param("ROF2OCN_LIQ_RMAPNAME", self.runoff_mapping_file_nnsm)
        self.set_output_param("ROF2OCN_ICE_RMAPNAME", self.runoff_mapping_file_nnsm)
        super().configure()

    def validate_args(self, **kwargs):

        if (kwargs["rmax"] is None) != (kwargs["fold"] is None):
            raise ValueError("Both rmax and fold must be specified together.")
        if kwargs["rmax"] is not None:
            assert "SROF" not in kwargs["compset"], (
                "When rmax and fold are specified, "
                "the compset must include an active or data runoff model."
            )


@register
class ChlConfigurator(BaseConfigurator):
    name = "Chl"
    forbidden_compsets = ["MARBL"]
    input_params = [
        InputFileParam(
            "chl_processed_filepath",
            comment="NetCDF file containing processed chlorophyll data",
        ),
        InputValueParam("case_grid_name", comment="Case grid name"),
        InputValueParam("case_session_id", comment="Case session identifier"),
    ]
    output_params = [
        UserNLConfigParam(
            "CHL_FILE", comment="Chlorophyll data file", user_nl_name="mom"
        ),
        UserNLConfigParam(
            "CHL_FROM_FILE", comment="Enable chlorophyll from file", user_nl_name="mom"
        ),
        UserNLConfigParam(
            "VAR_PEN_SW",
            comment="Enable variable penetration for shortwave",
            user_nl_name="mom",
        ),
        UserNLConfigParam(
            "PEN_SW_NBANDS",
            comment="Number of shortwave penetration bands",
            user_nl_name="mom",
        ),
    ]

    def __init__(self, chl_processed_filepath, case_grid_name, case_session_id):

        super().__init__(
            chl_processed_filepath=chl_processed_filepath,
            case_grid_name=case_grid_name,
            case_session_id=case_session_id,
        )

    def validate_args(self, **kwargs):
        if not Path(kwargs["chl_processed_filepath"]).exists():
            raise FileNotFoundError(
                f"Chlorophyll file {kwargs['chl_processed_filepath']} does not exist."
            )

    def configure(self):
        regional_chl_file_path = (
            f"seawifs-clim-1997-2010-{self.get_input_param('case_grid_name')}.nc"
        )
        self.set_output_param("CHL_FILE", regional_chl_file_path)
        self.set_output_param("CHL_FROM_FILE", "TRUE")
        self.set_output_param("VAR_PEN_SW", "TRUE")
        self.set_output_param("PEN_SW_NBANDS", 3)
        super().configure()
