from .utils import setup_logger

driver_logger = setup_logger(__name__)
import datetime as dt
import xarray as xr
import json
from . import grid_gen
from . import unsupported_boundary_conditions
from .regional_casegen import cesm_tools as rcg_ct
import os
from pathlib import Path
import subprocess
from .rm6 import regional_mom6 as rm6
import shutil
import importlib
import sys
import glob


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
        hgrid_type="from_file",  # Don't do anything with this
        vgrid_type="from_file",  # Don't do anything with this
        repeat_year_forcing=False,
        minimum_depth=4,
        tidal_constituents=["M2"],
        expt_name=None,
    ):
        """
        This init function requires no arguments. It sets up the experiment object with default values. The only reason to have these arguments is for easy storage.
        This is just a style change from Regional MOM6, where the experiment object takes most arguments and doesn't ask for them at function calls.
        """
        # ## Set up the experiment with no config file
        ## in case list was given, convert to tuples
        self.grid_gen_obj = grid_gen.GridGen()
        self.boundary_conditions_obj = (
            unsupported_boundary_conditions.BoundaryConditions()
        )  # Not Implemented Yet
        self.rcg_obj = rcg_ct.RegionalCaseGen()
        self.empty_expt_obj = (
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
                hgrid_type=hgrid_type,
            )
        )

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
    def load_experiment_from_config(
        self,
        config_file_path,
        rearrange_files_to_expt_format=True,
        create_hgrid_and_vgrid=False,
    ):
        """
        This reads from the config file and sets up an experiment in mom_input_dir and mom_run_dir. If the files are not in the mom_input_dir, they are copied there by default. THIS DELETES THE CURRENT FILES

        Parameters
        ----------
        config_file_path : str
            Path to the config file
        rearrange_files_to_expt_format : bool, optional
            If True, the files are moved to the mom_input_dir, by default True
        create_hgrid_and_vgrid : bool, optional
            If True, the hgrid and vgrid are created from the lat, long

        Returns
        -------
        expt : rm6.experiment
            The experiment object

        """
        driver_logger.info("Reading from config file....")
        with open(config_file_path, "r") as f:
            config_dict = json.load(f)

        driver_logger.info("Creating Input and Run Dirs if not already....")
        os.makedirs(config_dict["mom_input_dir"], exist_ok=True)
        os.makedirs(config_dict["mom_run_dir"], exist_ok=True)

        driver_logger.info("Checking for hgrid and vgrid....")
        if os.path.exists(config_dict["hgrid"]):
            driver_logger.info("Found")
            # Move to mom_input_dir
            if rearrange_files_to_expt_format:
                self.replace_files_with_warnings(
                    Path(config_dict["hgrid"]),
                    Path(config_dict["mom_input_dir"]) / "hgrid.nc",
                )
        else:
            driver_logger.info("Hgrid not found, call _make_hgrid when you're ready.")

        if os.path.exists(config_dict["vgrid"]):
            driver_logger.info("Found")
            # Move to mom_input_dir
            if rearrange_files_to_expt_format:
                self.replace_files_with_warnings(
                    Path(config_dict["vgrid"]),
                    Path(config_dict["mom_input_dir"]) / "vcoord.nc",
                )

        else:
            driver_logger.info("Vgrid not found, call _make_vgrid when ready")

        driver_logger.info("Creating Expt Object....")
        expt = rm6.create_experiment_from_config(
            config_file_path,
            mom_input_folder=config_dict["mom_input_dir"],
            mom_run_folder=config_dict["mom_run_dir"],
            create_hgrid_and_vgrid=create_hgrid_and_vgrid,
        )

        driver_logger.info("Checking for bathymetry...")
        if (
            "bathymetry" in config_dict
            and config_dict["bathymetry"] is not None
            and os.path.exists(config_dict["bathymetry"])
        ):
            driver_logger.info("Found")
            # Move to mom_input_dir
            if rearrange_files_to_expt_format:
                self.replace_files_with_warnings(
                    Path(config_dict["bathymetry"]),
                    Path(config_dict["mom_input_dir"]) / "bathymetry.nc",
                )
        else:
            driver_logger.info(
                "Bathymetry not found. Please provide bathymetry, or call setup_bathymetry method to set up bathymetry."
            )

        driver_logger.info("Checking for ocean state files....")
        if "ocean_state" in config_dict and config_dict["ocean_state"] is not None:

            for path in config_dict["ocean_state"]:
                if not os.path.exists(path):
                    driver_logger.info(
                        "At least one ocean state file not found. Please provide ocean state files, or call setup_ocean_state_boundaries method to set up ocean state."
                    )
                else:
                    # Move to mom_input_dir
                    driver_logger.info("Found at least one ocean state file.")
                    if rearrange_files_to_expt_format:
                        self.replace_files_with_warnings(
                            Path(path),
                            Path(config_dict["mom_input_dir"]) / os.path.basename(path),
                        )
        else:
            driver_logger.info(
                'Ocean state files not found. Please provide ocean state files (with key "ocean_state"), or call setup_ocean_state_boundaries method to set up ocean state.'
            )

        driver_logger.info("Checking for initial condition files....")
        if (
            "initial_conditions" in config_dict
            and config_dict["initial_conditions"] is not None
        ):
            for path in config_dict["initial_conditions"]:
                if not os.path.exists(path):

                    driver_logger.info(
                        "At least one initial condition file not found. Please provide initial condition files, or call setup_initial_condition method to set up initial condition."
                    )
                    break
                else:
                    driver_logger.info("Found at least one initial condition file.")
                    # Move to mom_input_dir
                    if rearrange_files_to_expt_format:
                        self.replace_files_with_warnings(
                            Path(path),
                            Path(config_dict["mom_input_dir"]) / os.path.basename(path),
                        )
        else:
            driver_logger.info(
                'Initial condition files not found. Please provide initial condition files (with key "initial_conditions"), or call setup_initial_condition method to set up initial condition.'
            )

        driver_logger.info("Checking for tides files....")
        if "tides" in config_dict and config_dict["tides"] is not None:
            for path in config_dict["tides"]:
                if not os.path.exists(path):

                    driver_logger.info(
                        "At least one tides file not found. If you would like tides, call setup_tides_boundaries method to set up tides"
                    )
                    break
                else:
                    driver_logger.info("Found at least one tides file.")
                    # Move to mom_input_dir
                    if rearrange_files_to_expt_format:
                        self.replace_files_with_warnings(
                            Path(path),
                            Path(config_dict["mom_input_dir"]) / os.path.basename(path),
                        )
        else:
            driver_logger.info(
                'Tides files not found. Please provide tides files (with key "tides"), or  call setup_tides_boundaries method to set up tides'
            )

        driver_logger.info("Checking for run files....")
        if "run_files" in config_dict and config_dict["run_files"] is not None:
            for path in config_dict["run_files"]:
                if not os.path.exists(path):

                    driver_logger.info(
                        "At least one run_files file not found. If you would like run_files, call setup_run_directory method to set up run_files"
                    )
                    break
                else:
                    driver_logger.info("Found at least one run_files file.")
                    # Move to mom_input_dir
                    if rearrange_files_to_expt_format:
                        self.replace_files_with_warnings(
                            Path(path),
                            Path(config_dict["mom_run_dir"]) / os.path.basename(path),
                        )
        else:
            driver_logger.info(
                'Tides files not found. Please provide run_files files (with key "run_files"), or  call setup_run_files_boundaries method to set up run_files'
            )

        if os.path.exists(Path(config_dict["mom_input_dir"]) / "bathymetry.nc"):
            expt.bathymetry = xr.open_dataset(
                Path(config_dict["mom_input_dir"]) / "bathymetry.nc"
            )
        if os.path.exists(Path(config_dict["mom_input_dir"]) / "hgrid.nc"):
            expt.hgrid = xr.open_dataset(
                Path(config_dict["mom_input_dir"]) / "hgrid.nc"
            )
        if os.path.exists(Path(config_dict["mom_input_dir"]) / "vcoord.nc"):
            expt.vgrid = xr.open_dataset(
                Path(config_dict["mom_input_dir"]) / "vcoord.nc"
            )
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

    @classmethod
    def write_config_file(self, expt, path=None, export=True, quiet=False):
        """
        Write a configuration file for the experiment. This takes in the expt variable and writes a config file. This is a simple json file
        that contains the expirment object information to allow for reproducibility, to pick up where a user left off, and
        to make information about the expirement readable.
        """
        if not quiet:
            driver_logger.info("Writing Config File.....")

        rm6_config = expt.write_config_file(export=False, quiet=True)

        ## To Add Specific Path Things to the config file:

        # MOM dirs
        rm6_config["mom_input_dir"] = str(expt.mom_input_dir)
        rm6_config["mom_run_dir"] = str(expt.mom_run_dir)

        driver_logger.info(
            "Searching {} for bathymetry, hgrid, vgrid".format(expt.mom_input_dir)
        )
        # Bathymetry
        if os.path.join(expt.mom_input_dir, "bathymetry.nc"):
            rm6_config["bathymetry"] = str(expt.mom_input_dir / "bathymetry.nc")
        else:
            rm6_config["bathymetry"] = None
            driver_logger.info(
                "Couldn't find bathymetry file in {}".format(expt.mom_input_dir)
            )

        # Hgrid
        if os.path.join(expt.mom_input_dir, "hgrid.nc"):
            rm6_config["hgrid"] = str(expt.mom_input_dir / "hgrid.nc")
        else:
            rm6_config["hgrid"] = None
            driver_logger.info(
                "Couldn't find hgrid file in {}".format(expt.mom_input_dir)
            )

        # Vgrid
        if os.path.join(expt.mom_input_dir, "vgrid.nc"):
            rm6_config["vgrid"] = str(expt.mom_input_dir / "vcoord.nc")
        else:
            rm6_config["vgrid"] = None
            driver_logger.info(
                "Couldn't find vgrid file in {}".format(expt.mom_input_dir)
            )

        # Initial Conditions
        driver_logger.info(
            "Searching {} for initial conditions".format(expt.mom_input_dir)
        )
        initial_conditions_files = self.search_for_files(
            [expt.mom_input_dir, expt.mom_input_dir / "forcing"], ["init_*.nc"]
        )
        if type(initial_conditions_files) == list:
            rm6_config["initial_conditions"] = initial_conditions_files
        else:
            rm6_config["initial_conditions"] = None
            driver_logger.info(
                "Couldn't find initial conditions in {}".format(expt.mom_input_dir)
            )

        # Ocean State Files
        driver_logger.info(
            "Searching {} for ocean_state conditions".format(expt.mom_input_dir)
        )
        ocean_state_files = self.search_for_files(
            [expt.mom_input_dir, expt.mom_input_dir / "forcing"],
            [
                "forcing_*",
                "weights/bi*",
            ],
        )
        if type(ocean_state_files) == list:
            rm6_config["ocean_state"] = ocean_state_files
        else:
            rm6_config["ocean_state"] = None
            driver_logger.info(
                "Couldn't find ocean_state conditions in {}".format(expt.mom_input_dir)
            )

        # Tides Files
        driver_logger.info("Searching {} for tides".format(expt.mom_input_dir))
        tides_files = self.search_for_files(
            [expt.mom_input_dir, expt.mom_input_dir / "forcing"],
            ["regrid*", "tu_*", "tz_*"],
        )
        if type(tides_files) == list:
            rm6_config["tides"] = tides_files
        else:
            rm6_config["tides"] = None
            driver_logger.info("Couldn't find tides in {}".format(expt.mom_input_dir))

        # Run Files
        driver_logger.info("Searching {} for run files".format(expt.mom_run_dir))
        mom_files = self.search_for_files(
            [expt.mom_run_dir],
            [
                "MOM_input",
                "MOM_override",
                "MOM_layout",
                "SIS_input",
                "field_table",
                "input.nml",
                "diag_table",
                "data_table",
            ],
        )
        if type(mom_files) == list:
            rm6_config["run_files"] = mom_files
        else:
            rm6_config["run_files"] = None
            driver_logger.info("Couldn't find run files in {}".format(expt.mom_run_dir))

        if export:
            if path is not None:
                export_path = path
            else:
                export_path = self.mom_run_dir / "crr_config.json"
            with open(export_path, "w") as f:
                json.dump(
                    rm6_config,
                    f,
                    indent=4,
                )
        if not quiet:
            driver_logger.info("Done.")
        return rm6_config

    def explicit_setup_run_directory(
        self,
        mom_input_dir,
        mom_run_dir,
        date_range,
        hgrid,
        vgrid,
        tidal_constituents,
        surface_forcing=None,
        overwrite=False,
        with_tides=False,
        boundaries=["south", "north", "west", "east"],
        premade_rundir_path_arg=None,
    ):
        """
        This function should set up the run directory for the experiment.
        """
        expt = rm6.experiment.create_empty(
            mom_input_dir=mom_input_dir,
            mom_run_dir=mom_run_dir,
            date_range=date_range,
            tidal_constituents=tidal_constituents,
        )
        expt.hgrid = hgrid
        expt.vgrid = vgrid
        os.makedirs(mom_input_dir, exist_ok=True)
        os.makedirs(mom_run_dir, exist_ok=True)
        premade_rundir_path_arg = Path(
            os.path.join(
                importlib.resources.files("crocodileregionalruckus"),
                "rm6_dir",
                "demos",
                "premade_run_directories",
            )
        )
        sys.modules["regional_mom6"] = rm6
        return expt.setup_run_directory(
            surface_forcing=surface_forcing,
            overwrite=overwrite,
            with_tides=with_tides,
            boundaries=boundaries,
        )

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

        driver_logger.info(f"All files have been exported to {output_folder}")

    def search_for_files(paths, patterns):
        try:
            all_files = []

            for pattern in patterns:
                for path in paths:
                    all_files.extend(glob.glob(str(path / pattern)))

            if len(all_files) == 0:
                return "No files found (or files misplaced from {})".format(paths)
            return all_files
        except:
            return "No files found (or files misplaced from {})".format(paths)

    def replace_files_with_warnings(path_to_file, path_to_replace):
        if Path(path_to_file) != Path(path_to_replace) and os.path.exists(
            path_to_replace
        ):
            driver_logger.warning(
                f"There was a {os.path.basename(path_to_replace)} already in the directory to replace. We are removing it! To disable this aggresive move, set rearrange_files_to_expt_format=False"
            )
            os.remove(path_to_replace)
        if Path(path_to_file) != Path(path_to_replace):
            driver_logger.info(
                f"Copying {os.path.basename(path_to_file)} to {path_to_replace}"
            )
            shutil.copyfile(Path(path_to_file), Path(path_to_replace))
        else:
            driver_logger.info(f"{os.path.basename(path_to_replace)} already in dir")
