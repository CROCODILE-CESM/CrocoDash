from pathlib import Path
import uuid
import shutil
from datetime import datetime
import json
import sys
import pandas as pd
import regional_mom6 as rmom6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.raw_data_access import driver as dv
from CrocoDash.raw_data_access import config as tb
from CrocoDash.raw_data_access import driver as dv
from ProConPy.config_var import ConfigVar, cvars
from ProConPy.stage import Stage
from ProConPy.csp_solver import csp
from ProConPy.dev_utils import ConstraintViolation
from visualCaseGen.cime_interface import CIME_interface
from visualCaseGen.initialize_configvars import initialize_configvars
from visualCaseGen.initialize_widgets import initialize_widgets
from visualCaseGen.initialize_stages import initialize_stages
from visualCaseGen.specs.options import set_options
from visualCaseGen.specs.relational_constraints import get_relational_constraints
from visualCaseGen.custom_widget_types.case_creator import CaseCreator, ERROR, RESET
from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl
from mom6_bathy import chl, mapping, grid
import xesmf as xe
import xarray as xr
import numpy as np
import cftime


class Case:
    """This class represents a regional MOM6 case within the CESM framework. It is similar to the
    Experiment class in the regional_mom6 package, but with modifications to work within the CESM framework.
    """

    def __init__(
        self,
        *,
        cesmroot: str | Path,
        caseroot: str | Path,
        inputdir: str | Path,
        compset: str,
        ocn_grid: Grid,
        ocn_topo: Topo,
        ocn_vgrid: VGrid,
        datm_grid_name: str = "TL319",
        ninst: int = 1,
        machine: str | None = None,
        project: str | None = None,
        override: bool = False,
        ntasks_ocn: int | None = None,
        job_queue: str | None = None,
        job_wallclock_time: str | None = None,
    ):
        """
        Initialize a new regional MOM6 case within the CESM framework.

        Parameters
        ----------
        cesmroot : str | Path
            Path to the existing CESM root directory.
        caseroot : str | Path
            Path to the case root directory to be created.
        inputdir : str | Path
            Path to the input directory to be created.
        compset : str
            The component set alias (e.g. "G_JRA") or long name
            (e.g. "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV_SESP") for the case.
        ocn_grid : Grid
            The ocean grid object to be used in the case.
        ocn_topo : Topo
            The ocean topography object to be used in the case.
        ocn_vgrid : VGrid
            The ocean vertical grid object to be used in the case.
        datm_grid_name : str, optional
            The data atmosphere grid name of the case. Default is "TL319".
        ninst : int, optional
            The number of model instances. Default is 1.
        machine : str, optional
            The machine name to be used in the case. Default is None.
        project : str, optional
            The project name to be used in the case. Default is None.
            If the machine requires a project, this argument must be provided.
        override : bool, optional
            Whether to override existing caseroot and inputdir directories. Default is False.
        ntasks_ocn : int, optional
            Number of tasks for the ocean model. If None, defaults to VisualCaseGen Grid Calculation.
        job_queue: str, optional
            The queue to submit the CESM case to. If None, defaults to the CESM defaults (usually main)
        job_wallclock_time: str, optional
            Must be in the form hh:mm:ss. If None, defaults to the CESM defaults
        """

        # Initialize the CIME interface object
        self.cime = CIME_interface(cesmroot)

        if machine is None:
            machine = self.cime.machine

        # Sanity checks on the input arguments
        self._init_args_check(
            caseroot,
            inputdir,
            ocn_grid,
            ocn_topo,
            ocn_vgrid,
            compset,
            datm_grid_name,
            ninst,
            machine,
            project,
            override,
            ntasks_ocn,
            job_queue,
            job_wallclock_time,
        )

        self.caseroot = Path(caseroot)
        self.inputdir = Path(inputdir)
        self.ocn_grid = ocn_grid
        self.ocn_topo = ocn_topo
        self.ocn_vgrid = ocn_vgrid
        self.ninst = ninst
        self.override = override
        self.ProductFunctionRegistry = dv.ProductFunctionRegistry()
        self.ProductFunctionRegistry.load_functions()
        self.forcing_product_name = None
        self._configure_forcings_called = False
        self._large_data_workflow_called = False
        self.compset = compset

        # Resolution name:
        self.resolution = f"{datm_grid_name}_{ocn_grid.name}"

        self._initialize_visualCaseGen()

        try:
            self._assign_configvars(compset, machine, project)
        except ConstraintViolation as e:
            print(f"{ERROR}{str(e)}{RESET}")
            return
        # Removed redundant exception handling block.

        self._create_grid_input_files()

        self._create_newcase()

        self._cime_case = self.cime.get_case(
            self.caseroot, non_local=self.cc._is_non_local()
        )

        self.compset = self._cime_case.get_value("COMPSET")
        print("Compset longname is:", self.compset)

        self.runoff_in_compset = "DROF" in self.compset
        self.bgc_in_compset = "%MARBL" in self.compset
        self.cice_in_compset = "CICE" in self.compset

        # CICE grid file (if needed)
        if self.cice_in_compset:
            self.cice_grid_path = (
                inputdir / "ocnice" / f"cice_grid_{ocn_grid.name}_{cvars['MB_ATTEMPT_ID'].value}.nc"
            )
            self.ocn_topo.write_cice_grid(self.cice_grid_path)

        xmlchange(
            "MOM6_MEMORY_MODE",
            "dynamic_symmetric",
            is_non_local=self.cc._is_non_local(),
        )
        # xmlchange(
        #     "MOM6_DOMAIN_TYPE",
        #     "REGIONAL",
        #     is_non_local=self.cc._is_non_local(),
        # )

        # xmlchange("ROOTPE_OCN", 128, is_non_local=self.cc._is_non_local()) -> needs to be before the the setup
        if ntasks_ocn is not None:
            xmlchange("NTASKS_OCN", ntasks_ocn, is_non_local=self.cc._is_non_local())
        # This will trigger for both the run and the archiver.
        if job_queue is not None:
            xmlchange("JOB_QUEUE", job_queue, is_non_local=self.cc._is_non_local())
        if job_wallclock_time is not None:
            xmlchange(
                "JOB_WALLCLOCK_TIME",
                job_wallclock_time,
                is_non_local=self.cc._is_non_local(),
            )

    def _init_args_check(
        self,
        caseroot: str | Path,
        inputdir: str | Path,
        ocn_grid: Grid,
        ocn_topo: Topo,
        ocn_vgrid: VGrid,
        compset: str,
        datm_grid_name: str,
        ninst: int,
        machine: str | None,
        project: str | None,
        override: bool,
        ntasks_ocn: int | None = None,
        job_queue: str | None = None,
        job_wallclock_time: str | None = None,
    ):

        if Path(caseroot).exists() and not override:
            raise ValueError(f"Given caseroot {caseroot} already exists!")
        if Path(inputdir).exists() and not override:
            raise ValueError(f"Given inputdir {inputdir} already exists!")
        if not isinstance(ocn_grid, Grid):
            raise TypeError("ocn_grid must be a Grid object.")
        if not isinstance(ocn_vgrid, VGrid):
            raise TypeError("ocn_vgrid must be a VGrid object.")
        if not isinstance(ocn_topo, Topo):
            raise TypeError("ocn_topo must be a Topo object.")
        if datm_grid_name not in (
            available_atm_grids := self.cime.domains["atm"].keys()
        ):
            raise ValueError(f"datm_grid_name must be one of {available_atm_grids}.")
        if ocn_grid.name is None:
            raise ValueError(
                "ocn_grid must have a name. Please set it using the 'name' attribute."
            )
        if ocn_grid.name in self.cime.domains["ocnice"] and not override:
            raise ValueError(f"ocn_grid name {ocn_grid.name} is already in use.")
        if not isinstance(ninst, int):
            raise TypeError("ninst must be an integer.")
        if machine is None:
            raise ValueError(
                "Couldn't determine machine. Please provide the machine argument."
            )
        if not isinstance(machine, str):
            raise TypeError("machine must be a string.")
        if not machine in self.cime.machines:
            raise ValueError(f"machine must be one of {self.cime.machines}.")
        if self.cime.project_required[machine] is True:
            if project is None:
                raise ValueError(f"project is required for machine {machine}.")
            if not isinstance(project, str):
                raise TypeError("project must be a string.")
        if ntasks_ocn is not None and not isinstance(ntasks_ocn, int):
            raise TypeError("ntasks_ocn must be an integer.")
        if job_queue is not None and not isinstance(job_queue, str):
            raise TypeError("job_queue must be a str")
        if job_wallclock_time is not None and not isinstance(job_wallclock_time, str):
            raise TypeError("job_wallclock_time must be a str of format hh:mm:ss")

    def _create_grid_input_files(self):

        inputdir = self.inputdir
        ocn_grid = self.ocn_grid
        ocn_topo = self.ocn_topo
        ocn_vgrid = self.ocn_vgrid

        if self.override is True:
            if inputdir.exists():
                shutil.rmtree(inputdir)

        inputdir.mkdir(parents=True, exist_ok=False)
        (inputdir / "ocnice").mkdir()

        # suffix for the MOM6 grid files
        session_id = cvars["MB_ATTEMPT_ID"].value
        self.supergrid_path = str(
            self.inputdir
            / "ocnice"
            / f"ocean_hgrid_{self.ocn_grid.name}_{session_id}.nc"
        )
        self.vgrid_path = str(
            self.inputdir
            / "ocnice"
            / f"ocean_vgrid_{self.ocn_grid.name}_{session_id}.nc"
        )
        self.topo_path = str(
            inputdir / "ocnice" / f"ocean_topog_{ocn_grid.name}_{session_id}.nc"
        )
        self.scrip_grid_path = (
            inputdir / "ocnice" / f"scrip_{ocn_grid.name}_{session_id}.nc"
        )
        self.esmf_mesh_path = (
            inputdir / "ocnice" / f"ESMF_mesh_{ocn_grid.name}_{session_id}.nc"
        )
        # MOM6 supergrid file
        ocn_grid.write_supergrid(self.supergrid_path)

        # MOM6 topography file
        ocn_topo.write_topo(self.topo_path)

        # MOM6 vertical grid file
        ocn_vgrid.write(self.vgrid_path)

        # SCRIP grid file (needed for runoff remapping)
        ocn_topo.write_scrip_grid(self.scrip_grid_path)

        # ESMF mesh file:
        ocn_topo.write_esmf_mesh(self.esmf_mesh_path)

    def _create_newcase(self):
        """Create the case instance."""
        # cvars["COMPSET_LNAME"].value = self.compset
        # If override is True, clean up the existing caseroot and output directories
        if self.override is True:
            if self.caseroot.exists():
                shutil.rmtree(self.caseroot)
            if (Path(self.cime.cime_output_root) / self.caseroot.name).exists():
                shutil.rmtree(Path(self.cime.cime_output_root) / self.caseroot.name)

        if not self.caseroot.parent.exists():
            self.caseroot.parent.mkdir(parents=True, exist_ok=False)

        self.cc = CaseCreator(self.cime, allow_xml_override=self.override)

        try:
            self.cc.create_case(do_exec=True)
        except Exception as e:
            print(f"{ERROR}{str(e)}{RESET}")
            self.cc.revert_launch(do_exec=True)

    def configure_forcings(
        self,
        date_range: list[str],
        boundaries: list[str] = ["south", "north", "west", "east"],
        tidal_constituents: list[str] | None = None,
        tpxo_elevation_filepath: str | Path | None = None,
        tpxo_velocity_filepath: str | Path | None = None,
        product_name: str = "GLORYS",
        function_name: str = "get_glorys_data_script_for_cli",
        product_info: str | Path | dict = None,
        too_much_data: bool = False,
        chl_processed_filepath: str | Path | None = None,
        runoff_esmf_mesh_filepath: str | Path | None = None,
        raw_data_path: str | Path | None = None,
        global_river_nutrients_filepath: str | Path | None = None,
        marbl_ic_filepath: str | Path | None = None,
    ):
        """
        Configure the boundary conditions and tides for the MOM6 case.

        Sets up initial and boundary condition forcing data for MOM6 using a specified product
        and download function. Optionally configures tidal constituents if specified. Supports
        a large data workflow mode that defers data download and processing to an external script.

        Parameters
        ----------
        date_range : list of str
            Start and end dates for the forcing data, formatted as strings.
            Must contain exactly two elements.
        boundaries : list of str, optional
            List of open boundaries to process (e.g., ["south", "north"]).
            Default is ["south", "north", "west", "east"].
        tidal_constituents : list of str, optional
            List of tidal constituents (e.g., ["M2", "S2"]) to be used for tidal forcing.
            If provided, both TPXO elevation and velocity file paths must also be provided.
        tpxo_elevation_filepath : str or Path, optional
            File path to the TPXO tidal elevation data file.
        tpxo_velocity_filepath : str or Path, optional
            File path to the TPXO tidal velocity data file.
        product_name : str, optional
            Name of the forcing data product to use. Default is "GLORYS".
        function_name : str, optional
            Name of the function to call for downloading the raw forcing data.
            Default is "get_glorys_data_script_for_cli".
        product_info: str | Path | dict, optional
            The equivalent MOM6 names to Product Names. Example:  xh -> lat time -> valid_time salinity -> salt, as well as any other information required for product parsing
            The `None` option assumes the information is in raw_data_access/config under {product_name}.json. Every other option is copied there.
        too_much_data : bool, optional
            If True, configures the large data workflow. In this case, data are not downloaded
            immediately, but a config file and workflow directory are created
            for external processing in the forcing directory, inside the input directory.
        chl_processed_filepath : Path
            If passed, points to the processed global chlorophyll file for regional processing through mom6_bathy.chl
        runoff_esmf_mesh_filepath : Path
            If passed, points to the processed global runoff file for mapping through mom6_bathy.mapping
        raw_data_path : str or Path, optional
            If passed, a path to the directory where raw output data is stored. This is used instead to extract OBCs and ICs for the case.
        global_river_nutrients_filepath: str or Path, optional
            If passed, points to the processed global river nutrients file for regional processing through mom6_bathy.mapping
        marbl_ic_filepath: str or Path, optional
            If passed, points to the processed MARBL initial condition file to be copied into the case input directory
        Raises
        ------
        TypeError
            If inputs such as `date_range`, `boundaries`, or `tidal_constituents` are not lists of strings.
        ValueError
            If `date_range` does not have exactly two elements, or if tidal arguments are inconsistently specified.
            Also raised if an invalid product or function is provided.
        AssertionError
            If the selected data product is not categorized as a forcing product.

        Notes
        -----
        - Creates an `regional_mom6.experiment` instance with the specified domain and inputs.
        - Downloads forcing data (or creates a script) for each boundary and the initial condition unless the large data workflow is used.
        - In large data workflow mode, creates a folder structure and `config.json` file for later manual processing.
        - Tidal forcing requires all of: `tidal_constituents`, `tpxo_elevation_filepath`, and `tpxo_velocity_filepath`.
        - This method must be called before `process_forcings()`.

        See Also
        --------
        process_forcings : Executes the actual boundary, initial condition, and tide setup based on the configuration.
        """

        self.forcing_product_name = product_name.lower()
        if product_info != None:
            self.ProductFunctionRegistry.add_product_config(
                product_name, product_info=product_info
            )
        if raw_data_path is not None and product_name.upper().startswith("CESM_OUTPUT"):
            self.configure_cesm_initial_and_boundary_conditions(
                input_path=raw_data_path,
                date_range=date_range,
                boundaries=boundaries,
                too_much_data=too_much_data,
            )
        elif product_name.upper() == "GLORYS":
            self.configure_initial_and_boundary_conditions(
                date_range=date_range,
                boundaries=boundaries,
                product_name=product_name,
                function_name=function_name,
                too_much_data=too_much_data,
            )
        else:
            raise ValueError("Product / Data Path is not supported quite yet")
        if tidal_constituents:
            self.configured_tides = self.configure_tides(
                tidal_constituents,
                tpxo_elevation_filepath,
                tpxo_velocity_filepath,
                boundaries,
            )
        else:
            self.configured_tides = False
        if chl_processed_filepath:
            self.configured_chl = self.configure_chl(chl_processed_filepath)
        else:
            self.configured_chl = False
        if self.runoff_in_compset:
            self.configured_runoff = self.configure_runoff(runoff_esmf_mesh_filepath)
        else:
            self.configured_runoff = False

        if global_river_nutrients_filepath:
            self.configured_river_nutrients = self.configure_river_nutrients(
                global_river_nutrients_filepath
            )
        else:
            self.configured_river_nutrients = False

        if self.bgc_in_compset:
            self.configure_bgc_ic(marbl_ic_filepath)
            self.configured_bgc = self.configure_bgc_iron_forcing()
        else:
            self.configured_bgc = False

        self._update_forcing_variables()
        self._configure_forcings_called = True

    def configure_bgc_ic(self, marbl_ic_filepath: str | Path | None = None):
        if marbl_ic_filepath is None:
            raise ValueError("MARBL initial condition file path must be provided.")
        if Path(marbl_ic_filepath).exists() is False:
            raise FileNotFoundError(
                f"MARBL initial condition file {marbl_ic_filepath} does not exist."
            )
        self.marbl_ic_filepath = Path(marbl_ic_filepath)
        self.marbl_ic_filename = self.marbl_ic_filepath.name
        return True

    def configure_bgc_iron_forcing(self):
        self.feventflux_filepath = (
            self.inputdir
            / "ocnice"
            / f"feventflux_5gmol_{self.ocn_grid.name}_{cvars['MB_ATTEMPT_ID'].value}.nc"
        )
        self.fesedflux_filepath = (
            self.inputdir
            / "ocnice"
            / f"fesedflux_total_reduce_oxic_{self.ocn_grid.name}_{cvars['MB_ATTEMPT_ID'].value}.nc"
        )
        return True

    def configure_cesm_initial_and_boundary_conditions(
        self,
        input_path: str | Path,
        date_range: list[str],
        boundaries: list[str] = ["south", "north", "west", "east"],
        too_much_data: bool = False,
    ):
        """
        Configure CESM OBC and ICs from previous CESM output
        """
        self.boundaries = boundaries

        if too_much_data:
            self._large_data_workflow_called = True

        self.date_range = pd.to_datetime(date_range)
        # Create the forcing directory
        if self.override is True:
            forcing_dir_path = self.inputdir / self.forcing_product_name
            if forcing_dir_path.exists():
                shutil.rmtree(forcing_dir_path)
        forcing_dir_path.mkdir(exist_ok=False)

        # Generate Boundary Info
        boundary_info = dv.get_rectangular_segment_info(self.ocn_grid)

        # Create the OBC generation files
        self.large_data_workflow_path = (
            self.inputdir
            / self.forcing_product_name
            / "cesm_output_extract_obc_workflow"
        )

        # Copy large data workflow folder there
        shutil.copytree(
            Path(__file__).parent / "extract_obc",
            self.large_data_workflow_path,
        )

        # Set Vars for Config
        date_format = "%Y%m%d"

        with open(self.large_data_workflow_path / "config.json", "r") as f:
            config = json.load(f)
        config["paths"]["input_path"] = str(input_path)
        config["paths"]["supergrid_path"] = self.supergrid_path
        config["paths"]["bathymetry_path"] = self.topo_path
        config["paths"]["vgrid_path"] = self.vgrid_path
        config["paths"]["subset_input_path"] = str(
            self.large_data_workflow_path / "subsetted_data"
        )
        config["paths"]["regrid_path"] = str(
            self.large_data_workflow_path / "regridded_data"
        )
        config["paths"]["output_path"] = str(self.inputdir / "ocnice")
        config["dates"]["start"] = self.date_range[0].strftime(date_format)
        config["dates"]["end"] = self.date_range[1].strftime(date_format)
        config["dates"]["format"] = date_format
        config["cesm_information"] = self.ProductFunctionRegistry.load_product_config(
            self.forcing_product_name.lower()
        )
        config["general"]["boundary_number_conversion"] = {
            item: idx + 1 for idx, item in enumerate(self.boundaries)
        }

        # Write out
        with open(self.large_data_workflow_path / "config.json", "w") as f:
            json.dump(config, f, indent=4)
        if self._large_data_workflow_called:
            print(
                f"Large data workflow was called, please go to the large data workflow path: {self.large_data_workflow_path} and run the driver script there."
            )

    def configure_initial_and_boundary_conditions(
        self,
        date_range: list[str],
        boundaries: list[str] = ["south", "north", "west", "east"],
        product_name: str = "GLORYS",
        function_name: str = "get_glorys_data_script_for_cli",
        too_much_data: bool = False,
    ):
        assert (
            tb.category_of_product(product_name) == "forcing"
        ), "Data product must be a forcing product"

        if not self.ProductFunctionRegistry.validate_function(
            product_name, function_name
        ):
            raise ValueError("Selected Product or Function was not valid")
        self.forcing_product_name = product_name.lower()
        if not (
            isinstance(date_range, list)
            and all(isinstance(date, str) for date in date_range)
        ):
            raise TypeError("date_range must be a list of strings.")
        if len(date_range) != 2:
            raise ValueError("date_range must have exactly two elements.")

        if not isinstance(boundaries, list):
            raise TypeError("boundaries must be a list of strings.")
        if not all(isinstance(boundary, str) for boundary in boundaries):
            raise TypeError("boundaries must be a list of strings.")
        self.boundaries = boundaries

        if too_much_data:
            self._large_data_workflow_called = True

        self.date_range = pd.to_datetime(date_range)
        # Create the forcing directory
        if self.override is True:
            forcing_dir_path = self.inputdir / self.forcing_product_name
            if forcing_dir_path.exists():
                shutil.rmtree(forcing_dir_path)
        forcing_dir_path.mkdir(exist_ok=False)
        # Generate Boundary Info
        boundary_info = dv.get_rectangular_segment_info(self.ocn_grid)

        # Create the OBC generation files
        self.large_data_workflow_path = (
            self.inputdir / self.forcing_product_name / "large_data_workflow"
        )

        # Copy large data workflow folder there
        shutil.copytree(
            Path(__file__).parent / "raw_data_access" / "large_data_workflow",
            self.large_data_workflow_path,
        )

        # Set Vars for Config
        date_format = "%Y%m%d"
        session_id = cvars["MB_ATTEMPT_ID"].value

        # Write Config File

        # Read in template
        if not self._large_data_workflow_called:
            step = (self.date_range[1] - self.date_range[0]).days + 1
        else:
            step = 5

        with open(self.large_data_workflow_path / "config.json", "r") as f:
            config = json.load(f)
        config["paths"]["hgrid_path"] = self.supergrid_path
        config["paths"]["vgrid_path"] = self.vgrid_path
        config["paths"]["raw_dataset_path"] = str(
            self.large_data_workflow_path / "raw_data"
        )
        config["paths"]["regridded_dataset_path"] = str(
            self.large_data_workflow_path / "regridded_data"
        )
        config["paths"]["merged_dataset_path"] = str(self.inputdir / "ocnice")
        config["dates"]["start"] = self.date_range[0].strftime(date_format)
        config["dates"]["end"] = self.date_range[1].strftime(date_format)
        config["dates"]["format"] = date_format
        config["forcing"]["product_name"] = self.forcing_product_name.upper()
        config["forcing"]["function_name"] = function_name
        config["forcing"]["varnames"] = (
            self.ProductFunctionRegistry.load_product_config(
                self.forcing_product_name.lower()
            )
        )
        config["boundary_number_conversion"] = {
            item: idx + 1 for idx, item in enumerate(self.boundaries)
        }
        config["params"]["step"] = step

        # Write out
        with open(self.large_data_workflow_path / "config.json", "w") as f:
            json.dump(config, f, indent=4)
        if not self._large_data_workflow_called:
            # This means we start to run the driver right away, the get dataset piecewise option.
            sys.path.append(str(self.large_data_workflow_path))
            import driver

            driver.main(regrid_dataset_piecewise=False, merge_piecewise_dataset=False)
        else:
            print(
                f"Large data workflow was called, please go to the large data workflow path: {self.large_data_workflow_path} and run the driver script there."
            )

    def configure_river_nutrients(self, global_river_nutrients_filepath: str | Path):
        if not (self.bgc_in_compset and self.runoff_in_compset):
            raise ValueError(
                "River Nutrients can only be turned on if both BGC and Runoff are in the compset!"
            )
        self.global_river_nutrients_filepath = Path(global_river_nutrients_filepath)
        self.river_nutrients_nnsm_filepath = (
            self.inputdir
            / "ocnice"
            / f"river_nutrients_{self.ocn_grid.name}_{cvars['MB_ATTEMPT_ID'].value}_nnsm.nc"
        )
        return True

    def configure_runoff(self, runoff_esmf_mesh_filepath: str | Path | None = None):
        if self.runoff_in_compset and (runoff_esmf_mesh_filepath is None):
            self.runoff_esmf_mesh_filepath = False
            raise ValueError(
                "Runoff ESMF Mesh File and Global Runoff file must be provided for mapping"
            )
        elif (runoff_esmf_mesh_filepath is not None) and not self.runoff_in_compset:
            self.runoff_esmf_mesh_filepath = False
            raise ValueError("Runoff can only be turned on if it is in the compset!")
        elif self.runoff_in_compset and (runoff_esmf_mesh_filepath is not None):
            self.runoff_esmf_mesh_filepath = runoff_esmf_mesh_filepath

        # Set runoff mapping file path
        self.runoff_mapping_file_nnsm = (
            self.inputdir
            / "ocnice"
            / f"glofas_{self.ocn_grid.name}_{cvars['MB_ATTEMPT_ID'].value}_nnsm.nc"
        )
        return True

    def configure_tides(
        self,
        tidal_constituents: list[str] | None = None,
        tpxo_elevation_filepath: str | Path | None = None,
        tpxo_velocity_filepath: str | Path | None = None,
        boundaries: list[str] = ["south", "north", "west", "east"],
    ):
        if tidal_constituents:
            if not isinstance(tidal_constituents, list):
                raise TypeError("tidal_constituents must be a list of strings.")
            if not all(
                isinstance(constituent, str) for constituent in tidal_constituents
            ):
                raise TypeError("tidal_constituents must be a list of strings.")

        self.tidal_constituents = tidal_constituents
        # all tidal arguments must be provided if any are provided
        if any([tidal_constituents, tpxo_elevation_filepath, tpxo_velocity_filepath]):
            if not all(
                [tidal_constituents, tpxo_elevation_filepath, tpxo_velocity_filepath]
            ):
                raise ValueError(
                    "If any tidal arguments are provided, all must be provided."
                )
        self.tidal_constituents = tidal_constituents
        self.tpxo_elevation_filepath = (
            Path(tpxo_elevation_filepath) if tpxo_elevation_filepath else None
        )
        self.tpxo_velocity_filepath = (
            Path(tpxo_velocity_filepath) if tpxo_velocity_filepath else None
        )
        session_id = cvars["MB_ATTEMPT_ID"].value

        self.expt = rmom6.experiment(
            date_range=("1850-01-01 00:00:00", "1851-01-01 00:00:00"),  # Dummy times
            resolution=None,
            number_vertical_layers=None,
            layer_thickness_ratio=None,
            depth=self.ocn_topo.max_depth,
            mom_run_dir=self._cime_case.get_value("RUNDIR"),
            mom_input_dir=self.inputdir / "ocnice",
            hgrid_type="from_file",
            hgrid_path=self.supergrid_path,
            vgrid_type="from_file",
            vgrid_path=self.vgrid_path,
            minimum_depth=self.ocn_topo.min_depth,
            tidal_constituents=self.tidal_constituents,
            expt_name=self.caseroot.name,
            boundaries=boundaries,
        )
        return True

    def configure_chl(self, chl_processed_filepath: str | Path):
        self.chl_processed_filepath = (
            Path(chl_processed_filepath) if chl_processed_filepath else None
        )
        self.regional_chl_file_path = (
            self.inputdir / "ocnice" / f"seawifs-clim-1997-2010-{self.ocn_grid.name}.nc"
        )
        return True

    def process_forcings(
        self,
        process_initial_condition=True,
        process_tides=True,
        process_velocity_tracers=True,
        process_bgc=True,
        process_chl=True,
        process_runoff=True,
        process_river_nutrients=True,
    ):
        """
        Process boundary conditions, initial conditions, and tides for a MOM6 case.

        This method configures a regional MOM6 case's ocean state boundaries and initial conditions
        using previously downloaded data setup in configure_forcings. It also processes tidal boundary conditions
        if tidal constituents are specified. The method expects `configure_forcings()` to be
        called beforehand.

        Parameters
        ----------
        process_initial_condition : bool, optional
            Whether to process the initial condition file. Default is True.
        process_tides : bool, optional
            Whether to process tidal boundary conditions. Default is True.
        process_chl : bool, optional
            Whether to process chlorophyll data. Default is True.
        process_velocity_tracers : bool, optional
            Whether to process velocity and tracer boundary conditions. Default is True.
            This will be overridden and set to False if the large data workflow in configure_forcings is enabled.
        process_runoff : bool, optional
            Whether to process runoff data. Default is True.
        process_bgc : bool, optional
            Whether to process BGC data. Default is True.

        Raises
        ------
        RuntimeError
            If `configure_forcings()` was not called before this method.
        FileNotFoundError
            If required unprocessed files are missing in the expected directories.

        Notes
        -----
        - This method uses variable name mappings specified in the forcing product configuration.
        - If the large data workflow has been enabled, velocity and tracer OBCs are not processed
          within this method and must be handled externally.
        - If tidal constituents are configured, TPXO elevation and velocity files must be available.
        - Applies forcing-related namelist and XML updates at the end of the method.

        See Also
        --------
        configure_forcings : Must be called before this method to set up the environment.
        """
        if not self._configure_forcings_called:
            raise RuntimeError(
                "configure_forcings() must be called before process_forcings()."
            )
        if self.forcing_product_name.upper().startswith("CESM_OUTPUT"):
            self.process_cesm_initial_and_boundary_conditions(
                process_initial_condition, process_velocity_tracers
            )
        else:
            self.process_initial_and_boundary_conditions(
                process_initial_condition, process_velocity_tracers
            )
        if self.configured_bgc and process_bgc:
            self.process_bgc_iron_forcing()
            self.process_bgc_ic()
        if self.configured_tides and process_tides:
            self.process_tides()
        if self.configured_chl and process_chl:
            self.process_chl()
        if self.configured_runoff and process_runoff:
            self.process_runoff()
        if self.configured_river_nutrients and process_river_nutrients:
            self.process_river_nutrients()
        print(f"Case is ready to be built: {self.caseroot}")

    def process_bgc_ic(self):
        dest_path = self.inputdir / "ocnice" / Path(self.marbl_ic_filepath).name
        shutil.copy(self.marbl_ic_filepath, dest_path)

    def process_bgc_iron_forcing(self):
        # Create coordinate variables
        nx = self.ocn_grid.nx
        ny = self.ocn_grid.ny
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
        ds.to_netcdf(self.fesedflux_filepath)
        ds.to_netcdf(self.feventflux_filepath)

    def process_cesm_initial_and_boundary_conditions(
        self,
        process_initial_condition=True,
        process_velocity_tracers=True,
    ):
        if self._large_data_workflow_called and (
            process_velocity_tracers or process_initial_condition
        ):
            process_velocity_tracers = False
            process_initial_condition = False
            print(
                f"Large data workflow was called, so boundary & initial conditions will not be processed."
            )
            print(
                f"Please make sure to execute large_data_workflow as described in {self.large_data_workflow_path}"
            )

        # Set up the initial condition & boundary conditions

        with open(self.large_data_workflow_path / "config.json", "r") as f:
            config = json.load(f)
        if process_initial_condition:
            config["general"]["run_initial_condition"] = True
        else:
            config["general"]["run_initial_condition"] = False
        if process_velocity_tracers:
            config["general"]["run_boundary_conditions"] = True
        else:
            config["general"]["run_boundary_conditions"] = False
        with open(self.large_data_workflow_path / "config.json", "w") as f:
            json.dump(config, f, indent=4)

        if process_initial_condition or process_velocity_tracers:
            sys.path.append(str(self.large_data_workflow_path))
            import eo_driver

            eo_driver.extract_obcs(config)

    def process_tides(self):
        # Process the tides
        if self.tidal_constituents:

            # Process the tides
            self.expt.setup_boundary_tides(
                tpxo_elevation_filepath=self.tpxo_elevation_filepath,
                tpxo_velocity_filepath=self.tpxo_velocity_filepath,
                tidal_constituents=self.tidal_constituents,
            )

    def process_chl(self):
        # Process the chlorophyll file if it is provided
        if self.chl_processed_filepath is not None:
            if not self.chl_processed_filepath.exists():
                raise FileNotFoundError(
                    f"Chlorophyll file {self.chl_processed_filepath} does not exist."
                )

            chl.interpolate_and_fill_seawifs(
                self.ocn_grid,
                self.ocn_topo,
                self.chl_processed_filepath,
                self.regional_chl_file_path,
            )

    def process_river_nutrients(self):
        if (
            self.bgc_in_compset
            and self.runoff_in_compset
            and self.global_river_nutrients_filepath is not None
        ):
            if not self.global_river_nutrients_filepath.exists():
                raise FileNotFoundError(
                    f"River Nutrients file {self.global_river_nutrients_filepath} does not exist."
                )
            # Process the river nutrients file
            self.river_nutrients_filepath = (
                self.inputdir / "ocnice" / f"river-nutrients-{self.ocn_grid.name}.nc"
            )

            # Open Dataset & Create Regridder
            global_river_nutrients = xr.open_dataset(
                self.global_river_nutrients_filepath
            )
            global_river_nutrients = global_river_nutrients.assign_coords(
                lon=((global_river_nutrients.lon + 360) % 360)
            )
            global_river_nutrients = global_river_nutrients.sortby("lon")
            grid_t_points = xr.Dataset()
            grid_t_points["lon"] = self.ocn_grid.tlon
            grid_t_points["lat"] = self.ocn_grid.tlat
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
                filename=self.runoff_mapping_file_nnsm,
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
                global_river_nutrients[v] = (
                    global_river_nutrients[v] * conversion_factor
                )
                global_river_nutrients[v].attrs["units"] = "mmol/cm^2/s"

            print("Regridding river nutrients...")
            river_nutrients_remapped = regridder(global_river_nutrients)

            # Write out
            print("Writing out river nutrients...")
            # new time value as cftime
            new_time_val = cftime.DatetimeNoLeap(1900, 1, 1, 0, 0, 0)

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
            time_calendar = "noleap"
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

            # Change nx,ny to lon,lat
            river_nutrients_remapped_cleaned = (
                river_nutrients_remapped_cleaned.rename_dims({"nx": "lon", "ny": "lat"})
            )

            # set CF-compliant attrs
            river_nutrients_remapped_cleaned["time"].attrs.update(
                {
                    "units": time_units,
                    "calendar": "noleap",
                    "long_name": "time",
                }
            )

            # encoding only for data vars
            encoding = {
                var: {"_FillValue": np.NaN}
                for var in river_nutrients_remapped_cleaned.data_vars
            }

            river_nutrients_remapped_cleaned.to_netcdf(
                self.river_nutrients_nnsm_filepath,
                encoding=encoding,
                unlimited_dims=["time"],
            )

    def process_runoff(self):
        if self.runoff_in_compset and self.runoff_esmf_mesh_filepath:
            if not self.runoff_mapping_file_nnsm.exists():
                print("Creating runoff mapping file(s)...")
                mapping.gen_rof_maps(
                    rof_mesh_path=self.runoff_esmf_mesh_filepath,
                    ocn_mesh_path=self.esmf_mesh_path,
                    output_dir=self.inputdir / "ocnice",
                    mapping_file_prefix=f'glofas_{self.ocn_grid.name}_{cvars["MB_ATTEMPT_ID"].value}',
                    rmax=100.0,
                    fold=100.0,
                )
            else:
                print(
                    f"Runoff mapping file {self.runoff_mapping_file_nnsm} already exists, reusing it."
                )

    def process_initial_and_boundary_conditions(
        self, process_initial_condition, process_velocity_tracers
    ):

        if self._large_data_workflow_called and (
            process_velocity_tracers or process_initial_condition
        ):
            process_velocity_tracers = False
            process_initial_condition = False
            print(
                f"Large data workflow was called, so boundary & initial conditions will not be processed."
            )
            print(
                f"Please make sure to execute large_data_workflow as described in {self.large_data_workflow_path}"
            )

        # check all the boundary files are present:
        if (
            process_initial_condition
            and not (
                self.large_data_workflow_path / "raw_data" / "ic_unprocessed.nc"
            ).exists()
        ):
            raise FileNotFoundError(
                f"Initial condition file ic_unprocessed.nc not found in {self.large_data_workflow_path/'raw_data' }. "
                "Please make sure to execute get_glorys_data.sh script as described in "
                "the message printed by configure_forcings()."
            )

        for boundary in self.boundaries:
            if process_velocity_tracers and not any(
                (self.large_data_workflow_path / "raw_data").glob(
                    f"{boundary}_unprocessed*.nc"
                )
            ):
                raise FileNotFoundError(
                    f"Boundary file {boundary}_unprocessed.nc not found in {self.large_data_workflow_path / 'raw_data'}. "
                    "Please make sure to execute get_glorys_data.sh script as described in "
                    "the message printed by configure_forcings()."
                )

        # Set up the initial condition & boundary conditions

        with open(self.large_data_workflow_path / "config.json", "r") as f:
            config = json.load(f)
        if process_initial_condition:
            config["params"]["run_initial_condition"] = True
        else:
            config["params"]["run_initial_condition"] = False
        if process_velocity_tracers:
            config["params"]["run_boundary_conditions"] = True
        else:
            config["params"]["run_boundary_conditions"] = False
        with open(self.large_data_workflow_path / "config.json", "w") as f:
            json.dump(config, f, indent=4)

        if process_initial_condition or process_velocity_tracers:
            sys.path.append(str(self.large_data_workflow_path))
            import driver

            driver.main(
                get_dataset_piecewise=False,
                regrid_dataset_piecewise=True,
                merge_piecewise_dataset=True,
            )

    @property
    def name(self) -> str:
        return self.caseroot.name

    def _initialize_visualCaseGen(self):

        ConfigVar.reboot()
        Stage.reboot()
        initialize_configvars(self.cime)
        initialize_widgets(self.cime)
        initialize_stages(self.cime)
        set_options(self.cime)
        csp.initialize(cvars, get_relational_constraints(cvars), Stage.first())

    def _configure_standard_compset(self, compset: str):
        """Configure the case for a standard component set."""

        assert Stage.active().title == "1. Component Set"
        cvars["COMPSET_MODE"].value = "Standard"

        assert Stage.active().title == "Support Level"
        cvars["SUPPORT_LEVEL"].value = "All"

        # Apply filters
        for comp_class in self.cime.comp_classes:
            cvars[f"COMP_{comp_class}_FILTER"].value = "any"

        ## Pick a standard compset
        cvars["COMPSET_ALIAS"].value = compset

    def _configure_custom_compset(self, compset: str):
        """Configure the case for a custom component set by setting individual component variables,
        which occurs in 4 stages:
          1. Time Period
          2. Models (e.g. cam, cice, mom6, etc.)
          3. Model Physics (e.g. CAM60, MOM6, etc.)
          4. Physics Options (i.e., modifiers for the physics, e.g. %JRA, %MARBL-BIO, etc.)
        """

        assert Stage.first().enabled
        cvars["COMPSET_MODE"].value = "Custom"

        # Stage: Time Period
        assert Stage.active().title.startswith("Time Period")
        inittime = compset.split("_")[0]
        cvars["INITTIME"].value = inittime

        # Generate a mapping from physics to models, e.g., "CAM60" -> "cam"
        phys_to_model = {}
        for model, phys_list in self.cime.comp_phys.items():
            for phys in phys_list:
                phys_to_model[phys] = model

        # Split the compset into components
        components = self.cime.get_components_from_compset_lname(compset)

        # Stage: Components (i.e., models, e.g., cam, cice, mom6, etc.)
        assert Stage.active().title.startswith("Components")
        for comp_class, phys in components.items():
            phys = phys.split("%")[0]  # Get the physics part
            if phys not in phys_to_model:
                raise ValueError(f"Model physics {phys} not found.")
            model = phys_to_model[phys]
            cvars[f"COMP_{comp_class}"].value = model

        # Stage: Model Physics (e.g, CAM60, MOM6, etc.)
        if Stage.active().title.startswith("Component Physics"):
            for comp_class, phys in components.items():
                phys = phys.split("%")[0]  # Get the physics part
                cvars[f"COMP_{comp_class}_PHYS"].value = phys
        else:
            # Physics and/or Options stages may be auto-completed if each chosen model has
            # exactly one physics and modifier option (though, this is unlikely).
            assert Stage.active().title.startswith(
                "Component Options"
            ) or Stage.active().title.startswith("2. Grid")

        # Stage: Component Physics Options (i.e., modifiers for the physics, e.g. %JRA, %MARBL-BIO, etc.)
        if Stage.active().title.startswith("Component Options"):
            for comp_class, phys in components.items():
                opt = phys.split("%")[1] if "%" in phys else None
                if opt is not None:
                    cvars[f"COMP_{comp_class}_OPTION"].value = opt
                else:
                    cvars[f"COMP_{comp_class}_OPTION"].value = "(none)"

        # Confirm successful configuration of custom component set
        assert Stage.active().title == "2. Grid"

    def _assign_configvars(self, compset, machine, project):
        """Assign the configvars (i.e., configuration variables for the case, such as components, physics,
        options, grids, etc.) The cvars dict is a visualCaseGen data structure that contains all the
        configuration variables for a case to be created. Incrementally setting configvars leads to the
        completion of successive stages in the visualCaseGen workflow and thus enables the creation of
        a new case.
        """

        # 1. Compset
        if compset in self.cime.compsets:
            self._configure_standard_compset(compset)
        else:
            self._configure_custom_compset(compset)

        # 2. Grid
        assert Stage.active().title == "2. Grid"
        cvars["GRID_MODE"].value = "Custom"

        assert Stage.active().title == "Custom Grid"
        cvars["CUSTOM_GRID_PATH"].value = self.inputdir.as_posix()

        assert Stage.active().title == "Ocean Grid Mode"
        cvars["OCN_GRID_MODE"].value = "Create New"

        assert Stage.active().title == "Custom Ocean Grid"
        cvars["OCN_GRID_EXTENT"].value = "Regional"
        cvars["OCN_CYCLIC_X"].value = "False"
        cvars["OCN_NX"].value = self.ocn_grid.nx
        cvars["OCN_NY"].value = self.ocn_grid.ny
        cvars["OCN_LENX"].value = (
            self.ocn_grid.tlon.max().item() - self.ocn_grid.tlon.min().item()
        )
        cvars["OCN_LENY"].value = (
            self.ocn_grid.tlat.max().item() - self.ocn_grid.tlat.min().item()
        )
        cvars["CUSTOM_OCN_GRID_NAME"].value = self.ocn_grid.name
        cvars["MB_ATTEMPT_ID"].value = str(uuid.uuid1())[:6]
        cvars["MOM6_BATHY_STATUS"].value = "Complete"
        if Stage.active().title == "Custom Ocean Grid":
            Stage.active().proceed()

        assert Stage.active().title == "New Ocean Grid Initial Conditions"
        cvars["OCN_IC_MODE"].value = "From File"

        assert Stage.active().title == "Initial Conditions from File"
        cvars["TEMP_SALT_Z_INIT_FILE"].value = "TBD"
        cvars["IC_PTEMP_NAME"].value = "TBD"
        cvars["IC_SALT_NAME"].value = "TBD"

        # 3. Grid
        assert Stage.active().title == "3. Launch"
        cvars["CASEROOT"].value = self.caseroot.as_posix()
        cvars["MACHINE"].value = machine
        if project is not None:
            cvars["PROJECT"].value = project

        # Variables that are not included in a stage:
        cvars["NINST"].value = self.ninst

    def _update_forcing_variables(self):
        """Update the runtime parameters of the case."""

        # Initial conditions:
        ic_params = [
            ("INIT_LAYERS_FROM_Z_FILE", "True"),
            ("Z_INIT_ALE_REMAPPING", True),
            ("TEMP_SALT_INIT_VERTICAL_REMAP_ONLY", True),
            ("DEPRESS_INITIAL_SURFACE", True),
            ("VELOCITY_CONFIG", "file"),
        ]
        if not self.forcing_product_name.upper().startswith("CESM_OUTPUT"):
            ic_params.extend(
                [
                    ("TEMP_SALT_Z_INIT_FILE", "init_tracers.nc"),
                    ("SURFACE_HEIGHT_IC_FILE", "init_eta.nc"),
                    ("SURFACE_HEIGHT_IC_VAR", "eta_t"),
                    ("VELOCITY_FILE", "init_vel.nc"),
                    ("Z_INIT_FILE_PTEMP_VAR", "temp"),
                ]
            )

        else:
            ic_params.extend(
                [
                    ("TEMP_Z_INIT_FILE", "TEMP_IC.nc"),
                    ("SALT_Z_INIT_FILE", "SALT_IC.nc"),
                    ("Z_INIT_FILE_PTEMP_VAR", "TEMP"),
                    ("Z_INIT_FILE_SALT_VAR", "SALT"),
                    ("SURFACE_HEIGHT_IC_FILE", "SSH_IC.nc"),
                    ("SURFACE_HEIGHT_IC_VAR", "SSH"),
                    ("VELOCITY_FILE", "VEL_IC.nc"),
                    ("U_IC_VAR", "UVEL"),
                    ("V_IC_VAR", "VVEL"),
                ]
            )

        append_user_nl(
            "mom",
            ic_params,
            do_exec=True,
            comment="Initial conditions",
        )

        # BGC
        if self.bgc_in_compset:
            bgc_params = [
                ("MAX_FIELDS", "200"),
                ("MARBL_FESEDFLUX_FILE", self.fesedflux_filepath),
                ("MARBL_FEVENTFLUX_FILE", self.feventflux_filepath),
                ("MARBL_TRACERS_IC_FILE", self.marbl_ic_filename),
            ]

            # Runoff & River Fluxes
            if self.configured_river_nutrients:
                bgc_params.extend(
                    [
                        ("READ_RIV_FLUXES", "True"),
                        ("RIV_FLUX_FILE", self.river_nutrients_nnsm_filepath),
                    ]
                )
            else:
                bgc_params.extend([("READ_RIV_FLUXES", "False")])
            append_user_nl(
                "mom",
                bgc_params,
                do_exec=True,
                comment="BGC Params",
                log_title=False,
            )

        # Tides
        if self.configured_tides:
            tidal_params = [
                ("TIDES", "True"),
                ("TIDE_M2", "True"),
                ("CD_TIDES", 0.0018),
                ("TIDE_USE_EQ_PHASE", "True"),
                (
                    "TIDE_REF_DATE",
                    f"{self.date_range[0].year}, {self.date_range[0].month}, {self.date_range[0].day}",
                ),
                ("OBC_TIDE_ADD_EQ_PHASE", "True"),
                ("OBC_TIDE_N_CONSTITUENTS", len(self.tidal_constituents)),
                (
                    "OBC_TIDE_CONSTITUENTS",
                    '"' + ", ".join(self.tidal_constituents) + '"',
                ),
                (
                    "OBC_TIDE_REF_DATE",
                    f"{self.date_range[0].year}, {self.date_range[0].month}, {self.date_range[0].day}",
                ),
            ]
            append_user_nl(
                "mom",
                tidal_params,
                do_exec=True,
                comment="Tides",
                log_title=False,
            )

        # Chlorophyll
        if self.configured_chl:
            chl_params = [
                ("CHL_FILE", Path(self.regional_chl_file_path).name),
                ("CHL_FROM_FILE", "TRUE"),
                ("VAR_PEN_SW", "TRUE"),
                ("PEN_SW_NBANDS", 3),
            ]
            append_user_nl(
                "mom",
                chl_params,
                do_exec=True,
                comment="Chlorophyll Climatology",
                log_title=False,
            )

        # Open boundary conditions (OBC):
        obc_params = [
            ("OBC_NUMBER_OF_SEGMENTS", len(self.boundaries)),
            ("OBC_FREESLIP_VORTICITY", "False"),
            ("OBC_FREESLIP_STRAIN", "False"),
            ("OBC_COMPUTED_VORTICITY", "True"),
            ("OBC_COMPUTED_STRAIN", "True"),
            ("OBC_ZERO_BIHARMONIC", "True"),
            ("OBC_TRACER_RESERVOIR_LENGTH_SCALE_OUT", "3.0E+04"),
            ("OBC_TRACER_RESERVOIR_LENGTH_SCALE_IN", "3000.0"),
            ("BRUSHCUTTER_MODE", "True"),
        ]

        # More OBC parameters:
        for seg in self.boundaries:
            seg_ix = str(self.find_MOM6_rectangular_orientation(seg)).zfill(
                3
            )  # "001", "002", etc.
            seg_id = "OBC_SEGMENT_" + seg_ix

            # Position and config
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
            obc_params.append(
                (
                    seg_id,
                    index_str + ',FLATHER,ORLANSKI,NUDGED,ORLANSKI_TAN,NUDGED_TAN"',
                )
            )

            # Nudging
            obc_params.append((seg_id + "_VELOCITY_NUDGING_TIMESCALES", "0.3, 360.0"))
            bgc_tracers = ""
            if not self.forcing_product_name.upper().startswith("CESM_OUTPUT"):
                standard_data_str = lambda: (
                    f'"U=file:forcing_obc_segment_{seg_ix}.nc(u),'
                    f"V=file:forcing_obc_segment_{seg_ix}.nc(v),"
                    f"SSH=file:forcing_obc_segment_{seg_ix}.nc(eta),"
                    f"TEMP=file:forcing_obc_segment_{seg_ix}.nc(temp),"
                    f"SALT=file:forcing_obc_segment_{seg_ix}.nc(salt)"
                )
            else:

                product_info = self.ProductFunctionRegistry.load_product_config(
                    self.forcing_product_name
                )

                standard_data_str = lambda: (
                    f"\"U=file:{product_info['u']}_obc_segment_{seg_ix}.nc({product_info['u']}),"
                    f"V=file:{product_info['v']}_obc_segment_{seg_ix}.nc({product_info['v']}),"
                    f"SSH=file:{product_info['ssh']}_obc_segment_{seg_ix}.nc({product_info['ssh']}),"
                    f"TEMP=file:{product_info['tracers']['temp']}_obc_segment_{seg_ix}.nc({product_info['tracers']['temp']}),"
                    f"SALT=file:{product_info['tracers']['salt']}_obc_segment_{seg_ix}.nc({product_info['tracers']['salt']})"
                )

                for tracer_mom6_name in product_info["tracers"]:
                    if tracer_mom6_name != "temp" and tracer_mom6_name != "salt":
                        bgc_tracers += f',{tracer_mom6_name}=file:{product_info["tracers"][tracer_mom6_name]}_obc_segment_{seg_ix}.nc({product_info["tracers"][tracer_mom6_name]})'
            tidal_data_str = lambda: (
                f",Uamp=file:tu_segment_{seg_ix}.nc(uamp),"
                f"Uphase=file:tu_segment_{seg_ix}.nc(uphase),"
                f"Vamp=file:tu_segment_{seg_ix}.nc(vamp),"
                f"Vphase=file:tu_segment_{seg_ix}.nc(vphase),"
                f"SSHamp=file:tz_segment_{seg_ix}.nc(zamp),"
                f"SSHphase=file:tz_segment_{seg_ix}.nc(zphase)"
            )
            if self.configured_tides:
                obc_params.append(
                    (
                        seg_id + "_DATA",
                        standard_data_str() + tidal_data_str() + bgc_tracers + '"',
                    )
                )
            else:
                obc_params.append(
                    (seg_id + "_DATA", standard_data_str() + bgc_tracers + '"')
                )

        append_user_nl(
            "mom",
            obc_params,
            do_exec=True,
            comment="Open boundary conditions",
            log_title=False,
        )
        if self.cice_in_compset:
            cice_param = [
                ("ice_ic", "'UNSET'"),
                ("ns_boundary_type", "'open'"),
                ("ew_boundary_type", "'cyclic'"),
                ("close_boundaries", ".false."),
            ]
            append_user_nl(
                "cice",
                cice_param,
                do_exec=True,
                comment="CICE options",
                log_title=False,
            )

        if self.runoff_in_compset and self.configured_runoff:

            xmlchange(
                "ROF2OCN_LIQ_RMAPNAME",
                str(self.runoff_mapping_file_nnsm),
                is_non_local=self.cc._is_non_local(),
            )
            xmlchange(
                "ROF2OCN_ICE_RMAPNAME",
                str(self.runoff_mapping_file_nnsm),
                is_non_local=self.cc._is_non_local(),
            )

        xmlchange(
            "RUN_STARTDATE",
            str(self.date_range[0])[:10],
            is_non_local=self.cc._is_non_local(),
        )

        self.date_range = pd.to_datetime(self.date_range)
        xmlchange(
            "STOP_OPTION",
            "ndays",
            is_non_local=self.cc._is_non_local(),
        )
        xmlchange(
            "STOP_N",
            (self.date_range[1] - self.date_range[0]).days,
            is_non_local=self.cc._is_non_local(),
        )

    def find_MOM6_rectangular_orientation(self, input):
        """
        Convert between MOM6 boundary and the specific segment number needed, or the inverse.
        """

        direction_dir = {}
        counter = 1
        for b in self.boundaries:
            direction_dir[b] = counter
            counter += 1
        direction_dir_inv = {v: k for k, v in direction_dir.items()}
        merged_dict = {**direction_dir, **direction_dir_inv}
        try:
            val = merged_dict[input]
        except KeyError:
            raise ValueError(
                "Invalid direction or segment number for MOM6 rectangular orientation"
            )
        return val
