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
from mom6_bathy import chl


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
        )

        self.caseroot = Path(caseroot)
        self.inputdir = Path(inputdir)
        self.ocn_grid = ocn_grid
        self.ocn_topo = ocn_topo
        self.ocn_vgrid = ocn_vgrid
        self.ninst = ninst
        self.override = override
        self.ProductFunctionRegistry = dv.ProductFunctionRegistry()
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

        # CICE grid file (if needed)
        if "CICE" in self.compset:
            self.cice_grid_path = (
                inputdir / "ocnice" / f"cice_grid_{ocn_grid.name}_{session_id}.nc"
            )
            ocn_topo.write_cice_grid(self.cice_grid_path)

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
        too_much_data: bool = False,
        chl_processed_filepath: str | Path | None = None,
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
            Name of the function to call for downloading the forcing data.
            Default is "get_glorys_data_script_for_cli".
        too_much_data : bool, optional
            If True, configures the large data workflow. In this case, data are not downloaded
            immediately, but a config file and workflow directory are created
            for external processing in the forcing directory, inside the input directory.

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

        self.configure_initial_and_boundary_conditions(
            date_range=date_range,
            boundaries=boundaries,
            product_name=product_name,
            function_name=function_name,
            too_much_data=too_much_data,
        )
        self.configure_tides(
            tidal_constituents, tpxo_elevation_filepath, tpxo_velocity_filepath
        )
        self.configure_chl(chl_processed_filepath)
        self._configure_forcings_called = True

    def process_forcings(
        self,
        process_initial_condition=True,
        process_tides=True,
        process_velocity_tracers=True,
        process_chl=True,
        process_param_changes=True,
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
        process_param_changes : bool, optional
            Whether to process the namelist and xml changes required to run a regional MOM6 case in the CESM.

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

        self.process_initial_and_boundary_conditions(
            process_initial_condition, process_velocity_tracers
        )
        self.process_tides(process_tides)
        self.process_chl(process_chl)

        # Apply forcing-related namelist and xml changes
        if process_param_changes:
            self._update_forcing_variables()

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

        self.ProductFunctionRegistry.load_functions()
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
        config["dates"]["start"] = date_range[0].strftime(date_format)
        config["dates"]["end"] = date_range[1].strftime(date_format)
        config["dates"]["format"] = date_format
        config["forcing"]["product_name"] = self.forcing_product_name.upper()
        config["forcing"]["function_name"] = function_name
        config["forcing"]["varnames"] = (
            self.ProductFunctionRegistry.forcing_varnames_config[
                self.forcing_product_name.upper()
            ]
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
            date_range=("0001-01-01 00:00:00", "0001-01-01 00:00:00"),
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
            boundaries=self.boundaries,
        )

    def configure_chl(self, chl_processed_filepath: str | Path):
        self.chl_processed_filepath = (
            Path(chl_processed_filepath) if chl_processed_filepath else None
        )

    def process_tides(self, process_tides: bool):
        # Process the tides
        if process_tides and self.tidal_constituents:

            # Process the tides
            self.expt.setup_boundary_tides(
                tpxo_elevation_filepath=self.tpxo_elevation_filepath,
                tpxo_velocity_filepath=self.tpxo_velocity_filepath,
                tidal_constituents=self.tidal_constituents,
            )

    def process_chl(self, process_chl: bool):
        # Process the chlorophyll file if it is provided
        if process_chl and self.chl_processed_filepath is not None:
            if not self.chl_processed_filepath.exists():
                raise FileNotFoundError(
                    f"Chlorophyll file {self.chl_processed_filepath} does not exist."
                )
            # Process the chlorophyll file
            self.regional_chl_file_path = (
                self.inputdir
                / "ocnice"
                / f"seawifs-clim-1997-2010-{self.ocn_grid.name}.nc"
            )
            chl.interpolate_and_fill_seawifs(
                self.ocn_grid,
                self.ocn_topo,
                self.chl_processed_filepath,
                self.regional_chl_file_path,
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
            ("TEMP_SALT_Z_INIT_FILE", "init_tracers.nc"),
            ("Z_INIT_FILE_PTEMP_VAR", "temp"),
            ("Z_INIT_ALE_REMAPPING", True),
            ("TEMP_SALT_INIT_VERTICAL_REMAP_ONLY", True),
            ("DEPRESS_INITIAL_SURFACE", True),
            ("SURFACE_HEIGHT_IC_FILE", "init_eta.nc"),
            ("SURFACE_HEIGHT_IC_VAR", "eta_t"),
            ("VELOCITY_CONFIG", "file"),
            ("VELOCITY_FILE", "init_vel.nc"),
        ]
        append_user_nl(
            "mom",
            ic_params,
            do_exec=True,
            comment="Initial conditions",
        )

        # Tides
        if self.tidal_constituents:
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
        if self.chl_processed_filepath is not None:
            chl_params = [
                ("CHL_FILE", f"seawifs-clim-1997-2010-{self.ocn_grid.name}.nc"),
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
        for seg in self.expt.boundaries:
            seg_ix = str(self.expt.find_MOM6_rectangular_orientation(seg)).zfill(
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

            standard_data_str = lambda: (
                f'"U=file:forcing_obc_segment_{seg_ix}.nc(u),'
                f"V=file:forcing_obc_segment_{seg_ix}.nc(v),"
                f"SSH=file:forcing_obc_segment_{seg_ix}.nc(eta),"
                f"TEMP=file:forcing_obc_segment_{seg_ix}.nc(temp),"
                f"SALT=file:forcing_obc_segment_{seg_ix}.nc(salt)"
            )
            tidal_data_str = lambda: (
                f",Uamp=file:tu_segment_{seg_ix}.nc(uamp),"
                f"Uphase=file:tu_segment_{seg_ix}.nc(uphase),"
                f"Vamp=file:tu_segment_{seg_ix}.nc(vamp),"
                f"Vphase=file:tu_segment_{seg_ix}.nc(vphase),"
                f"SSHamp=file:tz_segment_{seg_ix}.nc(zamp),"
                f"SSHphase=file:tz_segment_{seg_ix}.nc(zphase)"
            )
            if self.tidal_constituents:
                obc_params.append(
                    (seg_id + "_DATA", standard_data_str() + tidal_data_str() + '"')
                )
            else:
                obc_params.append((seg_id + "_DATA", standard_data_str() + '"'))

        append_user_nl(
            "mom",
            obc_params,
            do_exec=True,
            comment="Open boundary conditions",
            log_title=False,
        )

        xmlchange(
            "RUN_STARTDATE",
            str(self.date_range[0])[:10],
            is_non_local=self.cc._is_non_local(),
        )
        xmlchange(
            "MOM6_MEMORY_MODE",
            "dynamic_symmetric",
            is_non_local=self.cc._is_non_local(),
        )

        print(f"Case is ready to be built: {self.caseroot}")
