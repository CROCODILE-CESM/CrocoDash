from pathlib import Path
import uuid
import shutil
from datetime import datetime
import json
import pandas as pd
import regional_mom6 as rmom6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.forcing_configurations.base import ForcingConfigRegistry
from CrocoDash.raw_data_access.registry import ProductRegistry
from ProConPy.config_var import ConfigVar, cvars
from ProConPy.stage import Stage
from ProConPy.dev_utils import ConstraintViolation
from visualCaseGen.initialize import initialize as initialize_visualCaseGen
from visualCaseGen.custom_widget_types.case_creator import CaseCreator, ERROR, RESET
from visualCaseGen.custom_widget_types.case_tools import xmlchange
from mom6_forge import chl, mapping
import xesmf as xe
import xarray as xr
import numpy as np
import cftime

from CrocoDash import case_state


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
        atm_grid_name: str = "TL319",
        rof_grid_name: str | None = None,
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
        atm_grid_name : str, optional
            The atmosphere grid name of the case. Default is "TL319".
        rof_grid_name : str | None, optional
            The runoff grid name of the case. Default is None.
            If None, it will be set according to the compset. If multiple
            options are available, the user will be prompted to select one.
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

        # Capture scalar init args for state serialization before any local vars are added.
        _locals = locals()
        self._init_args = {
            k: v for k, v in _locals.items() if k not in case_state.INIT_ARGS_EXCLUDE
        }

        # Initialize visualCaseGen system and get the CIME interface
        self.cime = initialize_visualCaseGen(cesmroot)

        # Determine compset alias and long name
        if compset in self.cime.compsets:
            compset_alias = compset
            compset_lname = self.cime.compsets[compset].lname
        else:
            compset_alias = None
            compset_lname = compset

        # Sanity checks on the input arguments
        Case.init_args_check(
            cime=self.cime,
            caseroot=caseroot,
            inputdir=inputdir,
            ocn_grid=ocn_grid,
            ocn_topo=ocn_topo,
            ocn_vgrid=ocn_vgrid,
            compset_lname=compset_lname,
            atm_grid_name=atm_grid_name,
            rof_grid_name=rof_grid_name,
            ninst=ninst,
            machine=machine,
            project=project,
            override=override,
            ntasks_ocn=ntasks_ocn,
            job_queue=job_queue,
            job_wallclock_time=job_wallclock_time,
        )

        # Set instance attributes from arguments, in argument order
        self.cesmroot = Path(cesmroot)
        self.caseroot = Path(caseroot)
        self.inputdir = Path(inputdir)
        self.ocn_grid = ocn_grid
        self.ocn_topo = ocn_topo
        self.ocn_vgrid = ocn_vgrid
        self.atm_grid_name = atm_grid_name
        self.rof_grid_name = rof_grid_name
        self.ninst = ninst
        self.machine = machine or self.cime.machine
        self.project = project
        self.override = override
        self.ntasks_ocn = ntasks_ocn
        self.job_queue = job_queue
        self.job_wallclock_time = job_wallclock_time

        # Derived from compset argument
        self.compset_alias = compset_alias
        self.compset_lname = compset_lname

        # Internal state (not from arguments)
        self.ProductRegistry = ProductRegistry
        self.forcing_product_name = None
        self._configure_forcings_called = False

        # Using visualCaseGen's configuration system, set the configuration variables for the case
        # based on the provided arguments. This includes setting the compset, grid, and launch variables.
        try:
            self._configure_case(atm_grid_name, rof_grid_name)
        except Exception as e:
            print(f"\n{ERROR}Case Configuration Error:{RESET}")
            print(f"  {str(e)}")
            return

        # Before creating the case, we need to create the grid input files (except for mapping files,
        # which will be created later in process_forcings if needed).
        self._create_grid_input_files()

        # Having set the configuration variables and created the grid input files, we can now create the case instance.
        self._create_newcase()

        # After creating the case, instantiate the CIME case object for later use.
        self._cime_case = self.cime.get_case(
            self.caseroot, non_local=self.cc._is_non_local()
        )

        self.is_non_local = self.cc._is_non_local()

        self._apply_final_xmlchanges(ntasks_ocn, job_queue, job_wallclock_time)

        self._write_state()

        required_configurators = ForcingConfigRegistry.find_required_configurators(
            self.compset_lname
        )

        if len(required_configurators) > 0:
            print(
                "The following additional configuration options are required to run and must be provided with any listed arguments in configure_forcings:"
            )

            for configurator in required_configurators:
                user_args = ForcingConfigRegistry.get_user_args(configurator)
                args_str = ", ".join(user_args) if user_args else "no arguments"
                print(f"  - {configurator.name}: {args_str}")

    @property
    def cice_in_compset(self):
        """Check if CICE is included in the compset."""
        return "CICE" in self.compset_lname

    @property
    def ww3_in_compset(self):
        """Check if WW3 is included in the compset."""
        return "WW3" in self.compset_lname

    @property
    def runoff_in_compset(self):
        """Check if runoff is included in the compset."""
        return "SROF" not in self.compset_lname

    @property
    def bgc_in_compset(self):
        """Check if BGC is included in the compset."""
        return "%MARBL" in self.compset_lname

    @classmethod
    def init_args_check(
        cls,
        *,
        cime,
        caseroot: str | Path,
        inputdir: str | Path,
        ocn_grid: Grid,
        ocn_topo: Topo,
        ocn_vgrid: VGrid,
        compset_lname: str,
        atm_grid_name: str,
        rof_grid_name: str | None,
        ninst: int,
        machine: str | None,
        project: str | None,
        override: bool,
        ntasks_ocn: int | None = None,
        job_queue: str | None = None,
        job_wallclock_time: str | None = None,
    ):
        """Perform sanity checks on the input arguments to ensure they are valid and consistent."""

        if Path(caseroot).exists() and not override:
            raise ValueError(f"Given caseroot {caseroot} already exists!")
        if Path(inputdir).exists() and not override:
            raise ValueError(f"Given inputdir {inputdir} already exists!")
        if not isinstance(ocn_grid, Grid):
            raise TypeError("ocn_grid must be a Grid object.")
        if not isinstance(ocn_vgrid, VGrid):
            raise TypeError("ocn_vgrid must be a VGrid object.")
        if not isinstance(compset_lname, str) or len(compset_lname) == 0:
            raise TypeError("compset must be a non-empty string.")
        assert (
            compset_lname.count("_") >= 6
        ), "compset must be a valid CESM compset long name or alias."
        assert (
            "MOM6" in compset_lname
        ), "In CrocoDash, only MOM6-based compsets are supported."
        assert "SLND" in compset_lname, (
            "Currently, active or data land models are not supported by CrocoDash."
            "Please use a compset with SLND."
        )
        assert "SGLC" in compset_lname, (
            "Currently, active or data glacier models are not supported by CrocoDash."
            "Please use a compset with SGLC."
        )
        assert "DWAV" not in compset_lname, (
            "Currently, data wave models (DWAV) are not supported by CrocoDash. "
            "Please use a compset with SWAV or WW3."
        )
        if not isinstance(ocn_topo, Topo):
            raise TypeError("ocn_topo must be a Topo object.")
        if atm_grid_name not in (available_atm_grids := cime.domains["atm"].keys()):
            raise ValueError(f"atm_grid_name must be one of {available_atm_grids}.")
        if rof_grid_name is not None:
            assert "SROF" not in compset_lname, (
                "When a runoff grid is specified, "
                "the compset must include an active or data runoff model."
            )
            if rof_grid_name not in (available_rof_grids := cime.domains["rof"].keys()):
                raise ValueError(f"rof_grid_name must be one of {available_rof_grids}.")
        if ocn_grid.name is None:
            raise ValueError(
                "ocn_grid must have a name. Please set it using the 'name' attribute."
            )
        if ocn_grid.name in cime.domains["ocnice"] and not override:
            raise ValueError(f"ocn_grid name {ocn_grid.name} is already in use.")
        if not isinstance(ninst, int):
            raise TypeError("ninst must be an integer.")
        if machine is None:
            raise ValueError(
                "Couldn't determine machine. Please provide the machine argument."
            )
        if not isinstance(machine, str):
            raise TypeError("machine must be a string.")
        if not machine in cime.machines:
            raise ValueError(f"machine must be one of {cime.machines}.")
        if cime.project_required[machine] is True:
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

        ocnice = inputdir / "ocnice"
        ocnice.mkdir()

        # suffix for the MOM6 grid files
        session_id = cvars["MB_ATTEMPT_ID"].value
        suffix = f"{ocn_grid.name}_{session_id}"

        # MOM6 supergrid file
        self.supergrid_path = str(ocnice / f"ocean_hgrid_{suffix}.nc")
        ocn_grid.write_supergrid(self.supergrid_path)

        # MOM6 topography file
        self.topo_path = str(ocnice / f"ocean_topog_{suffix}.nc")
        ocn_topo.write_topo(self.topo_path)

        # MOM6 vertical grid file
        self.vgrid_path = str(ocnice / f"ocean_vgrid_{suffix}.nc")
        ocn_vgrid.write(self.vgrid_path)

        # SCRIP grid file (needed for runoff remapping)
        ocn_topo.write_scrip_grid(ocnice / f"scrip_{suffix}.nc")

        # ESMF mesh file:
        self.esmf_mesh_path = str(ocnice / f"ESMF_mesh_{suffix}.nc")
        ocn_topo.write_esmf_mesh(self.esmf_mesh_path)

        # CICE grid file (if needed)
        if self.cice_in_compset:
            self.ocn_topo.write_cice_grid(ocnice / f"cice_grid_{suffix}.nc")

        # WW3 grid file (if needed)
        if self.ww3_in_compset:
            self.ocn_topo.write_ww3_input(ocnice, grid_alias=ocn_grid.name)

    def _create_newcase(self):
        """Create the case instance."""
        # If override is True, clean up the existing caseroot and output directories
        if self.override is True:
            if self.caseroot.exists():
                shutil.rmtree(self.caseroot)
            if (Path(self.cime.cime_output_root) / self.caseroot.name).exists():
                shutil.rmtree(Path(self.cime.cime_output_root) / self.caseroot.name)

        if not self.caseroot.parent.exists():
            self.caseroot.parent.mkdir(parents=True, exist_ok=False)

        self.cc = CaseCreator(
            self.cime, allow_xml_override=self.override, add_grids_to_ccs_config=False
        )

        try:
            self.cc.create_case(do_exec=True)
        except Exception as e:
            print(f"{ERROR}{str(e)}{RESET}")
            self.cc.revert_launch(do_exec=True)

    def configure_forcings(
        self,
        date_range: list[str],
        boundaries: list[str] = ["south", "north", "west", "east"],
        product_name: str = "GLORYS",
        function_name: str = "get_glorys_data_script_for_cli",
        **kwargs,
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
        product_name : str, optional
            Name of the forcing data product to use. Default is "GLORYS".
        function_name : str, optional
            Name of the function to call for downloading the forcing data.
            Default is "get_glorys_data_script_for_cli".
        product_info: str | Path | dict, optional
            The equivalent MOM6 names to Product Names. Example:  xh -> lat time -> valid_time salinity -> salt, as well as any other information required for product parsing
            The `None` option assumes the information is in raw_data_access/config under {product_name}.json. Every other option is copied there.
        kwargs :
            These are the configuration options (please see accepted arguments in the configuration classes)
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
        - Downloads forcing data (or creates a script) for each boundary and the initial condition unless the large data workflow is used.
        - In large data workflow mode, creates a folder structure and `config.json` file for later manual processing.
        - This method must be called before `process_forcings()`.

        See Also
        --------
        process_forcings : Executes the actual boundary, initial condition, and tide setup based on the configuration.
        """

        # Set up Forcings Folder
        self.extract_forcings_path = self.inputdir / "extract_forcings"
        if self.override is True:
            if self.extract_forcings_path.exists():
                shutil.rmtree(self.extract_forcings_path)
        self.extract_forcings_path.mkdir(parents=True, exist_ok=True)

        # Validate date_range's raw shape and set case-level state. Everything else
        # (boundaries/product_name validity, IC/OBC user_nl params, config.json
        # "conditions" entry) is handled by ConditionsConfigurator's validate_args()/
        # configure() (see forcing_configurations/configurations.py).
        if not (
            isinstance(date_range, list)
            and all(isinstance(date, str) for date in date_range)
        ):
            raise TypeError("date_range must be a list of strings.")
        if len(date_range) != 2:
            raise ValueError("date_range must have exactly two elements.")

        self.forcing_product_name = product_name.lower()
        self.boundaries = boundaries
        self.date_range = pd.to_datetime(date_range)

        inputs = kwargs | {
            "date_range": pd.to_datetime(date_range),
            "boundaries": boundaries,
            "product_name": product_name,
            "function_name": function_name,
        }

        self.session_id = cvars["MB_ATTEMPT_ID"].value
        self.grid_name = self.ocn_grid.name

        config_path = self.extract_forcings_path / "config.json"
        with open(config_path, "w") as f:
            json.dump({"caseroot": str(self.caseroot)}, f, indent=4)

        self.fcr = ForcingConfigRegistry(self.compset_lname, inputs, self)
        self.fcr.run_configurators(config_path)

        xmlchange(
            "RUN_STARTDATE",
            str(self.date_range[0])[:10],
            is_non_local=self.cc._is_non_local(),
        )
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
        self._configure_forcings_called = True

    def process_forcings(
        self, process_initial_condition=True, process_velocity_tracers=True, **kwargs
    ):
        """
        Process boundary conditions, initial conditions, and other forcings for a MOM6 case. It's a wrapper around extract_forcings/case_setup/driver.py

        This method configures a regional MOM6 case's ocean state boundaries and initial conditions
        using previously downloaded data setup in configure_forcings. The method expects `configure_forcings()` to be
        called beforehand.

        Parameters
        ----------
        process_initial_condition : bool, optional
            Whether to process the initial condition file. Default is True.
        process_velocity_tracers : bool, optional
            Whether to process velocity and tracer boundary conditions. Default is True.
            This will be overridden and set to False if the large data workflow in configure_forcings is enabled.
        kwargs : bool, optional
            Whether to process the other forcings, of the form process_{configurator.name} = False

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
        - Applies forcing-related namelist and XML updates at the end of the method.

        See Also
        --------
        configure_forcings : Must be called before this method to set up the environment.
        """
        if not self._configure_forcings_called:
            raise RuntimeError(
                "configure_forcings() must be called before process_forcings()."
            )

        process_bgc = kwargs.get("process_bgc", True)
        process_tides = kwargs.get("process_tides", True)
        process_chl = kwargs.get("process_chl", True)
        process_runoff = kwargs.get("process_runoff", True)
        process_bgc_river_nutrients = kwargs.get("process_bgc_river_nutrients", True)

        from CrocoDash.extract_forcings.driver import run_workflow

        run_workflow(
            config_path=self.extract_forcings_path / "config.json",
            ic=process_initial_condition,
            bc=process_velocity_tracers,
            bgcic=process_bgc and self.fcr.is_active("bgc"),
            bgcironforcing=process_bgc and self.fcr.is_active("bgc"),
            tides=process_tides and self.fcr.is_active("tides"),
            chl_=process_chl and self.fcr.is_active("chl"),
            runoff=process_runoff and self.fcr.is_active("runoff"),
            bgcrivernutrients=process_bgc_river_nutrients
            and self.fcr.is_active("BGCRiverNutrients"),
        )

        print(f"Case is ready to be built: {self.caseroot}")

    @property
    def name(self) -> str:
        return self.caseroot.name

    @property
    def expt(self) -> rmom6.experiment:

        if not hasattr(self, "date_range"):
            print("Date not found so using a dummy date of 1850-1851")
            date_range = ("1850-01-01 00:00:00", "1851-01-01 00:00:00")  # Dummy times
        else:
            date_range = tuple(
                ts.strftime("%Y-%m-%d %H:%M:%S") for ts in self.date_range
            )
        if not hasattr(self, "boundaries"):
            print("Boundaries not found so using default")
            self.boundaries = ["north", "south", "east", "west"]
        if not hasattr(self, "tidal_constituents"):
            print("tidal_constituents not found so using only M2")
            self.tidal_constituents = ["M2"]

        expt = rmom6.experiment(
            date_range=date_range,
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
        expt.hgrid = self.ocn_grid.supergrid.to_ds()
        # expt.vgrid = self.ocn_vgrid.gen_vgrid_ds() # Not implemented yet
        return expt

    def _configure_case(self, atm_grid_name, rof_grid_name):
        """Using visualCaseGen's case configuration pipeline, set the variables for the case based
        on the provided arguments. This includes setting the compset, grid, and launch variables.
        """

        # 1. Compset
        if self.compset_alias is not None:
            self._configure_standard_compset(self.compset_alias)
        else:
            self._configure_custom_compset(self.compset_lname)

        # 2. Grid
        self._configure_custom_grid(atm_grid_name, rof_grid_name)

        # 3. Launch
        self._configure_launch()

    def _configure_standard_compset(self, compset_alias: str):
        """Configure the case for a standard component set."""

        assert Stage.active().title == "1. Component Set"
        cvars["COMPSET_MODE"].value = "Standard"

        assert Stage.active().title == "Support Level"
        cvars["SUPPORT_LEVEL"].value = "All"

        # Apply filters
        for comp_class in self.cime.comp_classes:
            cvars[f"COMP_{comp_class}_FILTER"].value = "any"

        ## Pick a standard compset by alias
        cvars["COMPSET_ALIAS"].value = compset_alias

    def _configure_custom_compset(self, compset_lname: str):
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
        inittime = compset_lname.split("_")[0]
        cvars["INITTIME"].value = inittime

        # Generate a mapping from physics to models, e.g., "CAM60" -> "cam"
        phys_to_model = {}
        for model, phys_list in self.cime.comp_phys.items():
            for phys in phys_list:
                phys_to_model[phys] = model

        # Split the compset_lname into components
        components = self.cime.get_components_from_compset_lname(compset_lname)

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

    def _configure_custom_grid(self, atm_grid_name, rof_grid_name):
        """Assign the custom grid variables for the case."""

        # 2. Grid
        assert Stage.active().title == "2. Grid"
        cvars["GRID_MODE"].value = "Custom"

        assert Stage.active().title == "Custom Grid"
        cvars["CUSTOM_GRID_PATH"].value = self.inputdir.as_posix()

        self._configure_custom_atmosphere_grid(atm_grid_name)
        self._configure_custom_ocean_grid()
        self._configure_custom_runoff_grid(rof_grid_name)
        self._configure_custom_wave_grid()

    def _configure_custom_atmosphere_grid(self, atm_grid_name):
        """Configure the atmosphere grid for the case. To be called by _configure_custom_grid()"""

        # Check if we are in the Atmosphere Grid stage. If so, that means there are multiple (or no) options for
        # the atm grid name. In that case, we need to check if the atm_grid_name is provided and valid.
        # If not, raise an error. If specified, then we can just set the atm grid name to the provided value.
        if Stage.active().title == "Atmosphere Grid":
            if not atm_grid_name:
                atm_grid_options = cvars["CUSTOM_ATM_GRID"].valid_options
                raise ValueError(
                    f"Atmosphere grid name (atm_grid_name) must be provided.\n  Valid options are: {atm_grid_options}"
                )
            cvars["CUSTOM_ATM_GRID"].value = atm_grid_name

        # If we are not in the Atmosphere Grid stage, that means atmosphere grid name is already set to the only
        # valid option available. In that case, check if the provided atm_grid_name is same as the valid option.
        elif atm_grid_name is not None:
            valid_atm_grid_name = cvars["CUSTOM_ATM_GRID"].value
            if atm_grid_name != valid_atm_grid_name:
                raise ValueError(
                    f"Based on the compset, the valid atmosphere grid name is {valid_atm_grid_name}, but got {atm_grid_name}."
                )

    def _configure_custom_ocean_grid(self):
        """Configure the ocean grid for the case. To be called by _configure_custom_grid()"""

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

    def _configure_custom_runoff_grid(self, rof_grid_name):
        """Configure the runoff grid for the case. To be called by _configure_custom_grid()"""

        # Check if we are in the Runoff Grid stage. If so, that means there are multiple (or no) options for
        # the rof grid name. In that case, we need to check if the rof_grid_name is provided and valid.
        # If not, raise an error. If specified, then we can just set the rof grid name to the provided value.
        if Stage.active().title == "Runoff Grid":
            if rof_grid_name is None:
                rof_grid_options = cvars["CUSTOM_ROF_GRID"].valid_options
                raise ValueError(
                    f"Runoff grid name (rof_grid_name) must be provided.\n  Valid options are: {rof_grid_options}"
                )
            cvars["CUSTOM_ROF_GRID"].value = rof_grid_name
        elif rof_grid_name is not None:
            valid_rof_grid_name = cvars["CUSTOM_ROF_GRID"].value
            if rof_grid_name != valid_rof_grid_name:
                raise ValueError(
                    f"Based on the compset, the valid runoff grid name is {valid_rof_grid_name}, but got {rof_grid_name}."
                )
        if Stage.active().title == "Runoff to Ocean Mapping":
            cvars["ROF_OCN_MAPPING_STATUS"].value = (
                "skip"  # to be generated later in process_forcings
            )

    def _configure_custom_wave_grid(self):
        """Configure the wave grid for the case. To be called by _configure_custom_grid().

        Only reached for an active wave model (WW3); for stub waves (SWAV) the Wave Grid
        stages are auto-skipped (irrelevant), this method is a no-op.
        """
        if Stage.active().title == "Wave Grid Mode":
            cvars["WAV_GRID_MODE"].value = "Custom Ocean Grid"
            # The WW3 grid-preprocessor input files are generated separately in
            # _create_grid_input_files() via ocn_topo.write_ww3_input(); mark the
            # input-file generation sub-stage complete so the flow proceeds to Launch.
            assert Stage.active().title == "Wave Input Files"
            cvars["WW3_INPUT_STATUS"].value = "Complete"

    def _configure_launch(self):
        """Assign the launch variables for the case."""

        assert Stage.active().title == "3. Launch"
        cvars["CASEROOT"].value = self.caseroot.as_posix()
        cvars["MACHINE"].value = self.machine
        if self.project is not None:
            cvars["PROJECT"].value = self.project

        # Variables that are not included in a stage:
        cvars["NINST"].value = self.ninst

    def _write_state(self):
        """Write case creation parameters to crocodash_state.json in caseroot."""
        case_state.write(
            self.caseroot,
            {
                # Derived / resolved fields that can't come from init args directly
                "inputdir": str(self.inputdir),
                "cesmroot": str(self.cesmroot),
                "supergrid_path": self.supergrid_path,
                "topo_path": self.topo_path,
                "vgrid_path": self.vgrid_path,
                "grid_name": self.ocn_grid.name,
                "session_id": cvars["MB_ATTEMPT_ID"].value,
                "compset_lname": self.compset_lname,
                "machine": self.machine,
                # Scalar init args captured at construction time
                **self._init_args,
            },
        )

    def _apply_final_xmlchanges(
        self, ntasks_ocn=None, job_queue=None, job_wallclock_time=None
    ):
        """Apply final XML changes after the case has been configured, and before the user
        configures the forcings."""

        xmlchange(
            "MOM6_MEMORY_MODE",
            "dynamic_symmetric",
            is_non_local=self.cc._is_non_local(),
        )

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

    def validate_case(self):

        # Ensure configurations are done
        for name, configurator in self.fcr.active_configurators.items():
            if not configurator.validate_output_filepaths(self.inputdir / "ocnice"):
                print(
                    f"{name} is not valid yet — process this forcing and generate "
                    f"the files using your case's extract_forcings module: "
                    f"{self.inputdir / 'extract_forcings'}"
                )
