from pathlib import Path
import uuid
import shutil
from datetime import datetime
import json
import threading

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
from visualCaseGen.cime_interface import CIME_interface
from visualCaseGen.initialize_configvars import initialize_configvars
from visualCaseGen.initialize_widgets import initialize_widgets
from visualCaseGen.initialize_stages import initialize_stages
from visualCaseGen.specs.options import set_options
from visualCaseGen.specs.relational_constraints import get_relational_constraints
from visualCaseGen.custom_widget_types.case_creator import CaseCreator, ERROR, RESET
from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl, remove_user_nl


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
        message: str = None, 
        object_messages: dict = None, 
        forcing_config: dict = None,
        forcing_scripts: list = None,
        restored_from: int = None,
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
        message : str, optional
        A user-provided message describing this case instantiation. This will be saved in the case history.
        object_messages : dict, optional
            A dictionary of per-object messages, e.g. {'grid': "...", 'vgrid': "...", 'topo': "..."}.
            These messages are saved in the object histories and can be used for provenance or notes about each file.
        """

        # Initialize the CIME interface object
        self.cime = CIME_interface(cesmroot)
        self.cesmroot = cesmroot

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
        self.ocn_vgrid.name = self.ocn_grid.name
        self.project = project
        self.machine = "derecho"
        self.ninst = ninst
        self.override = override
        self.message = message
        self.object_messages = object_messages
        self.ProductFunctionRegistry = dv.ProductFunctionRegistry()
        self.forcing_product_name = None
        self._configure_forcings_called = False
        self._large_data_workflow_called = False

        self._history_dir = self.caseroot.parent 
        self._object_history_path = self._history_dir / "object_histories.json"
        self._history_path = self._history_dir / "case_history.json"

        # Construct the compset long name
        self.compset = f"{inittime}_DATM%{datm_mode}_SLND_SICE_MOM6_SROF_SGLC_SWAV_SESP"
        # Resolution name:
        self.resolution = f"{datm_grid_name}_{ocn_grid.name}"

        self._initialize_visualCaseGen()

        self._assign_configvar_values(inittime, datm_mode, machine, project)

        self._create_grid_input_files()

        self._create_newcase()

        self._cime_case = self.cime.get_case(self.caseroot,non_local = self.cc._is_non_local())

        # --- Per-object history management ---
        if self._object_history_path.exists():
            with open(self._object_history_path, "r") as f:
                self._object_histories = json.load(f)
        else:
            self._object_histories = {
                "grid": {"history": []},
                "vgrid": {"history": []},
                "topo": {"history": []},
            }

        current_files = {
            "grid": Case.get_grid_file(ocn_grid, inputdir=self.inputdir),
            "vgrid": Case.get_vgrid_file(ocn_vgrid, inputdir=self.inputdir),
            "topo": Case.get_topo_file(ocn_topo, inputdir=self.inputdir),
        }

        # Append current files to their respective histories if changed
        for key in ["grid", "vgrid", "topo"]:
            hist = self._object_histories[key]["history"]
            file_path = current_files[key]
            obj_msg = None
            if object_messages and key in object_messages:
                obj_msg = object_messages[key]
            if not obj_msg:
                obj_msg = f"Selected {key} file at {datetime.now().isoformat()}"
            if not hist or hist[-1]["file"] != file_path:
                hist.append({"file": file_path, "message": obj_msg})
        self._save_object_histories()

       # Use user-provided message if available, else default
        current_files = {
            "grid_file": Case.get_grid_file(ocn_grid, inputdir=self.inputdir),
            "vgrid_file": Case.get_vgrid_file(ocn_vgrid, inputdir=self.inputdir),
            "topo_file": Case.get_topo_file(ocn_topo, inputdir=self.inputdir),
        }
        state_msg = message if message else "New instantiation"
        
        self._record_case_state(
            **current_files,
            message=state_msg,
            cesmroot=cesmroot,
            caseroot=caseroot,
            inputdir=inputdir,
            inittime=inittime,
            datm_mode=datm_mode,
            datm_grid_name=datm_grid_name,
            ninst=ninst,
            machine=machine,
            project=project,
            override=override,
            forcing_config=forcing_config,
            restored_from=restored_from,
        )

        # Store on self for summary writing
        self.forcing_config = forcing_config or {}
        self.forcing_scripts = forcing_scripts or []

        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=cesmroot,
            inputdir=inputdir,
            caseroot=caseroot,
        )
    
    # --- CASERECORD MANAGEMENT ---

    # When creating a new record:
    def _record_case_state(self, **kwargs):
        record = self.make_case_record(**kwargs)
        self.save_history(record)
        self.append_history_to_readme()
        return record
    
    @staticmethod
    def make_case_record(**kwargs):
        """
        Create a case record dictionary from keyword arguments.
        Always includes a timestamp and message.
        """
        record = dict(kwargs)
        record.setdefault("date", datetime.now().isoformat())
        record.setdefault("message", "")
        record.setdefault("forcing_config", {})
        return record

    @staticmethod
    def case_record_to_dict(record):
        """
        Convert all Path objects to strings for JSON serialization.
        """
        def stringify(obj):
            from pathlib import Path
            if isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: stringify(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return type(obj)(stringify(v) for v in obj)
            else:
                return obj
        return {k: stringify(v) for k, v in record.items()}

    @staticmethod
    def case_record_from_dict(d):
        """
        Return a case record dictionary from a dict (no hardcoding).
        """
        return dict(d)

    @staticmethod
    def case_record_summary_line(record, idx=None):
        """
        Return a summary line for a case record.
        """
        idx_str = f"{idx}: " if idx is not None else ""
        msg = f" | {record.get('message','')}" if record.get("message") else ""
        restored = f" | restored_from: {record.get('restored_from')}" if record.get("restored_from") is not None else ""
        grid = record.get("grid_file", "unknown")
        vgrid = record.get("vgrid_file", "unknown")
        topo = record.get("topo_file", "unknown")
        date = record.get("date", "")
        return f"{idx_str}Grid: {grid}, VGrid: {vgrid}, Topo: {topo}, Date: {date}{msg}{restored}"
    
    def save_history(self, new_state):
        """Appends a new case record to the global case history."""
        if self._history_path.exists():
            with open(self._history_path, "r") as f:
                existing = json.load(f)
        else:
            existing = []
        new_state_dict = self.case_record_to_dict(new_state)
        # Use JSON string for uniqueness (handles nested dicts/lists)
        key = json.dumps(new_state_dict, sort_keys=True)
        existing_keys = {json.dumps(d, sort_keys=True) for d in existing}
        if key not in existing_keys:
            existing.append(new_state_dict)
        with open(self._history_path, "w") as f:
            json.dump(existing, f, indent=2)

    def load_history(self):
        """Loads the entire global case history."""
        if self._history_path.exists():
            with open(self._history_path, "r") as f:
                return [self.case_record_from_dict(d) for d in json.load(f)]
        return []

    def append_history_to_readme(self):
        """Appends the global case history to the README.case file in the current case directory."""
        readme_path = Path(self.caseroot) / "README.case"
        if readme_path.exists():
            with open(readme_path, "r") as f:
                lines = f.readlines()
        else:
            lines = []
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "CaseRecord History:":
                start = i
                break
        if start is not None:
            lines = lines[:start]
        with open(readme_path, "w") as f:
            f.writelines(lines)
            f.write("\nCaseRecord History:\n")
            if self._history_path.exists():
                with open(self._history_path, "r") as h:
                    global_history = [self.case_record_from_dict(d) for d in json.load(h)]
                for idx, state in enumerate(global_history):
                    f.write(self.case_record_summary_line(state, idx) + "\n")

     # --- Per-object helpers ---

    def _save_object_histories(self):
        """Persists the per-object history (Grid, VGrid, Topo) to object_histories.json."""
        # Always append to the global object_histories.json
        if self._object_history_path.exists():
            with open(self._object_history_path, "r") as f:
                existing = json.load(f)
        else:
            existing = {"grid": {"history": []},
                        "vgrid": {"history": []},
                        "topo": {"history": []}}
        for key in ["grid", "vgrid", "topo"]:
            existing_hist = existing.get(key, {"history": []})["history"]
            new_hist = self._object_histories[key]["history"]
            existing_files = {h["file"] for h in existing_hist}
            for entry in new_hist:
                if entry["file"] not in existing_files:
                    existing_hist.append(entry)
                    existing_files.add(entry["file"])
            existing[key] = {"history": existing_hist}
        with open(self._object_history_path, "w") as f:
            json.dump(existing, f, indent=2)

    @staticmethod
    def topo_is_compatible_with_grid(topo_file, grid):
        import xarray as xr
        import numpy as np
        import os
        import re

        # Clean grid name (already done outside, but safe to repeat)
        grid_name_clean = Case.clean_grid_name(getattr(grid, "name", ""))

        # Clean topo name from filename
        topo_fname = os.path.basename(topo_file)
        topo_name_clean = re.sub(r'^(ocean_topog_)+', '', topo_fname)
        topo_name_clean = re.sub(r'_[0-9a-f]{6}\.nc$', '', topo_name_clean)
        topo_name_clean = re.sub(r'\.nc$', '', topo_name_clean)

        if grid_name_clean != topo_name_clean:
            return False

        try:
            ds = xr.open_dataset(topo_file)
            # Check shape
            if "depth" not in ds:
                return False
            if ds["depth"].shape != (grid.ny, grid.nx):
                return False
            return True
        except Exception as e:
            return False
    
    def get_forcing_config_history(self):
        """Return a list of unique forcing_config dicts from global case history."""
        if not self._history_path.exists():
            return []
        with open(self._history_path, "r") as f:
            history = json.load(f)
        configs = []
        seen = set()
        for entry in history:
            fc = entry.get("forcing_config", {})
            key = json.dumps(fc, sort_keys=True)
            if key not in seen and fc:
                configs.append(fc)
                seen.add(key)
        return configs

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

    @staticmethod
    def clean_grid_name(name):
        import re
        # Remove all leading ocean_hgrid_ prefixes (even if repeated)
        name = re.sub(r'^(ocean_hgrid_)+', '', name)
        # Remove all leading ocean_vgrid_ prefixes (for vgrid)
        name = re.sub(r'^(ocean_vgrid_)+', '', name)
        # Remove all leading ocean_topog_ prefixes (for topo)
        name = re.sub(r'^(ocean_topog_)+', '', name)
        # Remove all trailing _[sessionid] (6 hex digits) segments, possibly repeated
        while re.search(r'_[0-9a-f]{6}$', name):
            name = re.sub(r'_[0-9a-f]{6}$', '', name)
        return name
        
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
    
        # --- Sanitize grid name before writing ---
        sanitized_name = self.clean_grid_name(self.ocn_grid.name)

        # MOM6 grid file
        self.ocn_grid.to_netcdf(
            inputdir / "ocnice" / f"ocean_hgrid_{sanitized_name}_{session_id}.nc",
            format="supergrid"
        )

        # MOM6 topography file
        self.ocn_topo.write_topo(
            inputdir / "ocnice" / f"ocean_topog_{sanitized_name}_{session_id}.nc"
        )

        # MOM6 vertical grid file
        self.ocn_vgrid.write(
            inputdir / "ocnice" / f"ocean_vgrid_{sanitized_name}_{session_id}.nc"
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
        boundary_info = dv.get_rectangular_segment_info(self.ocn_grid)
        if not self._large_data_workflow_called:

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
                Path(__file__).parent / "raw_data_access" / "large_data_workflow",
                large_data_workflow_path,
            )
            print(
                f"Large data workflow was called, please go to the large data workflow path: {large_data_workflow_path} and run the driver script there."
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
            config["paths"]["merged_dataset_path"] = str(self.inputdir/"ocnice")
            config["dates"]["start"] = self.expt.date_range[0].strftime(date_format)
            config["dates"]["end"] = self.expt.date_range[1].strftime(date_format)
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
            config["params"]["step"] = 5

            # Write out
            with open(large_data_workflow_path / "config.json", "w") as f:
                json.dump(config, f, indent=4)

            # Generate Initial Condition Script
            self.ProductFunctionRegistry.functions[product_name][function_name](
                [date_range[0], date_range[0]],
                boundary_info["ic"]["lat_min"],
                boundary_info["ic"]["lat_max"],
                boundary_info["ic"]["lon_min"],
                boundary_info["ic"]["lon_max"],
                forcing_dir_path,
                "ic" + "_unprocessed.nc",
            )

        # --- BEGIN REPRODUCIBILITY BLOCK ---
        # Save all config options for reproducibility
        forcing_config = {
            "date_range": date_range,
            "boundaries": boundaries,
            "tidal_constituents": tidal_constituents,
            "tpxo_elevation_filepath": str(tpxo_elevation_filepath) if tpxo_elevation_filepath else None,
            "tpxo_velocity_filepath": str(tpxo_velocity_filepath) if tpxo_velocity_filepath else None,
            "product_name": product_name,
            "function_name": function_name,
            "too_much_data": too_much_data,
            "large_data_workflow_path": str(self.inputdir / self.forcing_product_name / "large_data_workflow") if too_much_data else None,
        }
        # Save to CaseRecord (last entry in history)
        if self._history_path.exists():
            with open(self._history_path, "r") as f:
                history = json.load(f)
            if history:
                history[-1]["forcing_config"] = forcing_config
                with open(self._history_path, "w") as f:
                    json.dump(history, f, indent=2)
        # Also store on self for summary writing
        self.forcing_config = forcing_config

        # Optionally, record any scripts/configs generated
        self.forcing_scripts = []
        forcing_dir_path = self.inputdir / self.forcing_product_name
        if not too_much_data:
            # Look for bash scripts generated (e.g., get_glorys_data.sh)
            for script in forcing_dir_path.glob("*.sh"):
                self.forcing_scripts.append(str(script))
        else:
            # Large data workflow: record config.json, driver.py, README, etc.
            ldw_path = forcing_dir_path / "large_data_workflow"
            for fname in ["config.json", "driver.py", "README"]:
                fpath = ldw_path / fname
                if fpath.exists():
                    self.forcing_scripts.append(str(fpath))
        # --- END REPRODUCIBILITY BLOCK ---

        self._configure_forcings_called = True

        # Write summary after configuring forcings
        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=self.cesmroot,
            inputdir=self.inputdir,
            caseroot=self.caseroot,
        )

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

        # Write summary after processing forcings
        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=self.cesmroot,
            inputdir=self.inputdir,
            caseroot=self.caseroot,
        )

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

    def _log_user_nl_action(self, caseroot, action, model, var_val_pairs, forcing_config_before=None, forcing_config_after=None, comment=None):
        log_path = Path(self.caseroot) / "user_nl_history.json"
        entry = {
            "action": action,
            "model": model,
            "params": [(str(var), str(val)) for var, val in var_val_pairs],
            "forcing_config_before": forcing_config_before,
            "forcing_config_after": forcing_config_after,
        }
        if comment is not None and action == "append":
            entry["block_comment"] = comment
        lock = threading.Lock()
        with lock:
            if log_path.exists():
                with open(log_path, "r") as f:
                    history = json.load(f)
            else:
                history = []
            history.append(entry)
            with open(log_path, "w") as f:
                json.dump(history, f, indent=2)

    def append_user_nl_block(self, block, params, tpxo_elevation_filepath=None, tpxo_velocity_filepath=None):
        """
        Append a block to user_nl_mom and log the action, updating forcing_config and README.case.
        Optionally set TPXO filepaths for Tides block.
        """
        import copy
        forcing_config_before = copy.deepcopy(self.forcing_config)

        # --- Update forcing_config as needed ---
        if block == "Tides":
            for k, v in params:
                if k == "OBC_TIDE_CONSTITUENTS":
                    cleaned = v.strip('"')
                    self.forcing_config["tidal_constituents"] = [c.strip() for c in cleaned.split(",")]
            # Use provided filepaths if given, else use attributes
            self.forcing_config["tpxo_elevation_filepath"] = (
                str(tpxo_elevation_filepath)
                if tpxo_elevation_filepath is not None
                else (str(getattr(self, "tpxo_elevation_filepath", None)) if getattr(self, "tpxo_elevation_filepath", None) else None)
            )
            self.forcing_config["tpxo_velocity_filepath"] = (
                str(tpxo_velocity_filepath)
                if tpxo_velocity_filepath is not None
                else (str(getattr(self, "tpxo_velocity_filepath", None)) if getattr(self, "tpxo_velocity_filepath", None) else None)
            )

        # Add other block-specific updates here if needed

        # Remove any existing block with the same comment before appending
        self.remove_user_nl_block(block)

        forcing_config_after = copy.deepcopy(self.forcing_config)

        append_user_nl("mom", params, do_exec=True, comment=block)

        self._log_user_nl_action(
            self.caseroot,
            "append",
            "mom",
            params,
            forcing_config_before=forcing_config_before,
            forcing_config_after=forcing_config_after,
            comment=block,
        )
        
        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=self.cesmroot,
            inputdir=self.inputdir,
            caseroot=self.caseroot,
        )

    def remove_user_nl_block(self, block, clear_config=False):
        """
        Remove a block from user_nl_mom and log the action, updating forcing_config and README.case.
        If clear_config is True, also set related forcing_config fields to None.
        """
        import copy
        forcing_config_before = copy.deepcopy(self.forcing_config)

        # --- Update forcing_config as needed ---
        if block == "Tides" and clear_config:
            self.forcing_config["tidal_constituents"] = None
            self.forcing_config["tpxo_elevation_filepath"] = None
            self.forcing_config["tpxo_velocity_filepath"] = None

        # Add other block-specific updates here if needed

        forcing_config_after = copy.deepcopy(self.forcing_config)

        remove_user_nl(
            "mom",
            comment=block,
            do_exec=True,
            forcing_config_before=forcing_config_before,
            forcing_config_after=forcing_config_after,
        )

        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=self.cesmroot,
            inputdir=self.inputdir,
            caseroot=self.caseroot,
        )

    def configure_tides(
        self,
        tidal_constituents: list[str] | None = None,
        tpxo_elevation_filepath: str | Path | None = None,
        tpxo_velocity_filepath: str | Path | None = None,
    ):
        """
        Configure tidal constituents and related files for the case.
        """
        if tidal_constituents:
            if not isinstance(tidal_constituents, list) or not all(isinstance(c, str) for c in tidal_constituents):
                raise TypeError("tidal_constituents must be a list of strings.")
            if not (tpxo_elevation_filepath and tpxo_velocity_filepath):
                raise ValueError("TPXO elevation and velocity filepaths must be provided if tides are enabled.")
        self.tidal_constituents = tidal_constituents
        self.tpxo_elevation_filepath = Path(tpxo_elevation_filepath) if tpxo_elevation_filepath else None
        self.tpxo_velocity_filepath = Path(tpxo_velocity_filepath) if tpxo_velocity_filepath else None

        # Update forcing_config for reproducibility
        if hasattr(self, "forcing_config"):
            self.forcing_config["tidal_constituents"] = tidal_constituents
            self.forcing_config["tpxo_elevation_filepath"] = str(tpxo_elevation_filepath) if tpxo_elevation_filepath else None
            self.forcing_config["tpxo_velocity_filepath"] = str(tpxo_velocity_filepath) if tpxo_velocity_filepath else None
        if self._history_path.exists():
            with open(self._history_path, "r") as f:
                history = json.load(f)
            if history:
                history[-1]["forcing_config"] = self.forcing_config
                with open(self._history_path, "w") as f:
                    json.dump(history, f, indent=2)
        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=self.cesmroot,
            inputdir=self.inputdir,
            caseroot=self.caseroot,
        )

    def process_tides(self):
        """
        Process tides for the MOM6 case, if configured.
        """
        if not self.tidal_constituents:
            print("Tides are not enabled for this case.")
            return
        # Ensure the forcing directory exists
        forcing_dir = self.inputdir / "ocnice" / "forcing"
        forcing_dir.mkdir(exist_ok=True)
        # Call the regional_mom6 tide setup
        self.expt.setup_boundary_tides(
            tpxo_elevation_filepath=self.tpxo_elevation_filepath,
            tpxo_velocity_filepath=self.tpxo_velocity_filepath,
            tidal_constituents=self.tidal_constituents,
        )
        # Update user_nl_mom via _update_forcing_variables
        self._update_forcing_variables()
        if self._history_path.exists():
            with open(self._history_path, "r") as f:
                history = json.load(f)
            if history:
                history[-1]["forcing_config"] = self.forcing_config
                with open(self._history_path, "w") as f:
                    json.dump(history, f, indent=2)
        self.write_summary(
            casename=self.caseroot.name,
            cesmroot=str(self.cesmroot),
            inputdir=str(self.inputdir),
            caseroot=str(self.caseroot),
        )

    def _update_forcing_variables(self):
        """Update the runtime parameters of the case."""

        # Remove previous blocks to avoid duplication
        self.remove_user_nl_block("Initial conditions")
        self.remove_user_nl_block("Tides")
        self.remove_user_nl_block("Open boundary conditions")

        # Initial conditions
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
        self.append_user_nl_block("Initial conditions", ic_params)

        # Tides (optional)
        if getattr(self, "tidal_constituents", None):
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
            self.append_user_nl_block("Tides", tidal_params)
            obc_tide_n_constituents = len(self.tidal_constituents)
            obc_tide_constituents = '"' + ", ".join(self.tidal_constituents) + '"'
        else:
            obc_tide_n_constituents = 0
            obc_tide_constituents = '""'
            # Remove the Tides block if present
            self.remove_user_nl_block("Tides")

        # Open boundary conditions
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
            ("OBC_TIDE_N_CONSTITUENTS", obc_tide_n_constituents),
            ("OBC_TIDE_CONSTITUENTS", obc_tide_constituents),
        ]

        for seg in self.expt.boundaries:
            seg_ix = str(self.expt.find_MOM6_rectangular_orientation(seg)).zfill(3)
            seg_id = "OBC_SEGMENT_" + seg_ix
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

        self.append_user_nl_block("Open boundary conditions", obc_params)

        xmlchange("RUN_STARTDATE", str(self.date_range[0])[:10], is_non_local=self.cc._is_non_local())
        xmlchange("MOM6_MEMORY_MODE", "dynamic_symmetric", is_non_local=self.cc._is_non_local())

        print(f"Case is ready to be built: {self.caseroot}")

    # --- Get file paths for grid, vgrid, topo ---
    @staticmethod
    def get_grid_file(grid, inputdir=None):
        if inputdir is not None:
            ocd = Path(inputdir) / "ocnice"
            sanitized_name = Case.clean_grid_name(grid.name)
            files = sorted(ocd.glob(f"ocean_hgrid_{sanitized_name}_*.nc"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return str(files[0])
            # Fallback: return the most recent ocean_hgrid_*.nc file
            files = sorted(ocd.glob("ocean_hgrid_*.nc"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return str(files[0])
        return "unknown"

    @staticmethod
    def get_vgrid_file(vgrid, inputdir=None):
        if inputdir is not None:
            ocd = Path(inputdir) / "ocnice"
            sanitized_name = Case.clean_grid_name(vgrid.name)
            files = sorted(ocd.glob(f"ocean_vgrid_{sanitized_name}_*.nc"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return str(files[0])
            # Fallback: return the most recent ocean_vgrid_*.nc file
            files = sorted(ocd.glob("ocean_vgrid_*.nc"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return str(files[0])
        return "unknown"

    @staticmethod
    def get_topo_file(topo, inputdir=None):
        if inputdir is not None:
            ocd = Path(inputdir) / "ocnice"
            files = sorted(ocd.glob("ocean_topog_*.nc"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return str(files[0])
        return "unknown"
        
    def write_summary(self, casename, cesmroot, inputdir, caseroot):
        """Write README.case with the current configuration (overwrite previous summary)."""

        grid_file = self.get_grid_file(self.ocn_grid, inputdir=self.inputdir)
        vgrid_file = self.get_vgrid_file(self.ocn_vgrid, inputdir=self.inputdir)
        topo_file = self.get_topo_file(self.ocn_topo, inputdir=self.inputdir)

        readme_path = Path(caseroot) / "README.case"

        # If you want to preserve the case history section, extract it
        history_lines = []
        if readme_path.exists():
            with open(readme_path, "r") as f:
                lines = f.readlines()
            # Find the CaseRecord History section
            for i, line in enumerate(lines):
                if line.strip() == "CaseRecord History:":
                    history_lines = lines[:i+1]
                    # Add the rest of the history lines
                    for l in lines[i+1:]:
                        if l.strip().startswith("Case name:"):
                            break
                        history_lines.append(l)
                    break

        # Check if this case was restored from another CaseRecord
        restored_note = ""
        restored_forcing_note = ""
        restored_from_idx = None
        if self._history_path.exists():
            with open(self._history_path, "r") as f:
                history = json.load(f)
            if history and "restored_from" in history[-1]:
                restored_from_idx = history[-1]["restored_from"]
                msg = history[-1].get("message", "")
                restored_note = (
                    f"NOTE: This case was restored from CaseRecord index {restored_from_idx}."
                    + (f" ({msg})" if msg else "")
                    + "\n"
                )

        # If restored and forcing_config is present, add a note
        forcing_config = getattr(self, "forcing_config", {})
        if restored_from_idx is not None and forcing_config:
            restored_forcing_note = (
                f"NOTE: The forcing configuration below was inherited from the restored case (index {restored_from_idx}).\n"
                "      You may wish to update it by running configure_forcings().\n"
            )

        with open(readme_path, "w") as f:
            # Write the history section if present
            if history_lines:
                f.writelines(history_lines)
                f.write("\n")
            # Write the restored note if present
            if restored_note:
                f.write(restored_note)
            # Write the new summary
            f.write(f"Case name: {casename}\n")
            f.write(f"CESM root: {cesmroot}\n")
            f.write(f"Input dir: {inputdir}\n")
            f.write(f"Case dir:  {caseroot}\n")
            f.write(f"Created:   {datetime.now().isoformat()}\n")
            f.write("-" * 100 + "\n")
            f.write("Grid file:  {}\n".format(grid_file))
            f.write("VGrid file: {}\n".format(vgrid_file))
            f.write("Topo file:  {}\n".format(topo_file))
            f.write("-" * 100 + "\n")
            f.write("Notebook workflow code used to create this case:\n")
            f.write("from CrocoDash.case import Case\n")
            f.write("case = Case(\n")
            f.write(f"    cesmroot = '{cesmroot}',\n")
            f.write(f"    caseroot = '{caseroot}',\n")
            f.write(f"    inputdir = '{inputdir}',\n")
            f.write(f"    ocn_grid = grid,      # file: {grid_file}\n")
            f.write(f"    ocn_vgrid = vgrid,    # file: {vgrid_file}\n")
            f.write(f"    ocn_topo = topo,      # file: {topo_file}\n")
            f.write(f"    project = '{getattr(self, 'project', 'NCGD0011')}',\n")
            f.write(f"    override = {self.override},\n")
            f.write(f"    machine = '{self.cime.machine}'\n")
            f.write(")\n")
            f.write("-" * 100 + "\n")
            # --- Forcing reproducibility section ---
            if restored_forcing_note:
                f.write(restored_forcing_note)
            f.write("Forcing configuration used for this case:\n")
            f.write(json.dumps(forcing_config, indent=2))
            f.write("\n")
            if hasattr(self, "forcing_scripts") and self.forcing_scripts:
                f.write("Forcing scripts/configs generated:\n")
                for script in self.forcing_scripts:
                    f.write(f"  {script}\n")
            f.write("-" * 100 + "\n")