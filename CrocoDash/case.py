from pathlib import Path
import uuid
import shutil
from datetime import datetime
import json
import importlib.util
import pandas as pd
import regional_mom6 as rmom6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.forcing_configurations import ForcingConfigRegistry
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import ForcingProduct
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
        self.ProductRegistry = ProductRegistry
        self.forcing_product_name = None
        self._configure_forcings_called = False
        self._too_much_data = False
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
                inputdir
                / "ocnice"
                / f"cice_grid_{ocn_grid.name}_{cvars['MB_ATTEMPT_ID'].value}.nc"
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
        product_name: str = "GLORYS",
        function_name: str = "get_glorys_data_script_for_cli",
        too_much_data: bool = False,
        **kwargs
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
        too_much_data : bool, optional
            If True, configures the large data workflow. In this case, data are not downloaded
            immediately, but a config file and workflow directory are created
            for external processing in the forcing directory, inside the input directory.
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
        ProductRegistry.load()
        self.forcing_product_name = product_name.lower()
        if (
            ProductRegistry.product_exists(product_name)
            and ProductRegistry.product_is_of_type(product_name,ForcingProduct)
        ):
            self.configure_initial_and_boundary_conditions(
                date_range=date_range,
                boundaries=boundaries,
                product_name=product_name,
                function_name=function_name,
                too_much_data=too_much_data,
            )
        else:
            raise ValueError("Product / Data Path is not supported quite yet")
        
        inputs = kwargs | {
            "date_range": date_range,
            "grid_name": self.ocn_grid.name,
            "session_id": cvars["MB_ATTEMPT_ID"].value,
        }
        ForcingConfigRegistry.find_active_configurators(self.compset, inputs)
        ForcingConfigRegistry.run_configurators()

        self._update_forcing_variables()
        self._configure_forcings_called = True

    def configure_initial_and_boundary_conditions(
        self,
        date_range: list[str],
        boundaries: list[str] = ["south", "north", "west", "east"],
        product_name: str = "GLORYS",
        function_name: str = "get_glorys_data_script_for_cli",
        too_much_data: bool = False,
    ):
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
        self._too_much_data = too_much_data
        self.date_range = pd.to_datetime(date_range)
        
        # Create the forcing directory
        forcing_dir_path = self.inputdir / self.forcing_product_name
        if self.override is True:
            if forcing_dir_path.exists():
                shutil.rmtree(forcing_dir_path)
        forcing_dir_path.mkdir(exist_ok=True)

        # Create the OBC generation files
        self.extract_forcings_path = (
            self.inputdir / self.forcing_product_name / "extract_forcings"
        )

        # Copy large data workflow folder there
        shutil.copytree(
            Path(__file__).parent / "extract_forcings",
            self.extract_forcings_path,
        )

        # Set Vars for Config
        date_format = "%Y%m%d"

        # Write Config File

        # Read in template
        if not self._too_much_data:
            step = (self.date_range[1] - self.date_range[0]).days + 1
        else:
            step = 5

        with open(self.extract_forcings_path / "config.json", "r") as f:
            config = json.load(f)

        # Paths
        config["paths"]["hgrid_path"] = self.supergrid_path
        config["paths"]["vgrid_path"] = self.vgrid_path
        config["paths"]["bathymetry_path"] = self.topo_path
        config["paths"]["raw_dataset_path"] = str(
            self.extract_forcings_path / "raw_data"
        )
        config["paths"]["regridded_dataset_path"] = str(
            self.extract_forcings_path / "regridded_data"
        )
        config["paths"]["output_path"] = str(self.inputdir / "ocnice")

        # Regex never changes!

        # Dates
        config["dates"]["start"] = self.date_range[0].strftime(date_format)
        config["dates"]["end"] = self.date_range[1].strftime(date_format)
        config["dates"]["format"] = date_format

        # Product Information
        config["forcing"]["product_name"] = self.forcing_product_name.upper()
        config["forcing"]["function_name"] = function_name
        config["forcing"]["information"] = ProductRegistry.get_product(self.forcing_product_name.lower()).write_metadata(include_marbl_tracers=self.bgc_in_compset)
        

        # General
        config["general"]["boundary_number_conversion"] = {
            item: idx + 1 for idx, item in enumerate(self.boundaries)
        }
        config["general"]["step"] = step

        # Write out
        with open(self.extract_forcings_path / "config.json", "w") as f:
            json.dump(config, f, indent=4)

        # Import Extract Forcings Workflow
        module_name = f"driver_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(
            module_name, self.extract_forcings_path / "driver.py"
        )
        self.driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.driver)

        if not self._too_much_data:
            self.driver.main(
                regrid_dataset_piecewise=False, merge_piecewise_dataset=False
            )
        else:
            print(
                f"Extract Forcings workflow was called, please go to the extract forcings path: {self.extract_forcings_path} and run the driver script there."
            )

    def process_forcings(
        self,
        process_initial_condition=True,
        process_velocity_tracers=True,
        **kwargs
    ):
        """
        Process boundary conditions, initial conditions, and other forcings for a MOM6 case.

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

        self.process_initial_and_boundary_conditions(
            process_initial_condition, process_velocity_tracers
        )

        
        if ForcingConfigRegistry.is_active("bgc") and process_bgc:
            self.process_bgc_iron_forcing()
            self.process_bgc_ic()
        if ForcingConfigRegistry.is_active("tides") and process_tides:
            self.process_tides()
        if ForcingConfigRegistry.is_active("chl") and process_chl:
            self.process_chl()
        if ForcingConfigRegistry.is_active("runoff") and process_runoff:
            self.process_runoff()
        if ForcingConfigRegistry.is_active("BGCRiverNutrients") and process_river_nutrients:
            self.process_river_nutrients()
        print(f"Case is ready to be built: {self.caseroot}")

    def process_bgc_ic(self):
        dest_path = self.inputdir / "ocnice" / Path(ForcingConfigRegistry["bgc"].marbl_ic_filepath).name
        shutil.copy(ForcingConfigRegistry["bgc"].marbl_ic_filepath, dest_path)

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
        ds.to_netcdf(self.inputdir / "ocnice" /ForcingConfigRegistry["BGCIronForcing"].fesedflux_filepath)
        ds.to_netcdf(self.inputdir / "ocnice" /ForcingConfigRegistry["BGCIronForcing"].feventflux_filepath)

    def process_tides(self):
        self.expt.setup_boundary_tides(
            tpxo_elevation_filepath=ForcingConfigRegistry["tides"].tpxo_elevation_filepath,
            tpxo_velocity_filepath=ForcingConfigRegistry["tides"].tpxo_velocity_filepath,
            tidal_constituents=ForcingConfigRegistry["tides"].tidal_constituents,
        )

    def process_chl(self):       
        chl.interpolate_and_fill_seawifs(
            self.ocn_grid,
            self.ocn_topo,
            ForcingConfigRegistry["chl"].chl_processed_filepath,
            ForcingConfigRegistry["chl"].regional_chl_file_path,
        )

    def process_river_nutrients(self):
           
            # Open Dataset & Create Regridder
            global_river_nutrients = xr.open_dataset(
                ForcingConfigRegistry["bgcrivernutrients"].global_river_nutrients_filepath
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
                filename=ForcingConfigRegistry["runoff"].runoff_mapping_file_nnsm,
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
                ForcingConfigRegistry["bgcrivernutrients"].river_nutrients_nnsm_filepath,
                encoding=encoding,
                unlimited_dims=["time"],
            )

    def process_runoff(self):
            if not (self.inputdir / "ocnice"/ForcingConfigRegistry["runoff"].runoff_mapping_file_nnsm).exists():
                print("Creating runoff mapping file(s)...")
                mapping.gen_rof_maps(
                    rof_mesh_path=ForcingConfigRegistry["runoff"].runoff_esmf_mesh_filepath,
                    ocn_mesh_path=ForcingConfigRegistry["runoff"].esmf_mesh_path,
                    output_dir=self.inputdir / "ocnice",
                    mapping_file_prefix=ForcingConfigRegistry['runoff'].runoff_mapping_file_nnsm,
                    rmax=ForcingConfigRegistry['runoff'].rmax,
                    fold=ForcingConfigRegistry['runoff'].fold,
                )
            else:
                print(
                    f"Runoff mapping file {ForcingConfigRegistry['runoff'].runoff_mapping_file_nnsm} already exists, reusing it."
                )

    def process_initial_and_boundary_conditions(
        self, process_initial_condition, process_velocity_tracers
    ):

        if self._too_much_data and (
            process_velocity_tracers or process_initial_condition
        ):
            process_velocity_tracers = False
            process_initial_condition = False
            print(
                f"Large data workflow was called, so boundary & initial conditions will not be processed."
            )
            print(
                f"Please make sure to execute large_data_workflow as described in {self.extract_forcings_path}"
            )

        if process_initial_condition or process_velocity_tracers:
            self.driver.main(
                get_dataset_piecewise=False,
                regrid_dataset_piecewise=True,
                merge_piecewise_dataset=True,
            )

    @property
    def name(self) -> str:
        return self.caseroot.name

    @property 
    def expt(self) -> rmom6.experiment:
        
        if not hasattr(self, "date_range"):
            print("Date not found so using a dummy date of 1850-1851")
            date_range = ("1850-01-01 00:00:00", "1851-01-01 00:00:00")  # Dummy times
        else:
            date_range = tuple(ts.strftime("%Y-%m-%d %H:%M:%S") for ts in self.date_range)
        if not hasattr(self, "boundaries"):
            print("Boundaries not found so using default")
            self.boundaries =  ["north", "south", "east", "west"]
        if not hasattr(self, "tidal_constituents"):
            print("tidal_constituents not found so using only M2")
            self.tidal_constituents =  ["M2"]

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
        expt.hgrid = self.ocn_grid.gen_supergrid_ds()
        # expt.vgrid = self.ocn_vgrid.gen_vgrid_ds() # Not implemented yet
        return expt


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
            ("TEMP_SALT_Z_INIT_FILE", "init_tracers.nc"),
            ("SURFACE_HEIGHT_IC_FILE", "init_eta.nc"),
            ("VELOCITY_FILE", "init_vel.nc"),
            ("Z_INIT_FILE_PTEMP_VAR", "temp"),
            ("Z_INIT_FILE_SALT_VAR", "salt"),
            ("SURFACE_HEIGHT_IC_VAR", "eta_t"),
            ("U_IC_VAR", "u"),
            ("V_IC_VAR", "v"),
        ]

        append_user_nl(
            "mom",
            ic_params,
            do_exec=True,
            comment="Initial conditions",
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
            standard_data_str = lambda: (
                f'"U=file:forcing_obc_segment_{seg_ix}.nc(u),'
                f"V=file:forcing_obc_segment_{seg_ix}.nc(v),"
                f"SSH=file:forcing_obc_segment_{seg_ix}.nc(eta),"
                f"TEMP=file:forcing_obc_segment_{seg_ix}.nc(temp),"
                f"SALT=file:forcing_obc_segment_{seg_ix}.nc(salt)"
            )
            if ForcingConfigRegistry.is_active("bgc"):

                product_info = ProductRegistry.get_product(self.forcing_product_name.lower()).marbl_var_names
                for tracer_mom6_name in product_info:
                    bgc_tracers += f',{tracer_mom6_name}=file:forcing_obc_segment_{seg_ix}.nc({product_info["tracer_var_names"][tracer_mom6_name]})'


            if ForcingConfigRegistry.is_active("tides"):
                obc_params.append(
                    (
                        seg_id + "_DATA",
                        standard_data_str() +  ForcingConfigRegistry.active_configurators["tides"].tidal_data_str(seg_ix) + bgc_tracers + '"',
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
