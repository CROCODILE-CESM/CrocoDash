from CrocoDash.forcing_configurations.base import *
from pathlib import Path
from datetime import datetime
from ProConPy.config_var import ConfigVar, cvars
from mom6_forge import mapping
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import ForcingProduct


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

    def get_output_filepaths(self, ocn_ice_directory):
        # Search directory for tu_* and tz_* files
        ocn_ice_directory = Path(ocn_ice_directory)

        if not ocn_ice_directory.exists():
            raise FileNotFoundError(f"{ocn_ice_directory} does not exist")

        return [
            str(p.resolve())
            for pattern in ("tu_*", "tz_*")
            for p in ocn_ice_directory.glob(pattern)
            if p.is_file()
        ]


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
            is_file=True,
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
            is_file=True,
        ),
        UserNLConfigParam(
            "MARBL_FEVENTFLUX_FILE",
            comment="MARBL event iron flux file",
            user_nl_name="mom",
            is_file=True,
        ),
        UserNLConfigParam(
            "MARBL_FESEDFLUXRED_FILE",
            comment="MARBL sediment iron flux (reduced) file",
            user_nl_name="mom",
        ),
    ]

    def __init__(self, case_session_id, case_grid_name):
        super().__init__(case_session_id=case_session_id, case_grid_name=case_grid_name)

    def configure(self):
        feventflux_filepath = f"feventflux_5gmol_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}.nc"
        fesedflux_filepath = f"fesedflux_total_reduce_oxic_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}.nc"
        fesedfluxred_filepath = f"fesedfluxred_{self.get_input_param('case_grid_name')}_{self.get_input_param('case_session_id')}.nc"
        self.set_output_param("MARBL_FESEDFLUX_FILE", fesedflux_filepath)
        self.set_output_param("MARBL_FEVENTFLUX_FILE", feventflux_filepath)
        self.set_output_param("MARBL_FESEDFLUXRED_FILE", fesedfluxred_filepath)
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
            is_file=True,
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
            "ROF2OCN_LIQ_RMAPNAME",
            comment="Runoff to ocean liquid runoff mapping file",
            is_file=True,
        ),
        XMLConfigParam(
            "ROF2OCN_ICE_RMAPNAME",
            comment="Runoff to ocean ice runoff mapping file",
            is_file=True,
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
            if rof_esmf_mesh_filepath is None:
                rof_esmf_mesh_filepath = case_cime.get_mesh_path(
                    "rof", cvars["CUSTOM_ROF_GRID"].value
                )
            if rof_grid_name is None:
                rof_grid_name = cvars["CUSTOM_ROF_GRID"].value
            super().__init__(
                case_grid_name=case_grid_name,
                case_session_id=case_session_id,
                case_inputdir=case_inputdir,
                rmax=rmax,
                fold=fold,
                case_esmf_mesh_path=case_esmf_mesh_path,
                case_compset_lname=case_compset_lname,
                case_is_non_local=case_is_non_local,
                rof_esmf_mesh_filepath=rof_esmf_mesh_filepath,
                rof_grid_name=rof_grid_name,
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

    def get_output_filepaths(self, ocn_ice_directory):
        # Return just the xml file paths (Can be either direct path or in ocn_ice as well)
        ocn_ice_directory = Path(ocn_ice_directory)

        params = [
            self.get_output_param("ROF2OCN_LIQ_RMAPNAME"),
            self.get_output_param("ROF2OCN_ICE_RMAPNAME"),
        ]

        valid_paths = []
        for p in params:
            if not p:
                continue
            p_path = Path(p)
            if not p_path.exists():
                p_path = ocn_ice_directory / p_path.name
            if p_path.exists():
                valid_paths.append(str(p_path.resolve()))

        return valid_paths


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
            "CHL_FILE",
            comment="Chlorophyll data file",
            user_nl_name="mom",
            is_file=True,
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


@register
class ConditionsConfigurator(BaseConfigurator):
    """Initial condition + open boundary condition (OBC) setup for MOM6.

    Always active for regional MOM6 cases. Builds the `user_nl_mom` initial
    condition and OBC_SEGMENT_* parameters, and the derived values consumed by
    extract_forcings (dates, forcing product metadata, boundary numbering).
    """

    name = "conditions"
    required_for_compsets = ["MOM6"]

    _DATE_FORMAT = "%Y%m%d"

    # Static output params that don't vary by boundary count.
    _IC_PARAM_NAMES = {
        "INIT_LAYERS_FROM_Z_FILE",
        "Z_INIT_ALE_REMAPPING",
        "TEMP_SALT_INIT_VERTICAL_REMAP_ONLY",
        "DEPRESS_INITIAL_SURFACE",
        "VELOCITY_CONFIG",
        "TEMP_SALT_Z_INIT_FILE",
        "SURFACE_HEIGHT_IC_FILE",
        "VELOCITY_FILE",
        "Z_INIT_FILE_PTEMP_VAR",
        "Z_INIT_FILE_SALT_VAR",
        "SURFACE_HEIGHT_IC_VAR",
        "U_IC_VAR",
        "V_IC_VAR",
    }

    input_params = [
        InputValueParam("start_date", comment="Forcing start date"),
        InputValueParam("end_date", comment="Forcing end date"),
        InputValueParam("boundaries", comment="List of open boundaries to process"),
        InputValueParam("product_name", comment="Forcing data product name"),
        InputValueParam(
            "function_name", comment="Download function name for the product"
        ),
        InputValueParam(
            "compset", comment="Compset lname, used to detect MARBL tracers"
        ),
    ]

    output_params = [
        # Initial conditions
        UserNLConfigParam("INIT_LAYERS_FROM_Z_FILE", comment="Initial conditions"),
        UserNLConfigParam("Z_INIT_ALE_REMAPPING", comment="Initial conditions"),
        UserNLConfigParam(
            "TEMP_SALT_INIT_VERTICAL_REMAP_ONLY", comment="Initial conditions"
        ),
        UserNLConfigParam("DEPRESS_INITIAL_SURFACE", comment="Initial conditions"),
        UserNLConfigParam("VELOCITY_CONFIG", comment="Initial conditions"),
        UserNLConfigParam("TEMP_SALT_Z_INIT_FILE", comment="Initial conditions"),
        UserNLConfigParam("SURFACE_HEIGHT_IC_FILE", comment="Initial conditions"),
        UserNLConfigParam("VELOCITY_FILE", comment="Initial conditions"),
        UserNLConfigParam("Z_INIT_FILE_PTEMP_VAR", comment="Initial conditions"),
        UserNLConfigParam("Z_INIT_FILE_SALT_VAR", comment="Initial conditions"),
        UserNLConfigParam("SURFACE_HEIGHT_IC_VAR", comment="Initial conditions"),
        UserNLConfigParam("U_IC_VAR", comment="Initial conditions"),
        UserNLConfigParam("V_IC_VAR", comment="Initial conditions"),
        # Open boundary conditions (static; per-boundary params are added dynamically)
        UserNLConfigParam("OBC_NUMBER_OF_SEGMENTS", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_FREESLIP_VORTICITY", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_FREESLIP_STRAIN", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_COMPUTED_VORTICITY", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_COMPUTED_STRAIN", comment="Open boundary conditions"),
        UserNLConfigParam("OBC_ZERO_BIHARMONIC", comment="Open boundary conditions"),
        UserNLConfigParam(
            "OBC_TRACER_RESERVOIR_LENGTH_SCALE_OUT", comment="Open boundary conditions"
        ),
        UserNLConfigParam(
            "OBC_TRACER_RESERVOIR_LENGTH_SCALE_IN", comment="Open boundary conditions"
        ),
        UserNLConfigParam("BRUSHCUTTER_MODE", comment="Open boundary conditions"),
        # Derived, config.json-only values consumed by extract_forcings/driver.py.
        # No case-side effect (see ConfigOutputParam).
        ConfigOutputParam(
            "date_format", comment="strftime format used for dates in config.json"
        ),
        ConfigOutputParam("start_date", comment="Forcing start date"),
        ConfigOutputParam("end_date", comment="Forcing end date"),
        ConfigOutputParam("information", comment="Product variable-name metadata"),
        ConfigOutputParam("step", comment="Chunk size (days) for forcing extraction"),
        ConfigOutputParam(
            "boundary_number_conversion",
            comment="Boundary name -> MOM6 segment number",
        ),
        ConfigOutputParam(
            "preview", comment="Whether extract_forcings should preview only"
        ),
    ]

    def __init__(
        self,
        boundaries,
        product_name,
        function_name,
        compset,
        date_range=None,
        start_date=None,
        end_date=None,
    ):
        if date_range is not None:
            start_date = date_range[0].strftime(self._DATE_FORMAT)
            end_date = date_range[1].strftime(self._DATE_FORMAT)
        super().__init__(
            start_date=start_date,
            end_date=end_date,
            boundaries=boundaries,
            product_name=product_name,
            function_name=function_name,
            compset=compset,
        )

    def validate_args(self, **kwargs):
        super().validate_args(**kwargs)

        boundaries = kwargs["boundaries"]
        if not isinstance(boundaries, list):
            raise TypeError("boundaries must be a list of strings.")
        if not all(isinstance(boundary, str) for boundary in boundaries):
            raise TypeError("boundaries must be a list of strings.")

        ProductRegistry.load()
        product_name = kwargs["product_name"]
        if not (
            ProductRegistry.product_exists(product_name)
            and ProductRegistry.product_is_of_type(product_name, ForcingProduct)
        ):
            raise ValueError("Product / Data Path is not supported quite yet")

    @staticmethod
    def _segment_index(boundaries, boundary):
        """Map a boundary name to its 1-based MOM6 segment number (or the inverse)."""
        direction_dir = {b: i + 1 for i, b in enumerate(boundaries)}
        direction_dir_inv = {v: k for k, v in direction_dir.items()}
        merged = {**direction_dir, **direction_dir_inv}
        try:
            return merged[boundary]
        except KeyError:
            raise ValueError(
                "Invalid direction or segment number for MOM6 rectangular orientation"
            )

    def configure(self):
        start_date = self.get_input_param("start_date")
        end_date = self.get_input_param("end_date")
        boundaries = self.get_input_param("boundaries")
        product_name = self.get_input_param("product_name").lower()
        compset = self.get_input_param("compset")
        product = ProductRegistry.get_product(product_name)

        # ---- derived, config.json-only values ----
        self.set_output_param("date_format", self._DATE_FORMAT)
        self.set_output_param("start_date", start_date)
        self.set_output_param("end_date", end_date)
        self.set_output_param(
            "information",
            product.write_metadata(include_marbl_tracers="%MARBL" in compset),
        )
        start_dt = datetime.strptime(start_date, self._DATE_FORMAT)
        end_dt = datetime.strptime(end_date, self._DATE_FORMAT)
        self.set_output_param("step", (end_dt - start_dt).days + 1)
        self.set_output_param(
            "boundary_number_conversion",
            {b: i + 1 for i, b in enumerate(boundaries)},
        )
        self.set_output_param("preview", False)

        # ---- static initial condition / OBC params ----
        self.set_output_param("INIT_LAYERS_FROM_Z_FILE", "True")
        self.set_output_param("Z_INIT_ALE_REMAPPING", True)
        self.set_output_param("TEMP_SALT_INIT_VERTICAL_REMAP_ONLY", True)
        self.set_output_param("DEPRESS_INITIAL_SURFACE", True)
        self.set_output_param("VELOCITY_CONFIG", "file")
        self.set_output_param("TEMP_SALT_Z_INIT_FILE", "init_tracers.nc")
        self.set_output_param("SURFACE_HEIGHT_IC_FILE", "init_eta.nc")
        self.set_output_param("VELOCITY_FILE", "init_vel.nc")
        self.set_output_param("Z_INIT_FILE_PTEMP_VAR", "temp")
        self.set_output_param("Z_INIT_FILE_SALT_VAR", "salt")
        self.set_output_param("SURFACE_HEIGHT_IC_VAR", "eta_t")
        self.set_output_param("U_IC_VAR", "u")
        self.set_output_param("V_IC_VAR", "v")

        self.set_output_param("OBC_NUMBER_OF_SEGMENTS", len(boundaries))
        self.set_output_param("OBC_FREESLIP_VORTICITY", "False")
        self.set_output_param("OBC_FREESLIP_STRAIN", "False")
        self.set_output_param("OBC_COMPUTED_VORTICITY", "True")
        self.set_output_param("OBC_COMPUTED_STRAIN", "True")
        self.set_output_param("OBC_ZERO_BIHARMONIC", "True")
        self.set_output_param("OBC_TRACER_RESERVOIR_LENGTH_SCALE_OUT", "3.0E+04")
        self.set_output_param("OBC_TRACER_RESERVOIR_LENGTH_SCALE_IN", "3000.0")
        self.set_output_param("BRUSHCUTTER_MODE", "True")

        # ---- dynamic, per-boundary OBC params ----
        dynamic_params = []
        for seg in boundaries:
            seg_ix = str(self._segment_index(boundaries, seg)).zfill(3)
            seg_id = "OBC_SEGMENT_" + seg_ix

            if seg == "south":
                index_str = '"J=0,I=0:N'
            elif seg == "north":
                index_str = '"J=N,I=N:0'
            elif seg == "west":
                index_str = '"I=0,J=N:0'
            elif seg == "east":
                index_str = '"I=N,J=0:N'
            else:
                raise ValueError(f"Unknown segment {seg_id}")

            position_param = UserNLConfigParam(
                seg_id, comment="Open boundary conditions"
            )
            position_param.set_item(
                index_str + ',FLATHER,ORLANSKI,NUDGED,ORLANSKI_TAN,NUDGED_TAN"'
            )
            dynamic_params.append(position_param)

            nudging_param = UserNLConfigParam(
                seg_id + "_VELOCITY_NUDGING_TIMESCALES",
                comment="Open boundary conditions",
            )
            nudging_param.set_item("0.3, 360.0")
            dynamic_params.append(nudging_param)

            standard_data_str = (
                f'"U=file:forcing_obc_segment_{seg_ix}.nc(u),'
                f"V=file:forcing_obc_segment_{seg_ix}.nc(v),"
                f"SSH=file:forcing_obc_segment_{seg_ix}.nc(eta),"
                f"TEMP=file:forcing_obc_segment_{seg_ix}.nc(temp),"
                f"SALT=file:forcing_obc_segment_{seg_ix}.nc(salt)"
            )

            if self.registry and self.registry.is_active("bgc"):
                for tracer_mom6_name, source_var in product.marbl_var_names.items():
                    tracer_param = UserNLConfigParam(
                        f"OBC_DATA_{tracer_mom6_name}",
                        comment="Open boundary conditions",
                    )
                    tracer_param.set_item(
                        f"{tracer_mom6_name}_obc_segment.nc({source_var})"
                    )
                    dynamic_params.append(tracer_param)

            data_str = standard_data_str
            if self.registry and self.registry.is_active("tides"):
                data_str += self.registry.active_configurators["tides"].tidal_data_str(
                    seg_ix
                )
            data_str += '"'

            data_param = UserNLConfigParam(
                seg_id + "_DATA", comment="Open boundary conditions"
            )
            data_param.set_item(data_str)
            dynamic_params.append(data_param)

        self.output_params = self.output_params + dynamic_params

        # ---- apply: batch into exactly 2 append_user_nl calls (preserves today's
        # "Initial conditions" / "Open boundary conditions" banner formatting) ----
        ic_params, obc_params = [], []
        for param in self.output_params:
            if not isinstance(param, UserNLConfigParam):
                continue
            (ic_params if param.name in self._IC_PARAM_NAMES else obc_params).append(
                (param.name, param.value)
            )

        append_user_nl("mom", ic_params, do_exec=True, comment="Initial conditions")
        append_user_nl(
            "mom",
            obc_params,
            do_exec=True,
            comment="Open boundary conditions",
            log_title=False,
        )
        for param in self.output_params:
            if isinstance(param, UserNLConfigParam):
                param.executed = True

    @classmethod
    def deserialize(cls, data):
        """Reconstruct dynamic per-boundary output params alongside the static ones."""
        obj = super().deserialize(data)
        boundaries = obj.get_input_param("boundaries")
        for seg in boundaries:
            seg_ix = str(cls._segment_index(boundaries, seg)).zfill(3)
            for suffix in ("", "_VELOCITY_NUDGING_TIMESCALES", "_DATA"):
                name = f"OBC_SEGMENT_{seg_ix}{suffix}"
                if name in data["outputs"]:
                    param = UserNLConfigParam(name, comment="Open boundary conditions")
                    param.set_item(data["outputs"][name])
                    obj.output_params.append(param)
        return obj
