from CrocoDash.forcing_configurations.base import *
from pathlib import Path
from ProConPy.config_var import ConfigVar, cvars
from mom6_bathy import mapping


def register(cls):
    ForcingConfigRegistry.register(cls)
    return cls


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
            "start_date",
            comment="start_date",
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
        boundaries,
        date_range=None,
        start_date=None,
    ):
        if date_range is not None:
            # Set the input params
            super().__init__(
                tpxo_elevation_filepath=tpxo_elevation_filepath,
                tpxo_velocity_filepath=tpxo_velocity_filepath,
                tidal_constituents=tidal_constituents,
                start_date=date_range[0].strftime("%Y, %m, %d"),
                boundaries=boundaries,
            )
        else:
            super().__init__(
                tpxo_elevation_filepath=tpxo_elevation_filepath,
                tpxo_velocity_filepath=tpxo_velocity_filepath,
                tidal_constituents=tidal_constituents,
                start_date=start_date,
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
        self.set_output_param(
            "TIDE_REF_DATE",
            self.get_input_param("start_date"),
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
            self.get_input_param("start_date"),
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

    def configure(self):
        self.set_output_param(
            "MARBL_TRACERS_IC_FILE",
            Path(self.get_input_param("marbl_ic_filepath")).name,
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
        InputValueParam("case_grid_name", comment="Case grid name"),
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam("case_compset_lname", comment="Case compset"),
        InputValueParam("case_inputdir", comment="Case input directory"),
        InputValueParam(
            "rmax", comment="Smoothing radius (in meters) for runoff mapping generation"
        ),
        InputValueParam(
            "rof_grid_name", comment="Name of the runoff grid used in the case"
        ),
        InputValueParam("case_is_non_local", comment="Case is non-local"),
        InputValueParam(
            "fold", comment="Smoothing fold parameter for runoff mapping generation"
        ),
        InputFileParam("rof_esmf_mesh_filepath", comment="Runoff ESMF Mesh File Path"),
        InputFileParam("case_esmf_mesh_path", comment="Ocean ESMF Mesh File Path"),
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
        case_grid_name,
        case_session_id,
        case_compset_lname,
        case_inputdir,
        case_is_non_local,
        case_esmf_mesh_path,
        case_cime=None,
        rmax=None,
        fold=None,
        rof_grid_name=None,
        rof_esmf_mesh_filepath=None,
    ):
        """
        rmax : float, optional
            If passed, specifies the smoothing radius (in meters) for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        fold : float, optional
            If passed, specifies the smoothing fold parameter for runoff mapping generation.
            If not provided, a suggested value based on the ocean grid will be used.
        """
        if case_cime is not None:

            super().__init__(
                case_grid_name=case_grid_name,
                case_session_id=case_session_id,
                case_inputdir=case_inputdir,
                rmax=rmax,
                fold=fold,
                case_esmf_mesh_path=case_esmf_mesh_path,
                case_compset_lname=case_compset_lname,
                case_is_non_local=case_is_non_local,
                rof_esmf_mesh_filepath=case_cime.get_mesh_path(
                    "rof", cvars["CUSTOM_ROF_GRID"].value
                ),
                rof_grid_name=cvars["CUSTOM_ROF_GRID"].value,
            )
        else:
            super().__init__(
                case_grid_name=case_grid_name,
                case_session_id=case_session_id,
                case_inputdir=case_inputdir,
                rmax=rmax,
                fold=fold,
                case_compset_lname=case_compset_lname,
                case_esmf_mesh_path=case_esmf_mesh_path,
                case_is_non_local=case_is_non_local,
                rof_esmf_mesh_filepath=rof_esmf_mesh_filepath,
                rof_grid_name=rof_grid_name,
            )

    def configure(self):
        runoff_mapping_file_nnsm = f"glofas_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}_nnsm.nc"
        rof_case_grid_name = self.get_input_param("rof_grid_name")
        mapping_file_prefix = (
            f"{rof_case_grid_name}_to_{self.get_input_param('case_grid_name')}_map"
        )
        mapping_dir = Path(self.get_input_param("case_inputdir")) / "mapping"

        if self.get_input_param("rmax") is None:
            rmax, fold = mapping.get_suggested_smoothing_params(
                self.get_input_param("rof_esmf_mesh_filepath")
            )
            self.set_input_param("rmax", rmax)
            self.set_input_param("fold", fold)
        self.runoff_mapping_file_nnsm = mapping.get_smoothed_map_filepath(
            mapping_file_prefix=mapping_file_prefix,
            output_dir=mapping_dir,
            rmax=self.get_input_param("rmax"),
            fold=self.get_input_param("fold"),
        )
        self.set_output_param(
            "ROF2OCN_LIQ_RMAPNAME",
            self.runoff_mapping_file_nnsm,
            is_non_local=self.get_input_param("case_is_non_local"),
        )
        self.set_output_param(
            "ROF2OCN_ICE_RMAPNAME",
            self.runoff_mapping_file_nnsm,
            is_non_local=self.get_input_param("case_is_non_local"),
        )
        super().configure()

    def validate_args(self, **kwargs):

        if (kwargs["rmax"] is None) != (kwargs["fold"] is None):
            raise ValueError("Both rmax and fold must be specified together.")
        if kwargs["rmax"] is not None:
            assert "SROF" not in kwargs["case_compset_lname"], (
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
