from pathlib import Path
from typing import List, Dict
from abc import ABC, abstractmethod
from dataclasses import dataclass
from visualCaseGen.custom_widget_types.case_tools import (
    xmlchange,
    append_user_nl,
)
from CrocoDash.utils import setup_logger
import inspect
from ProConPy.config_var import ConfigVar, cvars

logger = setup_logger(__name__)


def register(cls):
    ForcingConfigRegistry.register(cls)
    return cls


class ForcingConfigRegistry:
    registered_types: List[type] = []

    @classmethod
    def register(cls, configurator_cls: type):

        cls.registered_types.append(configurator_cls)

    def __getitem__(self, key: str):
        return self.active_configurators[key.lower()]

    def __init__(self, compset, inputs: dict):
        self.active_configurators = {}
        self.find_active_configurators(compset, inputs)

    def find_active_configurators(self, compset, inputs: dict):
        inputs["compset"] = compset
        # Find Active Configurators
        for configurator_cls in self.registered_types:
            sig = inspect.signature(configurator_cls.__init__)
            args = [p.name for p in sig.parameters.values() if p.name != "self"]
            required_args = [
                p.name
                for p in sig.parameters.values()
                if p.name != "self" and p.default is inspect._empty
            ]
            # If required add to active configurators
            if configurator_cls.is_required(compset):

                logger.info(f"[REQUIRED] Activating {configurator_cls.name}")
                if not all(arg in inputs for arg in required_args):
                    raise ValueError(
                        f"[ERROR] Required configurator {configurator_cls.name} missing at least one of the args: {required_args}"
                    )
                ctor_kwargs = {arg: inputs[arg] for arg in args if arg in inputs}
                self.active_configurators[configurator_cls.name.lower()] = (
                    configurator_cls(**ctor_kwargs)
                )
            else:
                if not configurator_cls.validate_compset_compatibility(compset):

                    logger.info(
                        f"[SKIP] {configurator_cls.name} incompatible with compset"
                    )
                    continue
                if not all(arg in inputs for arg in required_args):
                    logger.info(
                        f"[SKIP] {configurator_cls.name} missing args: {required_args}"
                    )
                    continue

                # setup configurator
                ctor_kwargs = {arg: inputs[arg] for arg in args if arg in inputs}
                self.active_configurators[configurator_cls.name.lower()] = (
                    configurator_cls(**ctor_kwargs)
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


class BaseConfigurator(ABC):
    """Base class for all CrocoDash configurators."""

    name: str
    required_for_compsets: List[str] = []  # What compsets you must have this class
    allowed_compsets: List[str] = (
        []
    )  # What compsets this class is allowed for (must have all in the compset, e.g. DROF and BGC for river nutrients)
    forbidden_compsets: List[str] = []  # What compsets you cannot have this class

    def __init__(self, **kwargs):
        self.validate_args(**kwargs)
        # Store everything directly as attributes
        for k, v in kwargs.items():
            setattr(self, k, v)

    def validate_args(self, **kwargs):
        pass

    @abstractmethod
    def configure(self):
        for p in self.params:
            p.apply()
        pass

    # @abstractmethod Will implement when we get to the shareable case config part.
    # @classmethod
    # def identify():
    #     pass

    @classmethod
    def is_required(cls, compset):
        return any(sub in compset for sub in cls.required_for_compsets)

    @classmethod
    def validate_compset_compatibility(cls, compset):
        return all(sub in compset for sub in cls.allowed_compsets) and all(
            sub not in compset for sub in cls.forbidden_compsets
        )


@register
class TidesConfigurator(BaseConfigurator):
    name = "tides"

    def __init__(
        self,
        tpxo_elevation_filepath,
        tpxo_velocity_filepath,
        tidal_constituents,
        date_range,
        boundaries,
    ):
        super().__init__(
            tpxo_elevation_filepath=tpxo_elevation_filepath,
            tpxo_velocity_filepath=tpxo_velocity_filepath,
            tidal_constituents=tidal_constituents,
            date_range=date_range,
            boundaries=boundaries,
        )
        self.params = []
        self.params.append(UserNLConfigParam("TIDES", "True"))
        self.params.append(UserNLConfigParam("TIDE_M2", "True"))
        self.params.append(UserNLConfigParam("CD_TIDES", 0.0018))
        self.params.append(UserNLConfigParam("TIDE_USE_EQ_PHASE", "True"))
        self.params.append(
            UserNLConfigParam(
                "TIDE_REF_DATE",
                f"{self.date_range[0].year}, {self.date_range[0].month}, {self.date_range[0].day}",
            )
        )
        self.params.append(UserNLConfigParam("OBC_TIDE_ADD_EQ_PHASE", "True"))
        self.params.append(
            UserNLConfigParam("OBC_TIDE_N_CONSTITUENTS", len(self.tidal_constituents))
        )
        self.params.append(
            UserNLConfigParam(
                "OBC_TIDE_CONSTITUENTS", '"' + ", ".join(self.tidal_constituents) + '"'
            )
        )
        self.params.append(
            UserNLConfigParam(
                "OBC_TIDE_REF_DATE",
                f"{self.date_range[0].year}, {self.date_range[0].month}, {self.date_range[0].day}",
            )
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
        # "001", "002", etc.

    def configure(self):
        super().configure()
        # You also need to add the files to the OBC string, which is handled in the main case unfortunately


@register
class BGCConfigurator(BaseConfigurator):
    name = "BGC"
    required_for_compsets = ["MARBL"]
    allowed_compsets = ["MARBL"]
    forbidden_compsets = []

    def __init__(
        self,
    ):
        super().__init__()
        self.params = []
        self.params.append(UserNLConfigParam("MAX_FIELDS", 200))

    def configure(self):
        super().configure()


@register
class CICEConfigurator(BaseConfigurator):
    name = "CICE"
    required_for_compsets = ["CICE"]
    allowed_compsets = ["CICE"]
    forbidden_compsets = []

    def __init__(
        self,
    ):
        super().__init__()
        self.params = []
        self.params.append(UserNLConfigParam("ice_ic", "'UNSET'", user_nl_name="cice"))
        self.params.append(
            UserNLConfigParam("ns_boundary_type", "'open'", user_nl_name="cice")
        )
        self.params.append(
            UserNLConfigParam("ew_boundary_type", "'cyclic'", user_nl_name="cice")
        )
        self.params.append(
            UserNLConfigParam("close_boundaries", ".false.", user_nl_name="cice")
        )

    def configure(self):
        super().configure()


@register
class BGCICConfigurator(BaseConfigurator):
    name = "BGCIC"
    required_for_compsets = ["MARBL"]
    allowed_compsets = ["MARBL"]
    forbidden_compsets = []

    def __init__(self, marbl_ic_filepath):
        super().__init__(marbl_ic_filepath=marbl_ic_filepath)
        self.marbl_ic_filename = Path(marbl_ic_filepath).name
        self.params = []
        self.params.append(
            UserNLConfigParam("MARBL_TRACERS_IC_FILE", self.marbl_ic_filename)
        )

    def configure(self):
        super().configure()


@register
class BGCIronForcingConfigurator(BaseConfigurator):
    name = "BGCIronForcing"
    required_for_compsets = ["MARBL"]
    allowed_compsets = ["MARBL"]
    forbidden_compsets = []

    def __init__(self, session_id, grid_name):
        super().__init__(session_id=session_id, grid_name=grid_name)
        self.feventflux_filepath = (
            f"feventflux_5gmol_{self.grid_name}_{self.session_id}.nc"
        )
        self.fesedflux_filepath = (
            f"fesedflux_total_reduce_oxic_{self.grid_name}_{self.session_id}.nc"
        )
        self.params = []
        self.params.append(
            UserNLConfigParam("MARBL_FESEDFLUX_FILE", self.fesedflux_filepath)
        )
        self.params.append(
            UserNLConfigParam("MARBL_FEVENTFLUX_FILE", self.feventflux_filepath)
        )

    def configure(self):
        super().configure()


@register
class BGCRiverNutrientsConfigurator(BaseConfigurator):
    name = "BGCRiverNutrients"
    required_for_compsets = []
    allowed_compsets = ["MARBL", "DROF"]
    forbidden_compsets = []

    def __init__(self, global_river_nutrients_filepath, session_id, grid_name):
        super().__init__(
            global_river_nutrients_filepath=global_river_nutrients_filepath,
            session_id=session_id,
            grid_name=grid_name,
        )
        self.params = []
        self.river_nutrients_nnsm_filepath = (
            f"river_nutrients_{self.grid_name}_{self.session_id}_nnsm.nc"
        )
        self.params.append(
            UserNLConfigParam("READ_RIV_FLUXES", "True", user_nl_name="mom")
        )
        self.params.append(
            UserNLConfigParam(
                "RIV_FLUX_FILE", self.river_nutrients_nnsm_filepath, user_nl_name="mom"
            )
        )

    def validate_args(self, **kwargs):
        if not kwargs["global_river_nutrients_filepath"].exists():
            raise FileNotFoundError(
                f"River Nutrients file {kwargs['global_river_nutrients_filepath']} does not exist."
            )

    def configure(self):
        super().configure()


@register
class RunoffConfigurator(BaseConfigurator):
    name = "Runoff"
    required_for_compsets = {"DROF"}
    allowed_compsets = {"DROF"}
    forbidden_compsets = []

    def __init__(
        self,
        runoff_esmf_mesh_filepath,
        grid_name,
        session_id,
        compset,
        inputdir,
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
            grid_name=grid_name,
            session_id=session_id,
            rmax=rmax,
            fold=fold,
            compset=compset,
        )
        self.params = []
        self.runoff_mapping_file_nnsm = (
            f"glofas_{self.grid_name}_{self.session_id}_nnsm.nc"
        )
        rof_grid_name = cvars["CUSTOM_ROF_GRID"].value
        mapping_file_prefix = f"{rof_grid_name}_to_{grid_name}_map"
        mapping_dir = inputdir / "mapping"
        mapping_dir.mkdir(exist_ok=False)
        if self.rmax is None:
            self.rmax, self.fold = mapping.get_suggested_smoothing_params(
                self.esmf_mesh_path
            )
        self.runoff_mapping_file_nnsm = mapping.get_smoothed_map_filepath(
            mapping_file_prefix=mapping_file_prefix,
            output_dir=mapping_dir,
            rmax=self.rmax,
            fold=self.fold,
        )
        self.params.append(
            XMLConfigParam("ROF2OCN_LIQ_RMAPNAME", self.runoff_mapping_file_nnsm)
        )
        self.params.append(
            XMLConfigParam("ROF2OCN_ICE_RMAPNAME", self.runoff_mapping_file_nnsm)
        )

    def configure(self):
        super().configure()

    def validate_args(self, **kwargs):

        if (rmax is None) != (fold is None):
            raise ValueError("Both rmax and fold must be specified together.")
        if rmax is not None:
            assert "SROF" not in self.compset, (
                "When rmax and fold are specified, "
                "the compset must include an active or data runoff model."
            )


@register
class ChlConfigurator(BaseConfigurator):
    name = "Chl"
    required_for_compsets = []
    allowed_compsets = []
    forbidden_compsets = ["MARBL"]

    def __init__(self, chl_processed_filepath, grid_name, session_id):

        super().__init__(
            chl_processed_filepath=chl_processed_filepath,
            grid_name=grid_name,
            session_id=session_id,
        )
        self.params = []
        self.regional_chl_file_path = f"seawifs-clim-1997-2010-{self.grid_name}.nc"
        self.params.append(
            UserNLConfigParam("CHL_FILE", Path(self.regional_chl_file_path), "mom")
        )
        self.params.append(UserNLConfigParam("CHL_FROM_FILE", "TRUE", "mom"))
        self.params.append(UserNLConfigParam("VAR_PEN_SW", "TRUE", "mom"))
        self.params.append(UserNLConfigParam("PEN_SW_NBANDS", 3, "mom"))

    def validate_args(self, **kwargs):
        if not kwargs["chl_processed_filepath"].exists():
            raise FileNotFoundError(
                f"Chlorophyll file {kwargs['chl_processed_filepath']} does not exist."
            )

    def configure(self):
        super().configure()


@dataclass
class ConfigParam(ABC):
    """
    Base class for a single configuration parameter applied to a CESM/MOM6 case.

    Subclasses implement how the parameter is written (user_nl or XML).
    """

    name: str
    value: str
    comment: str = None
    executed: bool = False

    @abstractmethod
    def apply(self):
        """Apply the configuration change."""
        pass


@dataclass
class UserNLConfigParam(ConfigParam):
    """
    Parameter written to a `user_nl_<component>` file (default: user_nl_mom).
    """

    user_nl_name: str = "mom"

    def apply(self):
        """Insert this parameter into the appropriate user_nl file."""
        self.executed = True
        self.param = [(self.name, self.value)]
        append_user_nl(
            self.user_nl_name,
            self.param,
            do_exec=True,
            comment=self.comment,
        )


@dataclass
class XMLConfigParam(ConfigParam):
    """
    Parameter applied via xmlchange

    XML changes are permanent and do not save previous state, so removal is unsupported.
    """

    is_non_local: bool = False

    def apply(self):
        """Apply this change using xmlchange."""
        self.executed = True
        xmlchange(
            self.name,
            str(self.value),
            is_non_local=self.is_non_local,
        )
