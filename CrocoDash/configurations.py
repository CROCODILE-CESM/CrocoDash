from pathlib import Path
from typing import List, Dict
from abc import ABC, abstractmethod
from dataclasses import dataclass
from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl
from CrocoDash.utils import setup_logger

logger = setup_logger(__name__)



class ConfiguratorRegistry:
    registered_types: List[type] = []
    active_configurators = []

    @classmethod
    def register(cls, configurator_cls: type):
        cls.registered_types.append(configurator_cls)

    @classmethod
    def configure_case(cls, compset, inputs: dict):
        cls.active_configurators.clear()

        # Iterate through Registry, find the inouts that match the args, if exist (if not then continue)

        for configurator in registered_types:

            # If required add to active configurators
            if configurator.is_required(compset):
                configurator = configurator_cls(inputs)
                logger.info(f"Configuration option is required: {configurator.name}")
                cls.active_configurators.append(**configurator)
            else:
                if not configurator_cls.validate_compset_compatibility(
                    inputs["compset"]
                ):

                    logger.info(
                        f"Configuration option is not compatible: {configurator.name}"
                    )
                    continue
                # Check if all required constructor args are in inputs
                import inspect

                sig = inspect.signature(configurator_cls.__init__)
                # Drop 'self' from parameters
                required_args = [
                    p.name for p in sig.parameters.values() if p.name != "self"
                ]
                if not all(arg in inputs for arg in required_args):
                    logger.info(
                        f"Configuration option does not gave all the required args: {configurator.name} {required_args}"
                    )
                    continue

                cls.active_configurators.append(configurator_cls(**inputs))
            logger.info(f"Configuring {configurator.name}")
            configurator.configure()


class BaseConfigurator(ABC):
    """Base class for all CrocoDash configurators."""

    name: str
    required_for_compsets: List[str] = []  # What compsets you must have this class
    allowed_compsets: List[str] = (
        []
    )  # What compsets this class is allowed for (must have all in the compset, e.g. DROF and BGC for river nutrients)
    forbidden_compsets: List[str] = []  # What compsets you cannot have this class

    def __init__(self, **kwargs):
        # Store everything directly as attributes
        for k, v in kwargs.items():
            setattr(self, k, v)

    @abstractmethod
    def configure(self):
        pass

    @abstractmethod
    def deconfigure(self):
        pass

    @classmethod
    def is_required(cls, compset):
        if cls.validate_compset_compatibility(compset):
            return any(sub in compset for sub in cls.required_for_compsets)

    @classmethod
    def validate_compset_compatibility(cls, compset):
        return all(sub in compset for sub in cls.allowed_compsets) and all(
            sub not in compset for sub in cls.forbidden_compsets
        )


class TidesConfigurator(BaseConfigurator):
    name = "tides"
    expected_output_files = [
        "tu_segment_{boundaries}.nc",
        "tz_segment_{boundaries}.nc",
    ]

    def __init__(
        self,
        tpxo_elevation_filepath,
        tpxo_velocity_filepath,
        tidal_constituents,
        boundaries,
    ):
        super().__init__(
            tpxo_elevation_filepath=tpxo_elevation_filepath,
            tpxo_velocity_filepath=tpxo_velocity_filepath,
            tidal_constituents=tidal_constituents,
            boundaries=boundaries,
        )

    def configure(self):
        pass


class BGCICConfigurator(BaseConfigurator):
    name = "BGCIC"
    expected_output_files = ["{self.marbl_ic_filepath.name}"]
    required_for_compsets = {"MARBL"}
    allowed_compsets = {"MARBL"}
    forbidden_compsets = []

    def __init__(self, marbl_ic_filepath):
        super().__init__(marbl_ic_filepath=marbl_ic_filepath)

    def configure(self):
        pass


class BGCIronForcingConfigurator(BaseConfigurator):
    name = "BGCIronForcing"
    required_for_compsets = {"MARBL"}
    allowed_compsets = {"MARBL"}
    forbidden_compsets = []

    expected_output_files = [
        "fesedflux_total_reduce_oxic_{ocn_grid_name}_{session_id}.nc",
        "feventflux_5gmol_{ocn_grid_name}_{session_id}.nc",
    ]

    def __init__(self, session_id, grid_name):
        super().__init__(session_id=session_id, grid_name=grid_name)

    def configure(self):
        pass


class BGCRiverNutrientsConfigurator(BaseConfigurator):
    name = "BGCRiverNutrients"
    expected_output_files = ["river_nutrients_{ocn_grid_name}_{session_id}_nnsm.nc"]
    required_for_compsets = []
    allowed_compsets = {"MARBL", "DROF"}
    forbidden_compsets = []

    def __init__(self, global_river_nutrients_filepath, session_id, grid_name):
        super().__init__(
            global_river_nutrients_filepath=global_river_nutrients_filepath,
            session_id=session_id,
            grid_name=grid_name,
        )

    def configure(self):
        pass


class RunoffConfigurator(BaseConfigurator):
    name = "Runoff"
    expected_output_files = ["glofas_{ocn_grid_name}_{session_id}_nnsm.nc"]
    required_for_compsets = {"DROF"}
    allowed_compsets = {"DROF"}
    forbidden_compsets = []

    def __init__(self, runoff_esmf_mesh_filepath, grid_name, session_id):
        super().__init__(
            runoff_esmf_mesh_filepath=runoff_esmf_mesh_filepath,
            grid_name=grid_name,
            session_id=session_id,
        )
        self.runoff_mapping_file_nnsm = ( f"glofas_{self.grid_name}_{self.session_id}_nnsm.nc")
        params.append(XMLConfigParam("ROF2OCN_LIQ_RMAPNAME", self.runoff_mapping_file_nnsm))
        params.append(XMLConfigParam("ROF2OCN_LIQ_RMAPNAME", self.runoff_mapping_file_nnsm))



    def configure(self):
        for p in params:
            p.apply()

    def deconfigure(self):
        raise NotImplementedError("You cannot undo runoff mapping configuration")



class ChlConfigurator(BaseConfigurator):
    name = "Chl"
    expected_output_files = ["seawifs-clim-1997-2010-{ocn_grid_name}-{session_id}.nc"]
    required_for_compsets = []
    allowed_compsets = []
    forbidden_compsets = {"MARBL"}
    params = []

    def __init__(self, chl_processed_filepath, grid_name, session_id):
        super().__init__(
            chl_processed_filepath=chl_processed_filepath,
            grid_name=grid_name,
            session_id=session_id,
        )
        self.regional_chl_file_path =  f"seawifs-clim-1997-2010-{self.grid_name}.nc"
        params.append(UserNLConfigParam("CHL_FILE", Path(self.regional_chl_file_path), "mom"))
        params.append(UserNLConfigParam("CHL_FROM_FILE", "TRUE", "mom"))
        params.append(UserNLConfigParam("VAR_PEN_SW", "TRUE", "mom"))
        params.append(UserNLConfigParam("PEN_SW_NBANDS", 3, "mom"))
        
    

    def configure(self):
        for p in params:
            p.apply()

    def deconfigure(self):
        for p in params:
            if type(p) == UserNLConfigParam:
                p.remove()

            



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
