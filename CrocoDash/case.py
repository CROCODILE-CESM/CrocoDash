from pathlib import Path
import sys
import uuid
import shutil
from datetime import datetime
from functools import cached_property
import math
import pandas as pd
import regional_mom6 as rmom6
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.forcing.base import (
    CONFIG_FILENAME,
    CONFIG_META_KEYS,
    ForcingConfigRegistry,
    WorkflowContext,
    read_config,
    write_config,
    xmlchange,
)
from CrocoDash.forcing.utils import read_min_depth
from CrocoDash.raw_data_access.registry import ProductRegistry
from CrocoDash.raw_data_access.base import ForcingProduct
from ProConPy.config_var import ConfigVar, cvars
from ProConPy.stage import Stage
from ProConPy.dev_utils import ConstraintViolation
from visualCaseGen.initialize import initialize as initialize_visualCaseGen
from visualCaseGen.custom_widget_types.case_creator import CaseCreator
from visualCaseGen.custom_widget_types.case_tools import append_user_nl
from CrocoDash.forcing import cice, user_nl_blocks
from CrocoDash.forcing.mom6 import (
    DEFAULT_BOUNDARIES,
    DEFAULT_FUNCTION_NAME,
    DEFAULT_PRODUCT_NAME,
)
from CrocoDash.forcing.driver import run_workflow

from CrocoDash import case_state
from CrocoDash.logging import quiet_visualcasegen_info

quiet_visualcasegen_info()


def _remove_previous(path):
    """Delete a directory left by an earlier case of the same name (override=True)."""
    if path.exists():
        print(f"Removing previous case files: {path}")
        shutil.rmtree(path)


def _remove_failed_attempt(paths, preexisting):
    """Delete the dirs a failed Case() created, so that retrying it is not
    refused with "already exists". One that was already there before the
    attempt (the build/run dir, with override=False) is not ours to delete.
    """
    for path in paths:
        if path not in preexisting and path.exists():
            print(f"Removing files from the failed attempt: {path}")
            shutil.rmtree(path, ignore_errors=True)


# Seconds in each NCPL_BASE_PERIOD; year/decade assume a NO_LEAP calendar.
_NCPL_BASE_SECONDS = {
    "hour": 3600,
    "day": 86400,
    "year": 365 * 86400,
    "decade": 3650 * 86400,
}


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
            self._configure_case(
                atm_grid_name,
                rof_grid_name,
                ntasks_ocn_specified=ntasks_ocn is not None,
            )
        except Exception as e:
            raise RuntimeError(f"Case configuration failed: {e}") from e

        # Read now: visualCaseGen's state belongs to the case created last.
        self.session_id = cvars["MB_ATTEMPT_ID"].value
        self.grid_name = ocn_grid.name

        case_dirs = [
            self.inputdir,
            self.caseroot,
            Path(self.cime.cime_output_root) / self.caseroot.name,
        ]
        if override:
            for path in case_dirs:
                _remove_previous(path)
        preexisting = {path for path in case_dirs if path.exists()}
        try:
            # Before creating the case, we need to create the grid input files (except for mapping files,
            # which will be created later in process_forcings if needed).
            self._create_grid_input_files()

            # Having set the configuration variables and created the grid input files, we can now create the case instance.
            self._create_newcase()
            self.is_non_local = self.cc._is_non_local()

            # After creating the case, instantiate the CIME case object for later use.
            self._cime_case = self.cime.get_case(
                self.caseroot, non_local=self.is_non_local
            )

            # Need the case: they read <COMP>_NCPL and write user_nl_<comp>.
            if self.ww3_in_compset:
                self._set_ww3_timesteps()
            if self.cice_in_compset:
                self._set_cice_ndtd()

            self._apply_final_xmlchanges(ntasks_ocn, job_queue, job_wallclock_time)

            self._write_state()
            # Read the case back as from_caseroot() does, so that a created
            # case and a read-back one can't drift apart.
            self._bind(self.caseroot, is_non_local=self.is_non_local)
        except BaseException:
            _remove_failed_attempt(case_dirs, preexisting)
            raise

        required_specs = [
            spec
            for spec in ForcingConfigRegistry.param_specs(self.compset_lname)
            if spec.required
        ]
        if required_specs:
            print("configure_forcings() needs these arguments for this compset:")
            for spec in required_specs:
                print(f"  - {spec.name} ({spec.configurator}): {spec.comment}")

    @classmethod
    def from_caseroot(cls, caseroot, *, cesmroot=None):
        """Read back a case CrocoDash created, from its caseroot alone.

        Runs no create_newcase, case.setup or visualCaseGen: everything comes
        from the case's _crocodash_state.json and, once its forcings are
        configured, its config.json. The grids and the CIME case are loaded on
        first use. A case read back can configure and process its forcings:
        ``case.configure_forcings(**case.forcing_args(changes))``.

        Parameters
        ----------
        caseroot : str | Path
            The caseroot of a case created by this version of CrocoDash. A case
            created by an older version is refused and has to be recreated.
        cesmroot : str | Path, optional
            The CESM tree to use instead of the one the case was created with,
            e.g. because that one moved. It isn't saved.
        """
        case = cls.__new__(cls)
        case._bind(caseroot, cesmroot=cesmroot)
        return case

    def _bind(self, caseroot, cesmroot=None, is_non_local=True):
        """Set what configuring, processing and the properties need from the
        state file.

        __init__ ends here too, so a created case and one read back with
        from_caseroot() can't drift apart. is_non_local is whether CIME's
        tools run with --non-local: a case read back may be on another machine
        than its own, so it is True unless the case was just created here.
        """
        state = case_state.read(caseroot)
        self.caseroot = Path(caseroot)
        self.inputdir = Path(state["inputdir"])
        self.cesmroot = Path(cesmroot or state["cesmroot"])
        self.compset_lname = state["compset_lname"]
        self.machine = state["machine"]
        self.project = state["project"]
        self.ninst = state["ninst"]
        self.atm_grid_name = state["atm_grid_name"]
        self.rof_grid_name = state["rof_grid_name"]
        self.session_id = state["session_id"]
        self.grid_name = state["grid_name"]
        self.supergrid_path = state["supergrid_path"]
        self.topo_path = state["topo_path"]
        self.vgrid_path = state["vgrid_path"]
        self.esmf_mesh_path = state["esmf_mesh_path"]
        self.is_non_local = is_non_local
        # override=True applies to creating the case only; nothing is deleted
        # after that.
        self.override = False
        self.extract_forcings_path = self.inputdir / "extract_forcings"
        self._configure_forcings_called = (
            self.extract_forcings_path / CONFIG_FILENAME
        ).exists()
        # configure_forcings() sets it from its product_name.
        self.forcing_product = None

    # __init__ sets ocn_grid, ocn_topo, ocn_vgrid and _cime_case, which then
    # shadow these; a case read back loads each from its files when first used.

    @cached_property
    def ocn_grid(self):
        return Grid.from_supergrid(self.supergrid_path, name=self.grid_name)

    @cached_property
    def ocn_topo(self):
        return Topo.from_topo_file(
            self.ocn_grid,
            self.topo_path,
            min_depth=read_min_depth(self.topo_path),
            git=False,
        )

    @cached_property
    def ocn_vgrid(self):
        return VGrid.from_file(str(self.vgrid_path))

    @cached_property
    def _cime_case(self):
        """The case's read-only CIME case, opened with this case's cesmroot."""
        cimeroot = (self.cesmroot / "cime").as_posix()
        if cimeroot not in sys.path:
            sys.path.append(cimeroot)
        from CIME.case.case import Case as CIMECase

        return CIMECase(self.caseroot.as_posix(), read_only=True, non_local=True)

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
            raise ValueError(
                f"Given caseroot {caseroot} already exists! "
                "To overwrite it, use override=True."
            )
        if Path(inputdir).exists() and not override:
            raise ValueError(
                f"Given inputdir {inputdir} already exists! "
                "To overwrite it, use override=True."
            )
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
            raise ValueError(
                f"ocn_grid name '{ocn_grid.name}' is already registered in CESM's grid config. "
                "This happens when a previous case with this grid was deleted without using override=True. "
                "To recreate the case, use override=True."
            )
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

        inputdir.mkdir(parents=True, exist_ok=False)

        ocn_dir = inputdir / "ocn"
        ocn_dir.mkdir()

        # suffix for the MOM6 grid files
        suffix = f"{ocn_grid.name}_{self.session_id}"

        # MOM6 supergrid file
        self.supergrid_path = str(ocn_dir / f"ocean_hgrid_{suffix}.nc")
        ocn_grid.write_supergrid(self.supergrid_path)

        # MOM6 topography file
        self.topo_path = str(ocn_dir / f"ocean_topog_{suffix}.nc")
        ocn_topo.write_topo(self.topo_path)

        # MOM6 vertical grid file
        self.vgrid_path = str(ocn_dir / f"ocean_vgrid_{suffix}.nc")
        ocn_vgrid.write(self.vgrid_path)

        # SCRIP grid file (needed for runoff remapping)
        ocn_topo.write_scrip_grid(ocn_dir / f"scrip_{suffix}.nc")

        # ESMF mesh file:
        self.esmf_mesh_path = str(ocn_dir / f"ESMF_mesh_{suffix}.nc")
        ocn_topo.write_esmf_mesh(self.esmf_mesh_path)

        # CICE grid file (if needed)
        if self.cice_in_compset:
            ice_dir = inputdir / "ice"
            ice_dir.mkdir(exist_ok=True)
            self.ocn_topo.write_cice_grid(ice_dir / f"cice_grid_{suffix}.nc")

        # WW3 grid file (if needed)
        if self.ww3_in_compset:
            wav_dir = inputdir / "wav"
            wav_dir.mkdir(exist_ok=True)
            self.ocn_topo.write_ww3_input(wav_dir, grid_alias=ocn_grid.name)

    def _coupling_interval(self, comp):
        """Coupling interval of a component in seconds, from <COMP>_NCPL."""
        base_period = self._cime_case.get_value("NCPL_BASE_PERIOD")
        if base_period not in _NCPL_BASE_SECONDS:
            raise ValueError(f"Invalid NCPL_BASE_PERIOD {base_period}")
        calendar = self._cime_case.get_value("CALENDAR")
        if base_period in ("year", "decade") and calendar != "NO_LEAP":
            raise ValueError(
                f"Invalid CALENDAR {calendar} for NCPL_BASE_PERIOD {base_period}"
            )

        basedt = _NCPL_BASE_SECONDS[base_period]
        ncpl = int(self._cime_case.get_value(f"{comp}_NCPL"))
        cpl_dt, remainder = divmod(basedt, ncpl)
        if remainder:
            raise ValueError(f"{comp}_NCPL doesn't divide the base dt evenly")
        return cpl_dt

    def _set_ww3_timesteps(self):
        """Scale the WW3 time steps to the grid via user_nl_ww3."""

        cpl_dt = self._coupling_interval("WAV")
        dt = self.ocn_topo.ww3_timesteps(float(cpl_dt))
        append_user_nl(
            "ww3",
            [(k, f"{dt[k]:.1f}") for k in ("dtmax", "dtcfl", "dtcfli", "dtmin")],
            do_exec=True,
            comment=(
                f"WW3 time steps from the grid's smallest cell and the {cpl_dt} s "
                "coupling interval (CESM defaults are per wav_grid alias, not "
                "per resolution)"
            ),
        )

    def _set_cice_ndtd(self):
        """Scale CICE's dynamics substeps (ndtd) to the grid via user_nl_cice."""

        ice_dt = self._coupling_interval("ICE")
        min_dx = min(float(self.ocn_grid.dxt.min()), float(self.ocn_grid.dyt.min()))
        ndtd = cice.dynamics_substeps(ice_dt, min_dx)
        append_user_nl(
            "cice",
            [("ndtd", str(ndtd))],
            do_exec=True,
            comment=(
                f"CICE dynamics substeps: ice at {cice.MAX_ICE_SPEED} m/s crosses at "
                f"most {cice.MAX_CELL_FRACTION} of the smallest cell ({min_dx:.0f} m) "
                f"per substep of the {ice_dt} s ice time step"
            ),
        )

    def _create_newcase(self):
        """Create the case instance."""
        if not self.caseroot.parent.exists():
            self.caseroot.parent.mkdir(parents=True, exist_ok=False)

        self.cc = CaseCreator(
            self.cime, allow_xml_override=self.override, add_grids_to_ccs_config=False
        )

        try:
            self.cc.create_case(do_exec=True)
        except Exception:
            self.cc.revert_launch(do_exec=True)
            raise

    def configure_forcings(
        self,
        date_range: list[str],
        boundaries: list[str] = DEFAULT_BOUNDARIES,
        product_name: str = DEFAULT_PRODUCT_NAME,
        function_name: str = DEFAULT_FUNCTION_NAME,
        function_overrides: dict = None,
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
        function_overrides : dict, optional
            Overrides for `function_name`'s non-required arguments (e.g. `{"member": 3}`
            to select a specific ensemble member for a CESM2-LENS2-style product). Keys
            must match one of the function's non-required, defaulted parameters; any other
            key raises a ValueError. Without this, the function's own defaults are used,
            which previously could only be changed by hand-editing `config.json` between
            `configure_forcings()` and `process_forcings()`.
        kwargs :
            These are the configuration options (please see accepted arguments in the configuration classes)
        Raises
        ------
        TypeError
            If inputs such as `date_range`, `boundaries`, or `tidal_constituents` are not lists of strings.
        ValueError
            If `date_range` does not have exactly two elements, or if tidal arguments are inconsistently specified.
            Also raised if an invalid product or function is provided, or if `function_overrides`
            contains a key that is not a valid overridable argument of `function_name`.
        AssertionError
            If the selected data product is not categorized as a forcing product.

        Notes
        -----
        - Downloads forcing data (or creates a script) for each boundary and the initial condition unless the large data workflow is used.
        - In large data workflow mode, creates a folder structure and `config.json` file for later manual processing.
        - This method must be called before `process_forcings()`.
        - Calling it again replaces the previous forcing configuration. Its user_nl
          entries sit in `! >>> CrocoDash configure_forcings` blocks, which every call
          rewrites; values set outside those blocks are kept and take precedence.
          Files `process_forcings()` made for a different configuration are removed,
          so that it regenerates them.

        See Also
        --------
        process_forcings : Executes the actual boundary, initial condition, and tide setup based on the configuration.
        """

        # Set up Forcings Folder
        self.extract_forcings_path = self.inputdir / "extract_forcings"
        config_path = self.extract_forcings_path / CONFIG_FILENAME
        # What an earlier call configured, to tell which of the files its
        # process_forcings() made still match. A config.json from an
        # incompatible CrocoDash counts as no record, so those files go.
        try:
            previous_config = read_config(config_path)
        except (OSError, ValueError):
            previous_config = {}

        # Validate date_range's raw shape and set case-level state. Everything else
        # (boundaries/product_name validity, IC/OBC user_nl params, config.json
        # "conditions" entry) is handled by ConditionsConfigurator's validate_args()/
        # configure() (see forcing/mom6.py).
        if not (
            isinstance(date_range, list)
            and all(isinstance(date, str) for date in date_range)
        ):
            raise TypeError("date_range must be a list of strings.")
        if len(date_range) != 2:
            raise ValueError("date_range must have exactly two elements.")
        if function_overrides is not None and not isinstance(function_overrides, dict):
            raise TypeError("function_overrides must be a dict.")

        self.forcing_product_name = product_name.lower()
        self.boundaries = boundaries
        self.date_range = pd.to_datetime(date_range)

        ProductRegistry.load()
        if not (
            ProductRegistry.product_exists(product_name)
            and ProductRegistry.product_is_of_type(product_name, ForcingProduct)
        ):
            raise ValueError("Product / Data Path is not supported quite yet")
        self.forcing_product = ProductRegistry.get_product(self.forcing_product_name)

        function_args = ProductRegistry.get_function_default_args(
            self.forcing_product_name, function_name
        )
        if function_overrides:
            invalid = set(function_overrides) - set(function_args)
            if invalid:
                raise ValueError(
                    f"Invalid function_overrides key(s) {sorted(invalid)}; "
                    f"valid overridable args are {sorted(function_args)}"
                )
            function_args.update(function_overrides)

        # function_args is written straight to config.json (via ConditionsConfigurator's
        # "function_args" ConfigOutputParam); coerce Path values (e.g. a dataset_path
        # override) to strings so they're JSON-serializable.
        function_args = {
            k: (v.as_posix() if isinstance(v, Path) else v)
            for k, v in function_args.items()
        }

        inputs = kwargs | {
            "date_range": pd.to_datetime(date_range),
            "boundaries": boundaries,
            "product_name": product_name,
            "function_name": function_name,
            "function_args": function_args,
        }

        self.fcr = ForcingConfigRegistry(self.compset_lname, inputs, self)
        # Every input is validated by now, so replace the previous call's
        # user_nl entries. If anything from here on fails, the user_nl files
        # are put back, and config.json -- the record stale_outputs() compares
        # against -- is left as it was.
        user_nl_before = user_nl_blocks.snapshot(self.caseroot)
        try:
            edited = user_nl_blocks.strip(self.caseroot)
            config = {"caseroot": str(self.caseroot)}
            config |= self.fcr.run_configurators()
            user_nl_blocks.report_edits(self.caseroot, edited)

            stale = self.fcr.stale_outputs(previous_config, config, self.inputdir)
            for path in stale:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            # Last, so that it never describes files that are still to be removed.
            self.extract_forcings_path.mkdir(parents=True, exist_ok=True)
            write_config(config_path, config)
        except BaseException:
            user_nl_blocks.restore(self.caseroot, user_nl_before)
            raise
        if stale:
            print(
                "Removed forcing files made for another configuration "
                "(process_forcings() regenerates them): "
                + ", ".join(str(path.relative_to(self.inputdir)) for path in stale)
            )

        xmlchange(
            "CALENDAR",
            self.forcing_product.calendar.cesm,
            caseroot=self.caseroot,
            is_non_local=self.is_non_local,
        )
        xmlchange(
            "RUN_STARTDATE",
            str(self.date_range[0])[:10],
            caseroot=self.caseroot,
            is_non_local=self.is_non_local,
        )
        xmlchange(
            "STOP_OPTION",
            "ndays",
            caseroot=self.caseroot,
            is_non_local=self.is_non_local,
        )
        xmlchange(
            "STOP_N",
            (self.date_range[1] - self.date_range[0]).days,
            caseroot=self.caseroot,
            is_non_local=self.is_non_local,
        )
        if self._configure_forcings_called:
            print(
                "configure_forcings() replaced this case's previous forcing configuration."
            )
        self._configure_forcings_called = True

    def process_forcings(self, **kwargs):
        """
        Process boundary conditions, initial conditions, and other forcings for a MOM6 case. It's a wrapper around forcing/driver.py

        This method configures a regional MOM6 case's ocean state boundaries and initial conditions
        using previously downloaded data setup in configure_forcings. The method expects `configure_forcings()` to be
        called beforehand.

        Parameters
        ----------
        kwargs : bool, optional
            Whether to run each process component, of the form
            `process_{flag_name}=False` (e.g. `process_ic=False`,
            `process_bgcic=False`). Defaults to True for every component
            that's actually active for this case's compset -- components
            that aren't active are silently skipped regardless. Valid
            `{flag_name}`s come from every active configurator's
            `process_components` (see `CrocoDash.forcing.base`).

        Raises
        ------
        RuntimeError
            If `configure_forcings()` was not called before this method.
        TypeError
            If a `process_*` kwarg is passed that doesn't match any active
            configurator's `process_components` flag name.
        FileNotFoundError
            If required unprocessed files are missing in the expected directories.

        Notes
        -----
        - This method uses variable name mappings specified in the forcing product configuration.
        - Applies forcing-related namelist and XML updates at the end of the method.

        See Also
        --------
        configure_forcings : Must be called before this method to set up the environment.
        """
        if not self._configure_forcings_called:
            raise RuntimeError(
                "configure_forcings() must be called before process_forcings()."
            )

        flag_names = ForcingConfigRegistry.resolve_process_targets(
            self.forcing_config
        ).keys()
        valid_kwargs = {f"process_{name}" for name in flag_names}
        unrecognized = sorted(set(kwargs) - valid_kwargs)
        if unrecognized:
            raise TypeError(
                f"process_forcings() got unrecognized keyword argument(s): {unrecognized}. "
                f"Valid arguments are: {sorted(valid_kwargs)}."
            )
        flags = {name: kwargs.get(f"process_{name}", True) for name in flag_names}

        run_workflow(self, **flags)

        print(f"Case is ready to be built: {self.caseroot}")

    @property
    def forcing_config(self):
        """The config.json configure_forcings() wrote, read afresh on every
        access so that it never goes stale."""
        return read_config(self.extract_forcings_path / CONFIG_FILENAME)

    def configurators(self):
        """The configured forcings, rebuilt from config.json:
        {config.json entry: configurator}."""
        return {
            key: ForcingConfigRegistry.get_configurator(entry, self.caseroot)
            for key, entry in self.forcing_config.items()
            if key not in CONFIG_META_KEYS
        }

    def forcing_inputs(self):
        """This case's values that configurators take as case_* inputs.

        ForcingConfigRegistry adds them to the configure_forcings() arguments,
        so a case_* input a configurator declares must be provided here.
        """
        return {
            "case_cesmroot": self.cesmroot,
            "case_inputdir": self.inputdir,
            "case_compset_lname": self.compset_lname,
            "case_session_id": self.session_id,
            "case_grid_name": self.grid_name,
            "case_esmf_mesh_path": self.esmf_mesh_path,
            "case_forcing_product": self.forcing_product,
        }

    def forcing_args(self, changes=None):
        """The configure_forcings() arguments this case's forcings were
        configured with, read back from config.json (none if they never were),
        with ``changes`` applied.

        Pass them back to reconfigure the case:
        ``case.configure_forcings(**case.forcing_args({"boundaries": ["north"]}))``.
        A required argument config.json lacks (one a newer CrocoDash added)
        has to be given in ``changes``.
        """
        changes = changes or {}
        if not self._configure_forcings_called:
            return dict(changes)
        forcing_config = self.forcing_config
        conditions = forcing_config["conditions"]
        date_format = conditions["outputs"]["date_format"]
        product_name = conditions["inputs"]["product_name"]
        function_name = conditions["inputs"]["function_name"]
        args = {
            "date_range": [
                datetime.strptime(conditions["inputs"][key], date_format).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                for key in ("start_date", "end_date")
            ],
            "boundaries": list(conditions["outputs"]["boundary_number_conversion"]),
            "product_name": product_name.upper(),
            "function_name": function_name,
        }
        # config.json keeps the access method's merged arguments; hand back only
        # the ones that differ from its defaults, as configure_forcings takes them.
        function_args = conditions["inputs"].get("function_args") or {}
        if function_args:
            ProductRegistry.load()
            defaults = {
                name: value.as_posix() if isinstance(value, Path) else value
                for name, value in ProductRegistry.get_function_default_args(
                    product_name.lower(), function_name
                ).items()
            }
            overrides = {
                name: value
                for name, value in function_args.items()
                if name in defaults and value != defaults[name]
            }
            if overrides:
                args["function_overrides"] = overrides
        for key, entry in forcing_config.items():
            if key == "conditions" or key in CONFIG_META_KEYS:
                continue
            configurator_cls = ForcingConfigRegistry.get_configurator_from_name(key)
            # Round-trip every ctor arg, not just required ones -- an all-optional
            # configurator (e.g. CICE) would otherwise silently fall back to
            # defaults instead of reproducing the original case.
            all_args, required_args = ForcingConfigRegistry.get_ctor_signature(
                configurator_cls
            )
            stored_inputs = entry.get("inputs", {})
            derived = {p.name for p in configurator_cls.input_params if p.derived}
            for arg in all_args:
                # case_* args come from forcing_inputs(), and derived ones
                # (dates, calendar) from the other args, not from config.json.
                if (
                    arg.startswith("case_")
                    or arg in derived
                    or arg in args
                    or arg in changes
                ):
                    continue
                if arg in stored_inputs:
                    args[arg] = stored_inputs[arg]
                elif arg in required_args:
                    raise ValueError(
                        f"config.json's '{key}' block is missing required argument "
                        f"'{arg}' for configurator {configurator_cls.name}; give it "
                        f"in changes (crocodash configure: --set {arg}=...)."
                    )
        return args | changes

    def workflow_context(self, preview=False):
        """The WorkflowContext every process step gets: config.json and the
        case's paths that no single configurator owns."""
        return WorkflowContext(
            inputdir=self.inputdir,
            supergrid_path=self.supergrid_path,
            vgrid_path=self.vgrid_path,
            topo_path=self.topo_path,
            raw_data_dir=self.extract_forcings_path / "raw_data",
            regridded_data_dir=self.extract_forcings_path / "regridded_data",
            output_path=self.inputdir / "ocn",
            config=self.forcing_config,
            preview=preview,
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
            date_range = tuple(
                ts.strftime("%Y-%m-%d %H:%M:%S") for ts in self.date_range
            )
        if not hasattr(self, "boundaries"):
            print("Boundaries not found so using default")
            self.boundaries = ["north", "south", "east", "west"]
        if not hasattr(self, "tidal_constituents"):
            print("tidal_constituents not found so using only M2")
            self.tidal_constituents = ["M2"]

        # hgrid_type/vgrid_type take mom6_forge Grid/VGrid objects directly
        # now -- "from_file" + a separate hgrid_path/vgrid_path kwarg no
        # longer exists, and hgrid/vgrid are read-only properties derived
        # from them (no more assigning after construction).
        expt = rmom6.experiment(
            date_range=date_range,
            resolution=None,
            number_vertical_layers=None,
            layer_thickness_ratio=None,
            depth=self.ocn_topo.max_depth,
            mom_run_dir=self._cime_case.get_value("RUNDIR"),
            mom_input_dir=self.inputdir / "ocn",
            hgrid_type=self.ocn_grid,
            vgrid_type=self.ocn_vgrid,
            minimum_depth=self.ocn_topo.min_depth,
            tidal_constituents=self.tidal_constituents,
            expt_name=self.caseroot.name,
            boundaries=self.boundaries,
        )
        return expt

    def _configure_case(self, atm_grid_name, rof_grid_name, ntasks_ocn_specified=False):
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
        self._configure_launch(ntasks_ocn_specified=ntasks_ocn_specified)

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
                opt = "%".join(phys.split("%")[1:]) if "%" in phys else None
                if opt is not None:
                    cvars[f"COMP_{comp_class}_OPTION"].value = opt
                else:
                    cvars[f"COMP_{comp_class}_OPTION"].value = "(none)"

        # Confirm successful configuration of custom component set
        assert Stage.active().title == "2. Grid"

        # VCG's Z3 solver cannot handle multi-select option values (e.g., "REGIONAL%MARBL-BIO")
        # as assignment assertions, so only the first modifier was set above. Directly assign
        # the full correct COMPSET_LNAME now that the options stage is complete and its
        # options assertions have been cleared.
        cvars["COMPSET_LNAME"].value = compset_lname

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

    def _max_tasks_per_node(self):
        """Return MAX_TASKS_PER_NODE for the target machine, or None if unavailable.

        Read from the machine XML config rather than from a CIME case object, because
        PECOUNT must be set before create_newcase runs, i.e. before self._cime_case
        exists.
        """
        from CIME.XML.machines import Machines
        from CIME.utils import CIMEError

        machs_file = self.cime._files.get_value("MACHINES_SPEC_FILE")
        try:
            machines_obj = Machines(machs_file, machine=self.machine)
        except CIMEError:
            print(
                f"WARNING: machine {self.machine} not found in the CESM machines XML "
                "file, so MAX_TASKS_PER_NODE could not be determined."
            )
            return None

        max_tasks_per_node = machines_obj.get_value("MAX_TASKS_PER_NODE")
        if max_tasks_per_node is None:
            print(f"WARNING: MAX_TASKS_PER_NODE is not set for machine {self.machine}.")
            return None
        return int(max_tasks_per_node)

    def _compute_pecount(self):
        """Compute the CIME pecount tier based on active ocean points and compset.

        Uses target pts/core ratios derived from tx2_3v3 benchmarks:
          - without MARBL: ~170 pts/core
          - with MARBL:    ~60  pts/core

        MOM6 is allocated whole nodes, so the active point count is converted to a
        node count using the machine's MAX_TASKS_PER_NODE, and that node count is
        mapped to a CIME --pecount keyword. Returns None when no tier should be
        requested (the domain fits in the default layout, or the node size is
        unknown), in which case CIME's default PE layout is left in place.
        """
        max_tasks_per_node = self._max_tasks_per_node()
        if max_tasks_per_node is None:
            return None
        pts_per_core = 60 if self.bgc_in_compset else 170
        ocean_pts = int(self.ocn_topo.tmask.sum())
        nodes_needed = math.ceil(ocean_pts / (pts_per_core * max_tasks_per_node))
        if nodes_needed < 1:
            return None
        elif nodes_needed == 1:
            return "S"
        elif nodes_needed <= 3:
            return "M"
        else:
            return "L"

    def _configure_launch(self, ntasks_ocn_specified=False):
        """Assign the launch variables for the case."""

        assert Stage.active().title == "3. Launch"
        cvars["CASEROOT"].value = self.caseroot.as_posix()
        cvars["MACHINE"].value = self.machine
        if self.project is not None:
            cvars["PROJECT"].value = self.project

        # Variables that are not included in a stage:
        cvars["NINST"].value = self.ninst
        if not ntasks_ocn_specified:
            pecount = self._compute_pecount()
            if pecount is not None:
                cvars["PECOUNT"].value = pecount

    def _write_state(self):
        """Write case creation parameters to _crocodash_state.json in caseroot.

        Called after the last creation-time xmlchange and user_nl write, so its
        "created" snapshot holds everything creating the case left there.
        """
        case_state.write(
            self.caseroot,
            {
                # Derived / resolved fields that can't come from init args directly
                "inputdir": str(self.inputdir),
                "cesmroot": str(self.cesmroot),
                "supergrid_path": self.supergrid_path,
                "topo_path": self.topo_path,
                "vgrid_path": self.vgrid_path,
                "grid_name": self.grid_name,
                "session_id": self.session_id,
                "compset_lname": self.compset_lname,
                "machine": self.machine,
                "esmf_mesh_path": self.esmf_mesh_path,
                "created": case_state.created_snapshot(self.caseroot),
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
            caseroot=self.caseroot,
            is_non_local=self.is_non_local,
        )

        # xmlchange("ROOTPE_OCN", 128, is_non_local=self.cc._is_non_local()) -> needs to be before the the setup
        if ntasks_ocn is not None:
            xmlchange(
                "NTASKS_OCN",
                ntasks_ocn,
                caseroot=self.caseroot,
                is_non_local=self.is_non_local,
            )
        # This will trigger for both the run and the archiver.
        if job_queue is not None:
            xmlchange(
                "JOB_QUEUE",
                job_queue,
                caseroot=self.caseroot,
                is_non_local=self.is_non_local,
            )
        if job_wallclock_time is not None:
            xmlchange(
                "JOB_WALLCLOCK_TIME",
                job_wallclock_time,
                caseroot=self.caseroot,
                is_non_local=self.is_non_local,
            )

    def validate_case(self):

        # Ensure configurations are done
        for name, configurator in self.fcr.active_configurators.items():
            if not configurator.validate_output_filepaths(self.inputdir / "ocn"):
                print(
                    f"{name} is not valid yet — process this forcing and generate "
                    f"the files using your case's extract_forcings module: "
                    f"{self.inputdir / 'extract_forcings'}"
                )
