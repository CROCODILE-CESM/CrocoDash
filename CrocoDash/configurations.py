from pathlib import Path
from typing import List, Dict
from abc import ABC, abstractmethod
from dataclasses import dataclass
from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl


@dataclass
class ConfigParam(ABC):
    name: str
    value: str
    comment: str = None
    executed = False

    @abstractmethod
    def apply():
        pass

    @abstractmethod
    def remove():
        pass


@dataclass
class UserNLConfigParam(ConfigParam):
    user_nl_name: str

    def apply(self):
        executed = True
        param = [(self.name, self.value)]
        append_user_nl(self.user_nl_name, param, do_exec=True, comment=self.comment)

    def remove(self):
        remove_user_nl(self.user_nl_name, param)
        exectued = False


@dataclass
class XMLConfigParam(ConfigParam):
    is_non_local = False
    executed = False

    def apply(self):
        executed = True
        xmlchange(
            self.name,
            str(self.value),
            is_non_local=is_non_local,
        )

    def remove(self):
        raise ValueError("You cannot remove an xml change")


class ConfiguratorRegistry:
    registered_types: List[type] = []
    active_configurators = []

    @classmethod
    def register(cls, configurator_cls: type):
        cls.registered_types.append(configurator_cls)

    @classmethod
    def configure_case(cls, inputs: dict):

        # Iterate through Registry, find the inouts that match the args
        for configurator in registered_types:
            satisfied_args = True
            for arg in configurator.input_args:
                if arg not in inputs:
                    satisfied_args = False
            if not satisfied_args:
                continue

            # Create the corresponding configurator

            configurator = configurator_cls(inputs)

            # add to list
            cls.active_configurators.append(configurator)

            configurator.validate_args_satisfied()
            configurator.validate_input_files_exist()
            configurator.validate_param_inputs()
            configurator.set_user_nl_params()
            configurator.set_xml_params()
            activate_configurators.append(configurator)


class BaseConfigurator(ABC):
    """Base class for all CrocoDash configurators (which are singleton classes)."""

    name: str
    file_inputs: List[str]
    param_inputs: List[str]
    required_for_compset: List[str]
    compsets_required_for: List[str]
    expected_output_files: List[str]

    def __init__(self, inputs):
        self.inputs = inputs

    # ---- Validation methods ----
    def check_if_args_satisfied(self, inputs: Dict):
        required = set(self.file_inputs) | set(self.param_inputs)
        provided = set(inputs.keys())

        missing = required - provided
        if missing:
            return False
        return True

    def validate_input_files_exist(self, inputs: Dict):
        for item in self.file_inputs:
            filepath = inputs.get(item)
            if not Path(filepath).exists():
                raise ValueError(f"{self.name}: file does not exist: {filepath}")

    def validate_param_inputs(self, inputs: Dict):
        """Optional hook for subclasses to implement extra validation."""
        pass

    @abstractmethod
    def set_params():
        pass


class TidesConfigurator(BaseConfigurator):
    name = "tides"
    self.file_inputs = ["tpxo_elevation_filepath", "tpxo_velocity_filepath"]
    self.param_inputs = ["tidal_constituents", "boundaries"]
    self.expected_output_files = [
        "tu_segment_{boundaries}.nc",
        "tz_segment_{boundaries}.nc",
    ]

    def generate_output_file_names(self, **kwargs):
        """Need unique handling because I get multiple file names"""
        pass


class BGCICConfigurator(BaseConfigurator):
    name = "BGCIC"
    self.file_inputs = []
    self.required_for_compset = ["MOM6%REGIONAL%MARBL-BIO"]
    self.param_inputs = ["marbl_ic_filepath"]
    self.expected_output_files = ["{self.marbl_ic_filepath.name}"]


class BGCIronForcingConfigurator(BaseConfigurator):
    name = "BGCIronForcing"
    self.file_inputs = []
    self.param_inputs = ["session_id", "grid_name"]
    self.required_for_compset = ["MOM6%REGIONAL%MARBL-BIO"]
    self.expected_output_files = [
        "fesedflux_total_reduce_oxic_{ocn_grid_name}_{session_id}.nc",
        "feventflux_5gmol_{ocn_grid_name}_{session_id}.nc",
    ]


class BGCRiverNutrientsConfigurator(BaseConfigurator):
    name = "BGCRiverNutrients"
    self.file_inputs = ["global_river_nutrients_filepath"]
    self.param_inputs = ["session_id", "grid_name"]
    self.compsets_required_for = ["MOM6%REGIONAL%MARBL-BIO", "DROF"]
    self.expected_output_files = [
        "river_nutrients_{ocn_grid_name}_{session_id}_nnsm.nc"
    ]


class RunoffConfigurator(BaseConfigurator):
    name = "Runoff"

    self.file_inputs = ["runoff_esmf_mesh_filepath"]
    self.param_inputs = ["grid_name", "session_id"]
    self.required_for_compset = ["DROF"]
    self.expected_output_files = ["glofas_{ocn_grid_name}_{session_id}_nnsm.nc"]


class ChlConfigurator(BaseConfigurator):
    name = "Chl"

    self.file_inputs = ["chl_processed_filepath"]
    self.param_inputs = ["grid_name", "session_id"]
    self.required_for_compset = ["MOM6%REGIONAL_"]
    self.expected_output_files = [
        "seawifs-clim-1997-2010-{ocn_grid_name}-{session_id}.nc"
    ]
