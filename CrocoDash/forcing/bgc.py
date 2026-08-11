import shutil
from pathlib import Path

import numpy as np
import xarray as xr
import cftime
import xesmf as xe
from netCDF4 import default_fillvals

from CrocoDash.forcing.base import *


@register
class BGCConfigurator(BaseConfigurator):
    """Toggles the MARBL-tracer namelist default -- no forcing data of its
    own to extract. BGCIC/BGCIronForcing/BGCRiverNutrients below are the
    configurators that actually produce BGC forcing files."""

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
    process_components = {"bgcic": "process"}
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

    def process(self, ctx):
        """Copy the MARBL initial condition file into place."""
        shutil.copy(
            self.get_input_param("marbl_ic_filepath"),
            ctx.output_path / self.get_output_param("MARBL_TRACERS_IC_FILE"),
        )


@register
class BGCIronForcingConfigurator(BaseConfigurator):
    name = "BGCIronForcing"
    process_components = {"bgcironforcing": "process"}
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

    def process(self, ctx):
        """Create dummy iron forcing files for MARBL."""
        nx, ny = ctx.grid.nx, ctx.grid.ny
        depth = 103
        depth_edges = depth + 1
        dz = 6000.0 / depth
        DEPTH = np.linspace(dz / 2, 6000.0 - dz / 2, depth)
        DEPTH_EDGES = np.linspace(0, 6000, depth_edges)
        ds = xr.Dataset(
            {
                "DEPTH": (["DEPTH"], DEPTH),
                "DEPTH_EDGES": (["DEPTH_EDGES"], DEPTH_EDGES),
                "FESEDFLUXIN": (
                    ["DEPTH", "ny", "nx"],
                    np.zeros((depth, ny, nx), dtype=np.float32),
                ),
                "KMT": (["ny", "nx"], np.zeros((ny, nx), dtype=np.int32)),
                "TAREA": (["ny", "nx"], np.zeros((ny, nx), dtype=np.float64)),
            }
        )
        # Assign attributes
        ds["DEPTH"].attrs = {"units": "m", "edges": "DEPTH_EDGES"}
        ds["DEPTH_EDGES"].attrs = {"units": "m"}
        ds["FESEDFLUXIN"].attrs = {
            "_FillValue": 1.0e20,
            "units": "micromol/m^2/d",
            "long_name": "Fe sediment flux (total)",
        }
        ds["TAREA"].attrs = {"units": "m^2"}
        # Add global attributes
        ds.attrs = {
            "history": "Created with xarray (this file is empty)",
        }
        ds.to_netcdf(
            ctx.inputdir / "ocnice" / self.get_output_param("MARBL_FESEDFLUX_FILE")
        )
        ds.to_netcdf(
            ctx.inputdir / "ocnice" / self.get_output_param("MARBL_FEVENTFLUX_FILE")
        )
        ds.to_netcdf(
            ctx.inputdir / "ocnice" / self.get_output_param("MARBL_FESEDFLUXRED_FILE")
        )


@register
class BGCRiverNutrientsConfigurator(BaseConfigurator):
    name = "BGCRiverNutrients"
    process_components = {"bgcrivernutrients": "process"}
    allowed_compsets = ["MARBL", "DROF"]
    input_params = [
        InputFileParam(
            "global_river_nutrients_filepath",
            comment="NetCDF file containing global river nutrients data",
        ),
        InputValueParam("case_session_id", comment="Case session identifier"),
        InputValueParam("case_grid_name", comment="Case grid name"),
        InputValueParam(
            "cf_calendar", comment="CF calendar for the river nutrients output file"
        ),
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
        self,
        global_river_nutrients_filepath,
        case_session_id,
        case_grid_name,
        case_forcing_product=None,
        cf_calendar=None,
    ):
        if case_forcing_product is not None and cf_calendar is None:
            cf_calendar = case_forcing_product.cf_calendar
        super().__init__(
            global_river_nutrients_filepath=global_river_nutrients_filepath,
            case_session_id=case_session_id,
            case_grid_name=case_grid_name,
            cf_calendar=cf_calendar,
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

    def process(self, ctx):
        """Regrid global river nutrients onto the ocean grid via the runoff
        mapping file -- requires RunoffConfigurator's process step to have
        already produced that mapping file (see forcing/base.py's
        _PROCESS_ORDER_OVERRIDES in driver.py)."""
        mapping_file = ctx.config["runoff"]["outputs"]["ROF2OCN_LIQ_RMAPNAME"]
        river_nutrients_nnsm_filepath = ctx.output_path / self.get_output_param(
            "RIV_FLUX_FILE"
        )
        calendar = self.get_input_param("cf_calendar") or "noleap"

        # Open Dataset & Create Regridder
        global_river_nutrients = xr.open_dataset(
            self.get_input_param("global_river_nutrients_filepath")
        )

        # Convert to degrees east
        global_river_nutrients = global_river_nutrients.assign_coords(
            lon=((global_river_nutrients.lon + 360) % 360)
        )
        global_river_nutrients["LON"] = (global_river_nutrients["LON"] + 360) % 360

        # Rearrange to same shape as the GLOFAS file (GLOFAS goes 0 -> 360, River Nutrients goes -180 to 180)
        global_river_nutrients = global_river_nutrients.sortby("lon")
        grid_t_points = xr.Dataset()
        grid_t_points["lon"] = ctx.grid.tlon
        grid_t_points["lat"] = ctx.grid.tlat
        glofas_grid_t_points = xr.Dataset()
        glofas_grid_t_points["lon"] = global_river_nutrients.lon
        glofas_grid_t_points["lon"].attrs["units"] = "degrees"
        glofas_grid_t_points["lat"] = global_river_nutrients.lat
        glofas_grid_t_points["lat"].attrs["units"] = "degrees"
        print("Creating regridder for river nutrients...")
        regridder = xe.Regridder(
            glofas_grid_t_points,
            grid_t_points,
            method="bilinear",
            reuse_weights=True,
            filename=mapping_file,
        )

        # Open Dataset & Unit Convert

        vars = [
            "din_riv_flux",
            "dip_riv_flux",
            "don_riv_flux",
            "don_riv_flux",
            "dsi_riv_flux",
            "dsi_riv_flux",
            "dic_riv_flux",
            "alk_riv_flux",
            "doc_riv_flux",
        ]
        conversion_factor = 0.01  # nmol/cm^2/s -> mmol/m^2/s
        for v in vars:
            global_river_nutrients[v] = global_river_nutrients[v] * conversion_factor
            global_river_nutrients[v].attrs["units"] = "mmol/cm^2/s"

        print("Regridding river nutrients...")
        river_nutrients_remapped = regridder(global_river_nutrients)
        # Write out
        print("Writing out river nutrients...")
        # new time value as cftime - Required
        new_time_val = cftime.datetime(1900, 1, 1, 0, 0, 0, calendar=calendar)

        # select only variables that have 'time' as a dimension
        vars_with_time = [
            v
            for v in river_nutrients_remapped.data_vars
            if "time" in river_nutrients_remapped[v].dims
        ]

        # create new slice only for these
        ref_slice_new = (
            river_nutrients_remapped[vars_with_time]
            .isel(time=0)
            .expand_dims("time")
            .copy()
        )
        ref_slice_new = ref_slice_new.assign_coords(time=[new_time_val])

        # concatenate along time
        river_nutrients_remapped_time_added = xr.concat(
            [ref_slice_new, river_nutrients_remapped[vars_with_time]], dim="time"
        )

        # assign the new time coordinate
        river_nutrients_remapped_time_added = (
            river_nutrients_remapped_time_added.assign_coords(
                time=np.concatenate(
                    [[new_time_val], river_nutrients_remapped["time"].values]
                )
            )
        )

        # combine back with variables that don’t have time
        vars_without_time = [
            v
            for v in river_nutrients_remapped.data_vars
            if "time" not in river_nutrients_remapped[v].dims
        ]
        for v in vars_without_time:
            river_nutrients_remapped_time_added[v] = river_nutrients_remapped[v]

        # add units to all data vars
        for var in vars:
            river_nutrients_remapped_time_added[var].attrs["units"] = "mmol/cm^2/s"
        time_units = "days since 0001-01-01 00:00:00"
        time_calendar = calendar
        time_num = cftime.date2num(
            river_nutrients_remapped_time_added["time"].values,
            units=time_units,
            calendar=time_calendar,
        )

        # replace time coordinate with float64 numeric values
        river_nutrients_remapped_cleaned = (
            river_nutrients_remapped_time_added.assign_coords(
                time=("time", np.array(time_num, dtype="float64"))
            )
        )

        # Drop useless vars/broken ones
        river_nutrients_remapped_cleaned = river_nutrients_remapped_cleaned.drop_vars(
            ["LAT", "LON", "xc", "xv", "yc", "yv", "area"]
        )
        river_nutrients_remapped_cleaned["lat"] = grid_t_points["lat"]
        river_nutrients_remapped_cleaned["lon"] = grid_t_points["lon"]

        # set CF-compliant attrs
        river_nutrients_remapped_cleaned["time"].attrs.update(
            {
                "units": time_units,
                "calendar": calendar,
                "long_name": "time",
            }
        )

        # encoding only for data vars
        encoding = {
            var: {"_FillValue": default_fillvals["f8"]}
            for var in river_nutrients_remapped_cleaned.data_vars
        }
        river_nutrients_remapped_cleaned["nx"] = river_nutrients_remapped_cleaned.nx
        river_nutrients_remapped_cleaned["nx"].attrs["cartesian_axis"] = "X"
        river_nutrients_remapped_cleaned["ny"] = river_nutrients_remapped_cleaned.ny
        river_nutrients_remapped_cleaned["ny"].attrs["cartesian_axis"] = "Y"

        river_nutrients_remapped_cleaned.to_netcdf(
            river_nutrients_nnsm_filepath,
            encoding=encoding,
            unlimited_dims=["time"],
        )
