from pathlib import Path
import uuid
import shutil
from datetime import datetime
import json

import regional_mom6 as rmom6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.data_access import driver as dv
from CrocoDash.data_access import driver as dv
from CrocoDash.data_access import config as tb
from ProConPy.config_var import ConfigVar, cvars
from ProConPy.stage import Stage
from ProConPy.csp_solver import csp
from visualCaseGen.cime_interface import CIME_interface
from visualCaseGen.initialize_configvars import initialize_configvars
from visualCaseGen.initialize_widgets import initialize_widgets
from visualCaseGen.initialize_stages import initialize_stages
from visualCaseGen.specs.options import set_options
from visualCaseGen.specs.relational_constraints import get_relational_constraints
from visualCaseGen.custom_widget_types.case_creator import CaseCreator, ERROR, RESET
from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl


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
        ocn_grid: Grid,
        ocn_topo: Topo,
        ocn_vgrid: VGrid,
        inittime: str = "1850",
        datm_mode: str = "JRA",
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
        ocn_grid : Grid
            The ocean grid object to be used in the case.
        ocn_topo : Topo
            The ocean topography object to be used in the case.
        ocn_vgrid : VGrid
            The ocean vertical grid object to be used in the case.
        inittime : str, optional
            The initialization time of the case. Default is "1850".
        datm_mode : str, optional
            The data atmosphere mode of the case. Default is "JRA".
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
            inittime,
            datm_mode,
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

        # Construct the compset long name
        self.compset = f"{inittime}_DATM%{datm_mode}_SLND_SICE_MOM6_SROF_SGLC_SWAV_SESP"
        # Resolution name:
        self.resolution = f"{datm_grid_name}_{ocn_grid.name}"

        self._initialize_visualCaseGen()

        self._assign_configvar_values(inittime, datm_mode, machine, project)

        self._create_grid_input_files()

        self._create_newcase()

        self._cime_case = self.cime.get_case(self.caseroot)

    def _init_args_check(
        self,
        caseroot: str | Path,
        inputdir: str | Path,
        ocn_grid: Grid,
        ocn_topo: Topo,
        ocn_vgrid: VGrid,
        inittime: str,
        datm_mode: str,
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
        if inittime not in ["1850", "2000", "HIST"]:
            raise ValueError("inittime must be one of ['1850', '2000', 'HIST'].")
        if datm_mode not in (available_datm_modes := self.cime.comp_options["DATM"]):
            raise ValueError(f"datm_mode must be one of {available_datm_modes}.")
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

        # MOM6 supergrid file
        ocn_grid.write_supergrid(
            inputdir / "ocnice" / f"ocean_hgrid_{ocn_grid.name}_{session_id}.nc"
        )

        # MOM6 topography file
        ocn_topo.write_topo(
            inputdir / "ocnice" / f"ocean_topog_{ocn_grid.name}_{session_id}.nc"
        )

        # MOM6 vertical grid file
        ocn_vgrid.write(
            inputdir / "ocnice" / f"ocean_vgrid_{ocn_grid.name}_{session_id}.nc"
        )

        # CICE grid file (if needed)
        if "CICE" in self.compset:
            ocn_topo.write_cice_grid(
                inputdir / "ocnice" / f"cice_grid_{ocn_grid.name}_{session_id}.nc"
            )

        # SCRIP grid file (needed for runoff remapping)
        ocn_topo.write_scrip_grid(
            inputdir / "ocnice" / f"scrip_{ocn_grid.name}_{session_id}.nc"
        )

        # ESMF mesh file:
        ocn_topo.write_esmf_mesh(
            inputdir / "ocnice" / f"ESMF_mesh_{ocn_grid.name}_{session_id}.nc"
        )

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

        cc = CaseCreator(self.cime, allow_xml_override=self.override)

        try:
            cc.create_case(do_exec=True)
        except Exception as e:
            print(f"{ERROR}{str(e)}{RESET}")
            cc.revert_launch(do_exec=True)

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
    ):
        """Configure the boundary conditions and tides for the MOM6 case."""

        if too_much_data:
            self._large_data_workflow_called = True
        self.ProductFunctionRegistry.load_functions()
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

        # Instantiate the regional_mom6 experiment object
        self.expt = rmom6.experiment(
            date_range=date_range,
            resolution=None,
            number_vertical_layers=None,
            layer_thickness_ratio=None,
            depth=self.ocn_topo.max_depth,
            mom_run_dir=self._cime_case.get_value("RUNDIR"),
            mom_input_dir=self.inputdir / "ocnice",
            hgrid_type="from_file",
            hgrid_path=self.inputdir
            / "ocnice"
            / f"ocean_hgrid_{self.ocn_grid.name}_{session_id}.nc",
            vgrid_type="from_file",
            vgrid_path=self.inputdir
            / "ocnice"
            / f"ocean_vgrid_{self.ocn_grid.name}_{session_id}.nc",
            minimum_depth=self.ocn_topo.min_depth,
            tidal_constituents=self.tidal_constituents,
            expt_name=self.caseroot.name,
            boundaries=self.boundaries,
        )

        # Create the forcing directory
        if self.override is True:
            forcing_dir_path = self.inputdir / self.forcing_product_name
            if forcing_dir_path.exists():
                shutil.rmtree(forcing_dir_path)
        forcing_dir_path.mkdir(exist_ok=False)
        if not self._large_data_workflow_called:
            boundary_info = dv.get_rectangular_segment_info(self.ocn_grid)
            for key in boundary_info.keys():
                if key in self.boundaries:
                    self.ProductFunctionRegistry.functions[product_name][function_name](
                        date_range,
                        boundary_info[key]["lat_min"],
                        boundary_info[key]["lat_max"],
                        boundary_info[key]["lon_min"],
                        boundary_info[key]["lon_max"],
                        forcing_dir_path,
                        key + "_unprocessed.nc",
                    )
                elif key == "ic":
                    self.ProductFunctionRegistry.functions[product_name][function_name](
                        [date_range[0], date_range[0]],
                        boundary_info[key]["lat_min"],
                        boundary_info[key]["lat_max"],
                        boundary_info[key]["lon_min"],
                        boundary_info[key]["lon_max"],
                        forcing_dir_path,
                        key + "_unprocessed.nc",
                    )
        else:
            # Setup folder path
            large_data_workflow_path = (
                self.inputdir / self.forcing_product_name / "large_data_workflow"
            )

            # Copy large data workflow folder there
            shutil.copytree(
                Path(__file__).parent / "data_access" / "large_data_workflow",
                large_data_workflow_path,
            )

            # Set Vars
            date_format = "%Y%m%d"
            session_id = cvars["MB_ATTEMPT_ID"].value
            hgrid_path = str(
                self.inputdir
                / "ocnice"
                / f"ocean_hgrid_{self.ocn_grid.name}_{session_id}.nc"
            )

            # Write Config File

            # Read in template
            with open(large_data_workflow_path / "config.json", "r") as f:
                config = json.load(f)
            config["paths"]["hgrid_path"] = hgrid_path
            config["paths"]["raw_dataset_path"] = str(
                large_data_workflow_path / "raw_data"
            )
            config["paths"]["regridded_dataset_path"] = str(
                large_data_workflow_path / "regridded_data"
            )
            config["paths"]["merged_dataset_path"] = str(
                self.inputdir
            )
            config["dates"]["start"] = self.expt.date_range[0].strftime(date_format)
            config["dates"]["end"] = self.expt.date_range[1].strftime(date_format)
            config["dates"]["format"] = date_format
            config["forcing"]["product_name"] = self.forcing_product_name
            config["forcing"]["function_name"] = function_name
            config["forcing"]["varnames"] = (
                self.ProductFunctionRegistry.forcing_varnames_config[
                    self.forcing_product_name.upper()
                ]
            )
            config["boundary_number_conversion"] = {
                item: idx + 1 for idx, item in enumerate(self.boundaries)
            }
            config["params"]["step"] = 5

            # Write out
            with open(large_data_workflow_path / "config.json", "w") as f:
                json.dump(config, f, indent=4)
        self._configure_forcings_called = True

    def process_forcings(
        self,
        process_initial_condition=True,
        process_tides=True,
        process_velocity_tracers=True,
    ):
        """Process the boundary conditions and tides for the MOM6 case."""

        if not self._configure_forcings_called:
            raise RuntimeError(
                "configure_forcings() must be called before process_forcings()."
            )

        if self._large_data_workflow_called and process_velocity_tracers:
            process_velocity_tracers = False
            print(
                f"Large data workflow was called, so boundary conditions will not be processed."
            )
            large_data_workflow_path = (
                self.inputdir / self.forcing_product_name / "large_data_workflow"
            )
            print(
                f"Please make sure to execute large_data_workflow as described in {large_data_workflow_path}"
            )
        forcing_path = self.inputdir / self.forcing_product_name
        forcing_path = self.inputdir / self.forcing_product_name

        # check all the boundary files are present:
        if (
            process_initial_condition
            and not (forcing_path / "ic_unprocessed.nc").exists()
        ):
            raise FileNotFoundError(
                f"Initial condition file ic_unprocessed.nc not found in {forcing_path}. "
                f"Initial condition file ic_unprocessed.nc not found in {forcing_path}. "
                "Please make sure to execute get_glorys_data.sh script as described in "
                "the message printed by configure_forcings()."
            )

        for boundary in self.boundaries:
            if (
                process_velocity_tracers
                and not (forcing_path / f"{boundary}_unprocessed.nc").exists()
            ):
                raise FileNotFoundError(
                    f"Boundary file {boundary}_unprocessed.nc not found in {forcing_path}. "
                    "Please make sure to execute get_glorys_data.sh script as described in "
                    "the message printed by configure_forcings()."
                )

        # Define a mapping from the GLORYS variables and dimensions to the MOM6 ones
        ocean_varnames = self.ProductFunctionRegistry.forcing_varnames_config[
            self.forcing_product_name.upper()
        ]

        # Set up the initial condition
        if process_initial_condition:
            self.expt.setup_initial_condition(
                self.inputdir
                / self.forcing_product_name
                / "ic_unprocessed.nc",  # directory where the unprocessed initial condition is stored, as defined earlier
                ocean_varnames,
                arakawa_grid="A",
            )

        # Set up the four boundary conditions. Remember that in the glorys_path, we have four boundary files names north_unprocessed.nc etc.
        if process_velocity_tracers:
            self.expt.setup_ocean_state_boundaries(
                self.inputdir / self.forcing_product_name,
                ocean_varnames,
                arakawa_grid="A",
            )

        # Process the tides
        if process_tides and self.tidal_constituents:

            # Process the tides
            self.expt.setup_boundary_tides(
                tpxo_elevation_filepath=self.tpxo_elevation_filepath,
                tpxo_velocity_filepath=self.tpxo_velocity_filepath,
                tidal_constituents=self.tidal_constituents,
            )

        # regional_mom6 places OBC files under inputdir/forcing. Move them to inputdir:
        if (forcing_dir := self.inputdir / "ocnice" / "forcing").exists():
            for file in forcing_dir.iterdir():
                shutil.move(file, self.inputdir / "ocnice")
            forcing_dir.rmdir()

        # Apply forcing-related namelist and xml changes
        self._update_forcing_variables()

    @property
    def name(self) -> str:
        return self.caseroot.name

    @property
    def date_range(self) -> list[datetime]:
        # check if self.expt is defined
        if not hasattr(self, "expt"):
            raise AttributeError(
                "date_range is not available until configure_forcings() is called."
            )
        return self.expt.date_range

    def _initialize_visualCaseGen(self):

        ConfigVar.reboot()
        Stage.reboot()
        initialize_configvars(self.cime)
        initialize_widgets(self.cime)
        initialize_stages(self.cime)
        set_options(self.cime)
        csp.initialize(cvars, get_relational_constraints(cvars), Stage.first())

    def _assign_configvar_values(self, inittime, datm_mode, machine, project):

        assert Stage.active().title == "1. Component Set"
        cvars["COMPSET_MODE"].value = "Custom"
        # cvars["COMPSET_LNAME"].value = self.compset

        assert Stage.active().title == "Time Period"
        cvars["INITTIME"].value = inittime

        assert Stage.active().title == "Components"
        cvars["COMP_ATM"].value = "datm"
        cvars["COMP_LND"].value = "slnd"
        cvars["COMP_ICE"].value = "sice"
        cvars["COMP_OCN"].value = "mom"
        cvars["COMP_ROF"].value = "srof"
        cvars["COMP_GLC"].value = "sglc"
        cvars["COMP_WAV"].value = "swav"

        # Set model physics:
        assert Stage.active().title == "Component Options"
        cvars["COMP_ATM_OPTION"].value = datm_mode
        cvars["COMP_OCN_OPTION"].value = (
            "(none)"  # todo: in the future, we'll support MARBL too.
        )

        # Grid
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

        xmlchange("RUN_STARTDATE", str(self.date_range[0])[:10])
        xmlchange("MOM6_MEMORY_MODE", "dynamic_symmetric")

        print(f"Case is ready to be built: {self.caseroot}")
