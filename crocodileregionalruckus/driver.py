import logging

driver_logger = logging.getLogger(__name__)
import datetime as dt
import xarray as xr
import json
from . import grid_gen
from . import boundary_conditions
from .regional_casegen import cesm_tools as rcg_ct
import os
from pathlib import Path
import subprocess
from .rm6_dir import regional_mom6 as rm6


class crr_driver:
    """Who needs documentation?"""

    def __init__(
        self,
        longitude_extent=None,
        latitude_extent=None,
        date_range=None,
        resolution=None,
        number_vertical_layers=None,
        layer_thickness_ratio=None,
        depth=None,
        mom_run_dir=None,
        mom_input_dir=None,
        toolpath_dir=None,
        grid_type="even_spacing",
        repeat_year_forcing=False,
        minimum_depth=4,
        tidal_constituents=["M2"],
        name=None,
    ):
        # ## Set up the experiment with no config file
        ## in case list was given, convert to tuples
        self.grid_gen = grid_gen.GridGen()
        self.boundary_conditions = boundary_conditions.BoundaryConditions()
        self.rcg = rcg_ct.RegionalCaseGen()
        self.og_mom6 = rm6.experiment.create_empty(
            latitude_extent=latitude_extent,
            longitude_extent=longitude_extent,
            depth=depth,
            resolution=resolution,
            number_vertical_layers=number_vertical_layers,
            layer_thickness_ratio=layer_thickness_ratio,
            date_range=date_range,
            mom_run_dir=mom_run_dir,
            mom_input_dir=mom_input_dir,
            toolpath_dir="",
            grid_type=grid_type,
            repeat_year_forcing=repeat_year_forcing,
            minimum_depth=minimum_depth,
            tidal_constituents=tidal_constituents,
            name=name,
        )


        ## To ensure that the hgrid and vgrid are created in the original MOM6 expt, this is a hacky way to do it. Will be moved to grid gen when ready,
        if self.og_mom6.latitude_extent is not None and self.og_mom6.longitude_extent is not None and self.og_mom6.grid_type is not None:
            self.og_mom6.hgrid = self.og_mom6._make_hgrid()
        if self.og_mom6.layer_thickness_ratio is not None and self.og_mom6.depth is not None and self.og_mom6.number_vertical_layers is not None:
            self.og_mom6.vgrid = self.og_mom6._make_vgrid()
        self.expt_name = name
        self.tidal_constituents = tidal_constituents
        self.repeat_year_forcing = repeat_year_forcing
        self.grid_type = grid_type
        self.toolpath_dir = toolpath_dir
        self.mom_run_dir = mom_run_dir
        self.mom_input_dir = mom_input_dir
        self.min_depth = minimum_depth
        self.depth = depth
        self.layer_thickness_ratio = layer_thickness_ratio
        self.number_vertical_layers = number_vertical_layers
        self.resolution = resolution
        self.latitude_extent = latitude_extent
        self.longitude_extent = longitude_extent
        self.ocean_mask = None
        self.layout = None

        if date_range is not None:
            try:
                self.date_range = [
                    dt.datetime.strptime(date_range[0], "%Y-%m-%d %H:%M:%S"),
                    dt.datetime.strptime(date_range[1], "%Y-%m-%d %H:%M:%S"),
                ]
            except:
                driver_logger.warning(
                    "Date range not formatted correctly. Please use 'YYYY-MM-DD HH:MM:SS' format in a list or tuple of two."
                )

    def check_grid_generation(self):
        """
        This function should call grid_gen check_grid function and return some information about the grid.
        """
        raise ValueError("Not implemented yet")
    @classmethod
    def load_experiment(self, config_file_path):
        print("Reading from config file....")
        with open(config_file_path, "r") as f:
            config_dict = json.load(f)

        print("Creating Empty Driver Object....")
        expt = self()

        print("Setting Default Variables.....")
        expt.expt_name = config_dict["name"]
        try:
            expt.longitude_extent = tuple(config_dict["longitude_extent"])
            expt.latitude_extent = tuple(config_dict["latitude_extent"])
        except:
            expt.longitude_extent = None
            expt.latitude_extent = None
        try:
            expt.date_range = config_dict["date_range"]
            expt.date_range[0] = dt.datetime.strptime(expt.date_range[0], "%Y-%m-%d")
            expt.date_range[1] = dt.datetime.strptime(expt.date_range[1], "%Y-%m-%d")
        except:
            expt.date_range = None
        expt.mom_run_dir = Path(config_dict["run_dir"])
        expt.mom_input_dir = Path(config_dict["input_dir"])
        expt.toolpath_dir = Path(config_dict["toolpath_dir"])
        expt.resolution = config_dict["resolution"]
        expt.number_vertical_layers = config_dict["number_vertical_layers"]
        expt.layer_thickness_ratio = config_dict["layer_thickness_ratio"]
        expt.depth = config_dict["depth"]
        expt.grid_type = config_dict["grid_type"]
        expt.repeat_year_forcing = config_dict["repeat_year_forcing"]
        expt.ocean_mask = None
        expt.layout = None
        expt.min_depth = config_dict["min_depth"]
        expt.tidal_constituents = config_dict["tidal_constituents"]

        print("Checking for hgrid and vgrid....")
        if os.path.exists(config_dict["hgrid"]):
            print("Found")
            expt.hgrid = xr.open_dataset(config_dict["hgrid"])
        else:
            print("Hgrid not found, call _make_hgrid when you're ready.")
            expt.hgrid = None
        if os.path.exists(config_dict["vgrid"]):
            print("Found")
            expt.vgrid = xr.open_dataset(config_dict["vgrid"])
        else:
            print("Vgrid not found, call _make_vgrid when ready")
            expt.vgrid = None

        print("Checking for bathymetry...")
        if config_dict["bathymetry"] is not None and os.path.exists(
            config_dict["bathymetry"]
        ):
            print("Found")
            expt.bathymetry = xr.open_dataset(config_dict["bathymetry"])
        else:
            print(
                "Bathymetry not found. Please provide bathymetry, or call setup_bathymetry method to set up bathymetry."
            )

        print("Checking for ocean state files....")
        found = True
        for path in config_dict["ocean_state"]:
            if not os.path.exists(path):
                found = False
                print(
                    "At least one ocean state file not found. Please provide ocean state files, or call setup_ocean_state_boundaries method to set up ocean state."
                )
                break
        if found:
            print("Found")
        found = True
        print("Checking for initial condition files....")
        for path in config_dict["initial_conditions"]:
            if not os.path.exists(path):
                found = False
                print(
                    "At least one initial condition file not found. Please provide initial condition files, or call setup_initial_condition method to set up initial condition."
                )
                break
        if found:
            print("Found")
        found = True
        print("Checking for tides files....")
        for path in config_dict["tides"]:
            if not os.path.exists(path):
                found = False
                print(
                    "At least one tides file not found. If you would like tides, call setup_tides_boundaries method to set up tides"
                )
                break
        if found:
            print("Found")
        found = True

        return expt

    def setup_directories(self, mom_run_dir, mom_input_dir):
        self.mom_run_dir = Path(mom_run_dir)
        self.mom_input_dir = Path(mom_input_dir)
        self.mom_run_dir.mkdir(exist_ok=True)
        self.mom_input_dir.mkdir(exist_ok=True)
        (self.mom_input_dir / "weights").mkdir(exist_ok=True)
        (self.mom_input_dir / "forcing").mkdir(exist_ok=True)

        run_inputdir = self.mom_run_dir / "inputdir"
        if not run_inputdir.exists():
            run_inputdir.symlink_to(self.mom_input_dir.resolve())
        input_rundir = self.mom_input_dir / "rundir"
        if not input_rundir.exists():
            input_rundir.symlink_to(self.mom_run_dir.resolve())

    def __str__(self) -> str:
        return json.dumps(self.write_config_file(export=False, quiet=True), indent=4)

    def write_config_file(self, path=None, export=True, quiet=False):
        """
        Write a configuration file for the experiment. This is a simple json file
        that contains the expirment object information to allow for reproducibility, to pick up where a user left off, and
        to make information about the expirement readable.
        """
        if not quiet:
            print("Writing Config File.....")
        ## check if files exist
        vgrid_path = None
        hgrid_path = None
        if os.path.exists(self.mom_input_dir / "vcoord.nc"):
            vgrid_path = self.mom_input_dir / "vcoord.nc"
        if os.path.exists(self.mom_input_dir / "hgrid.nc"):
            hgrid_path = self.mom_input_dir / "hgrid.nc"

        try:
            date_range = [
                self.date_range[0].strftime("%Y-%m-%d"),
                self.date_range[1].strftime("%Y-%m-%d"),
            ]
        except:
            date_range = None
        config_dict = {
            "name": self.expt_name,
            "date_range": date_range,
            "latitude_extent": self.latitude_extent,
            "longitude_extent": self.longitude_extent,
            "run_dir": str(self.mom_run_dir),
            "input_dir": str(self.mom_input_dir),
            "toolpath_dir": str(self.toolpath_dir),
            "resolution": self.resolution,
            "number_vertical_layers": self.number_vertical_layers,
            "layer_thickness_ratio": self.layer_thickness_ratio,
            "depth": self.depth,
            "grid_type": self.grid_type,
            "repeat_year_forcing": self.repeat_year_forcing,
            "ocean_mask": self.ocean_mask,
            "layout": self.layout,
            "min_depth": self.min_depth,
            "vgrid": str(vgrid_path),
            "hgrid": str(hgrid_path),
            "bathymetry": self.bathymetry_property,
            "ocean_state": self.ocean_state_boundaries,
            "tides": self.tides_boundaries,
            "initial_conditions": self.initial_condition,
            "tidal_constituents": self.tidal_constituents,
        }
        if export:
            if path is not None:
                export_path = path
            else:
                export_path = self.mom_run_dir / "rmom6_config.json"
            with open(export_path, "w") as f:
                json.dump(
                    config_dict,
                    f,
                    indent=4,
                )
        if not quiet:
            print("Done.")
        return config_dict

    def generate_grids(self):
        self.grid_gen.create_hgrid()

    def generate_boundary_conditions(self):
        # Set h and v grid
        # Call rectangular boundaries
        # Call tides
        return

    def setup_MOM_files(self):
        self.boundary_conditions.setup_MOM_files()
        return

    def setup_CESM_case(self, sandbox_dir, case_dir):
        """-compset  --res TL319_t232 --case /glade/u/home/manishrv/cases/hawaii_clean_demo_tides_v2 --machine derecho --run-unsupported --project p93300612 --non-local"""
        subprocess.run(
            [
                "./create_newcase",
                "--case",
                case_dir,
                "--compset",
                "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV",
                "--res",
                "TL319_t232",
                "--machine",
                "derecho",
                "--run-unsupported",
                "--project",
                "p93300612",
                "--non-local",
            ],
            cwd=sandbox_dir,
        )
        self.rcg.setup_cesm(
            CESMPath=case_dir,
            hgrid=self.hgrid,
            mom_input_dir=self.mom_input_dir,
            mom_run_dir=self.mom_run_dir,
            date_range=self.date_range,
        )

        return

    def wrap_rm6_setup_bathymetry(self, bathymetry_path, longitude_coordinate_name, latitude_coordinate_name, vertical_coordinate_name):
        return self.og_mom6.setup_bathymetry(bathymetry_path = bathymetry_path, longitude_coordinate_name = longitude_coordinate_name, latitude_coordinate_name = latitude_coordinate_name, vertical_coordinate_name = vertical_coordinate_name)

    def wrap_rm6_setup_initial_condition(self,  gp,
            varnames,
            arakawa_grid
        ):
        return self.og_mom6.setup_initial_condition(gp, varnames, arakawa_grid = arakawa_grid)
    
    def wrap_rm6_setup_ocean_state_boundaries(self, gp,
            varnames,
            boundaries,
            arakawa_grid
        ):
        return self.og_mom6.setup_ocean_state_boundaries(gp, varnames, boundaries=boundaries, arakawa_grid = arakawa_grid)
    
    def wrap_rm6_setup_tides(self, dump_files_dir, tidal_data):
        return self.og_mom6.setup_boundary_tides(dump_files_dir, tidal_data)
    
    def wrap_rm6_setup_run_directory(self, surface_forcing, with_tides_rectangular, overwrite,premade_rundir_path_arg = None):
        return self.og_mom6.setup_run_directory(surface_forcing= surface_forcing,with_tides_rectangular = with_tides_rectangular,overwrite = overwrite, premade_rundir_path_arg = premade_rundir_path_arg)