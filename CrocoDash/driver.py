"""This module (driver) implements the CRRDriver class and contains a logger called "driver_logger" """

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


class CrocoDashDriver:
    """
    This class is the main class for the Crocodile Regional Ruckus. It stores all classes/objects that are used to generate a regional MOM6 workflow.
    You can find objects for the GridGen class, the RegionalCaseGen class, and the Regional-MOM6 experiment class. It also implements a config file wrapper on top
    of the regional-mom6 config read/write functions for easy regional mom6 development.
    Variables:
    1. ``grid_gen_obj`` : GridGen Class Object from the grid_gen module
    2. ``boundary_conditions_obj`` : BoundaryConditions Class Object from the unsupported_boundary_conditions module
    3. ``rcg_obj`` : RegionalCaseGen Class Object from the regional_casegen module
    4. ``empty_expt_obj`` : An Empty Regional-MOM6 Experiment Class Object from the regional_mom6 module for whatever use you could need...
    Functions:
    1. ``__init__`` : Initializes the CRRDriver object with options to pass regional-mom6 experiment arguments to empty_expt_obj
    2. ``__str__`` : Returns the config file of the empty_expt_obj as a string
    3. ``create_experiment_from_config`` : Creates a regional-mom6 experiment object from a config file
    4. ``write_config_file`` : Writes a config file from a regional-mom6 experiment object
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
        This init function initializes the GridGen, RegionalCaseGen, Regional-MOM6, and BoundaryConditions class. It requires no arguments, but accepts (optional) Regional-MOM6 experiment parameters for the Regional-MOM6 object.
         The only reason to have these arguments is for easy storage.
         Parameters (For Regional-MOM6 in kwargs...)
         ----------
         longitude_extent : tuple, optional
             The longitude extent of the experiment, by default None
         latitude_extent : tuple, optional
             The latitude extent of the experiment, by default None
         date_range : tuple, optional
             The date range of the experiment, by default None
         resolution : float, optional
             The resolution of the experiment, by default None
         number_vertical_layers : int, optional
             The number of vertical layers in the experiment, by default None
         layer_thickness_ratio : float, optional
             The layer thickness ratio of the experiment, by default None
         depth : float, optional
             The depth of the experiment, by default None
         mom_run_dir : str, optional
             The mom run directory of the experiment, by default None
         mom_input_dir : str, optional
             The mom input directory of the experiment, by default None
         toolpath_dir : str, optional
             The toolpath directory of the experiment, by default None
         hgrid_type : str, optional
             The hgrid type of the experiment, by default "from_file"
         vgrid_type : str, optional
             The vgrid type of the experiment, by default "from_file"
         repeat_year_forcing : bool, optional
             The repeat year forcing of the experiment, by default False
         minimum_depth : int, optional
             The minimum depth of the experiment, by default None
         tidal_constituents : list, optional
             The tidal constituents of the experiment, by default ["M2"]
         expt_name : str, optional
             The experiment name of the experiment, by default None
         Returns
         -------
         None
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
                expt_name=expt_name,
                hgrid_type=hgrid_type,
            )
        )

    @classmethod
    def create_experiment_from_config(
        self,
        config_file_path: str,
        overwrite_files_to_expt_format: bool = True,
        create_hgrid_and_vgrid: bool = False,
    ) -> rm6.experiment:
        """
        This agressive function is a experiment setup and copier. It reads from a config file and sets up an experiment in config["mom_input_dir"] and config["mom_run_dir"].
        If the files are not in the config["mom_input_dir"], they are copied there by default from the specified file paths.
        Warning: This overwrite any files in the specified directories, and will always do that unless overwrite_files_to_expt_format is set to False.

        Parameters
        ----------
        config_file_path : str
            Path to the config file
        overwrite_files_to_expt_format : bool, optional
            If True, the files are copied to the mom_input_dir, by default True
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
            if overwrite_files_to_expt_format:
                self.replace_files_with_warnings(
                    Path(config_dict["hgrid"]),
                    Path(config_dict["mom_input_dir"]) / "hgrid.nc",
                )
        else:
            driver_logger.info("Hgrid not found, call _make_hgrid when you're ready.")

        if os.path.exists(config_dict["vgrid"]):
            driver_logger.info("Found")
            # Move to mom_input_dir
            if overwrite_files_to_expt_format:
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
            if overwrite_files_to_expt_format:
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
                    if overwrite_files_to_expt_format:
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
                    if overwrite_files_to_expt_format:
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
                    if overwrite_files_to_expt_format:
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
                    if overwrite_files_to_expt_format:
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

    def __str__(self) -> str:
        """
        This function dumps the empty_expt_object into the config maker as a string just so that we can see some information about this object.
        """
        return json.dumps(
            self.write_config_file(self.empty_expt_obj, export=False, quiet=True),
            indent=4,
        )

    @classmethod
    def write_config_file(
        self,
        expt: rm6.experiment,
        path: str = None,
        export: bool = True,
        quiet: bool = False,
    ) -> dict:
        """
        This function writes a configuration file for the experiment. It contains all the filepaths used in the experiment (ocean_state, tidal, inital_condition, run_files, etc..).
        This takes in the expt variable and writes a simple json file. This allows for reproducibility, to pick up where a user left off, and to make information about the expirement readable.

        Parameters
        ----------
        expt : rm6.experiment
            The experiment object
        path : str, optional
            The path to write the config file, by default set to expt.mom_input_dir/"crr_config.json"
        export : bool, optional
            If True, the config file is exported to path, by default True
        quiet : bool, optional
            If True, the function is quiet and doesn't print information, by default False

        Returns
        -------
        dict
            The configuration dictionary
        """
        if not quiet:
            driver_logger.info("Writing Config File.....")

        rm6_config = expt.write_config_file(export=False, quiet=True)

        ## To Add Specific Path Things to the config file:

        # MOM dirs
        rm6_config["mom_input_dir"] = str(expt.mom_input_dir)
        rm6_config["mom_run_dir"] = str(expt.mom_run_dir)

        if not quiet:
            driver_logger.info(
                "Searching {} for bathymetry, hgrid, vgrid".format(expt.mom_input_dir)
            )
        # Bathymetry
        if os.path.join(expt.mom_input_dir, "bathymetry.nc"):
            rm6_config["bathymetry"] = str(expt.mom_input_dir / "bathymetry.nc")
        else:
            rm6_config["bathymetry"] = None
            if not quiet:
                driver_logger.info(
                    "Couldn't find bathymetry file in {}".format(expt.mom_input_dir)
                )

        # Hgrid
        if os.path.join(expt.mom_input_dir, "hgrid.nc"):
            rm6_config["hgrid"] = str(expt.mom_input_dir / "hgrid.nc")
        else:
            rm6_config["hgrid"] = None
            if not quiet:
                driver_logger.info(
                    "Couldn't find hgrid file in {}".format(expt.mom_input_dir)
                )

        # Vgrid
        if os.path.join(expt.mom_input_dir, "vgrid.nc"):
            rm6_config["vgrid"] = str(expt.mom_input_dir / "vcoord.nc")
        else:
            rm6_config["vgrid"] = None
            if not quiet:
                driver_logger.info(
                    "Couldn't find vgrid file in {}".format(expt.mom_input_dir)
                )

        # Initial Conditions
        if not quiet:
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
            if not quiet:
                driver_logger.info(
                    "Couldn't find initial conditions in {}".format(expt.mom_input_dir)
                )

        # Ocean State Files
        if not quiet:
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
            if not quiet:
                driver_logger.info(
                    "Couldn't find ocean_state conditions in {}".format(
                        expt.mom_input_dir
                    )
                )

        # Tides Files
        if not quiet:
            driver_logger.info("Searching {} for tides".format(expt.mom_input_dir))
        tides_files = self.search_for_files(
            [expt.mom_input_dir, expt.mom_input_dir / "forcing"],
            ["regrid*", "tu_*", "tz_*"],
        )
        if type(tides_files) == list:
            rm6_config["tides"] = tides_files
        else:
            rm6_config["tides"] = None
            if not quiet:
                driver_logger.info(
                    "Couldn't find tides in {}".format(expt.mom_input_dir)
                )

        # Run Files
        if not quiet:
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
            if not quiet:
                driver_logger.info(
                    "Couldn't find run files in {}".format(expt.mom_run_dir)
                )

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

    def search_for_files(paths: list[str], patterns: list[str]) -> list[str]:
        """
        This function is a helper for write_config_file and searchs for given patterns at given folder paths.

        Parameters
        ----------
        paths : list
            List of paths to search for files
        patterns : list
            List of patterns to search for

        Returns
        -------
        list or str
            List of files found or a string saying no files found
        """
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

    def replace_files_with_warnings(path_to_file: str, path_to_replace: str) -> None:
        """
        This function is a helper function for create_experiment_from_config and replaces an original file with a copy of the given filepath.

        Parameters
        ----------
        path_to_file : str
            Path to the file to copy from
        path_to_replace : str
            Path to the file to replace

        Returns
        -------
        None
        """
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
