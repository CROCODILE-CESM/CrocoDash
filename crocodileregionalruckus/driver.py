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
import shutil
import importlib
class crr_driver:
    """Who needs documentation?

    The idea here is to wrap the regional mom6 workflow into one python package.
    """

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
        hgrid_type="from_file", # Don't do anything with this
        vgrid_type="from_file", # Don't do anything with this
        repeat_year_forcing=False,
        minimum_depth=4,
        tidal_constituents=["M2"],
        expt_name=None,
    ):
        # ## Set up the experiment with no config file
        ## in case list was given, convert to tuples
        self.grid_gen_obj = grid_gen.GridGen()
        self.boundary_conditions_obj = (
            boundary_conditions.BoundaryConditions()
        )  # Not Implemented Yet
        self.rcg_obj = rcg_ct.RegionalCaseGen()
        self.og_mom6 = (
            rm6.experiment.create_empty(  # Takes the place of boundary_conditions
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
                repeat_year_forcing=repeat_year_forcing,
                minimum_depth=minimum_depth,
                tidal_constituents=tidal_constituents,
                name=expt_name,
                hgrid_type = hgrid_type,
            )
        )
        """
        This init function requires no arguments. It sets up the experiment object with default values. The only reason to have these arguments is for easy storage. 
        This is just a style change from Regional MOM6, where the experiment object takes most arguments and doesn't ask for them at function calls.
        """

        self.expt_name = expt_name
        self.tidal_constituents = tidal_constituents
        self.repeat_year_forcing = repeat_year_forcing
        self.hgrid_type = hgrid_type
        self.vgrid_type = vgrid_type
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
        raise ValueError("Not implemented yet")
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
        if not os.path.islink(run_inputdir):
            run_inputdir.symlink_to(self.mom_input_dir.resolve())
        input_rundir = self.mom_input_dir / "rundir"
        if not os.path.islink(input_rundir):
            input_rundir.symlink_to(self.mom_run_dir.resolve())

    def __str__(self) -> str:
        return json.dumps(self.write_config_file(export=False, quiet=True), indent=4)

    def write_config_file(self, path=None, export=True, quiet=False):
        """
        Write a configuration file for the experiment. This is a simple json file
        that contains the expirment object information to allow for reproducibility, to pick up where a user left off, and
        to make information about the expirement readable.
        """
        raise ValueError("Not implemented yet")
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

    def setup_run_directory(self, mom_input_dir, mom_run_dir,date_range, hgrid, vgrid, tidal_constituents, 
        surface_forcing=None,
        overwrite=False,
        with_tides=False,
        boundaries=["south", "north", "west", "east"],
        premade_rundir_path_arg=None):
        """
        This function should set up the run directory for the experiment. 
        """
        expt = rm6.experiment.create_empty(mom_input_dir=mom_input_dir, mom_run_dir=mom_run_dir,date_range=date_range, tidal_constituents=tidal_constituents)
        expt.hgrid = hgrid
        expt.vgrid = vgrid
        os.makedirs(mom_input_dir, exist_ok=True)
        os.makedirs(mom_run_dir, exist_ok=True)
        premade_rundir_path_arg=Path(os.path.join(importlib.resources.files("crocodileregionalruckus"),"rm6_dir","demos","premade_run_directories"))
        return expt.setup_run_directory(surface_forcing=surface_forcing, overwrite=overwrite, with_tides=with_tides, boundaries=boundaries, premade_rundir_path_arg=premade_rundir_path_arg)
    
    def export_files(self, output_folder):
        """
        Export all files from the temp_storage directory to the output_folder.

        Parameters:
        output_folder (str): Path to the output directory where files will be copied.
        """
        input_dir = Path(self.temp_storage)
        output_dir = Path(output_folder)

        if not output_dir.exists():
            os.makedirs(output_dir)

        for item in input_dir.iterdir():
            if item.is_file():
                shutil.copy(item, output_dir / item.name)
            elif item.is_dir():
                shutil.copytree(item, output_dir / item.name)

        print(f"All files have been exported to {output_folder}")