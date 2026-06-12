import copy
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import xarray as xr
import yaml
from CrocoDash.case import Case
from CrocoDash.forcing_configurations.base import *
from CrocoDash.grid import Grid
from CrocoDash.logging import setup_logger
from CrocoDash.shareable.apply import *
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.workflow import create_case_from_yaml, generate_configure_forcing_args

logger = setup_logger(__name__)


@dataclass
class BundleManifest:
    forcing_config: dict
    init_args: dict
    paths: dict = field(default_factory=dict)
    user_nl_info: dict = field(default_factory=dict)
    sourcemods: list = field(default_factory=list)
    xmlchanges: dict = field(default_factory=dict)


@dataclass
class BundleDifferences:
    xml_files_missing_in_new: list = field(default_factory=list)
    user_nl_missing_params: dict = field(default_factory=dict)
    source_mods_missing_files: list = field(default_factory=list)
    xmlchanges_missing: list = field(default_factory=list)


class ForkCrocoDashBundle:
    """
    Share a CESM case by inspecting an existing CrocoDash bundle, optionally copying
    non-standard components, resolving forcing configurations, and creating
    a new case with equivalent forcings.
    """

    def __init__(self, bundle_location):
        self.bundle_location = Path(bundle_location)

        yaml_file = self.bundle_location / "crocodash_case.yaml"
        assert yaml_file.exists(), f"Bundle is missing crocodash_case.yaml: {yaml_file}"
        with open(yaml_file) as f:
            self.bundle_yaml = yaml.safe_load(f)

        # Populate a minimal manifest for backwards-compatible apply_copy_plan usage
        state = self.bundle_yaml
        case_cfg = state.get("case", {})
        inputdir_ocnice = str(
            Path(state.get("grid", {}).get("supergrid_path", "")).parent
        )
        self.manifest = BundleManifest(
            forcing_config={},
            init_args={
                "inputdir_ocnice": inputdir_ocnice,
                "compset": case_cfg.get("compset", ""),
                "atm_grid_name": case_cfg.get("atm_grid_name", "TL319"),
            },
        )

        json_file = self.bundle_location / "non_standard_case_info.json"
        assert (
            json_file.exists()
        ), f"Bundle is missing non_standard_case_info.json: {json_file}"
        with open(json_file) as f:
            self.differences = BundleDifferences(**json.load(f))

        self._validate_bundle()

    def _validate_bundle(self):
        missing = []
        ocnice = self.bundle_location / "ocnice"

        for f in self.differences.xml_files_missing_in_new:
            path = self.bundle_location / "xml_files" / f
            if not path.exists():
                missing.append(str(path))

        for f in self.differences.source_mods_missing_files:
            path = self.bundle_location / "SourceMods" / f
            if not path.exists():
                missing.append(str(path))

        if not ocnice.exists():
            missing.append(str(ocnice))

        if missing:
            raise FileNotFoundError(
                "Bundle is incomplete. Missing files:\n"
                + "\n".join(f"  {f}" for f in missing)
            )

    def fork(
        self,
        cesmroot,
        machine,
        project_number,
        new_caseroot,
        new_inputdir,
        plan=None,
    ):
        """
        Create a new case from a bundle, guiding the user through YAML modifications.

        Prompts the user to update destination paths and machine settings, then
        optionally opens $EDITOR for deeper edits. After confirmation, creates the
        case and copies non-standard CESM state per the plan.

        Parameters
        ----------
        cesmroot : str or Path
            Path to the CESM root for the new case.
        machine : str
            Machine name for the new case.
        project_number : str
            Project/account number for the new case.
        new_caseroot : str or Path
            Path for the new case root.
        new_inputdir : str or Path
            Path for the new input directory.
        plan : dict, optional
            Which non-standard items to copy, e.g.
            ``{"xml_files": True, "user_nl": False, "source_mods": True, "xmlchanges": True}``.
            When omitted the user is asked interactively.
        """
        # Phase 1: build patched YAML with new destination values
        config = self._configure_yaml_for_forked_case_args(
            cesmroot, machine, project_number, new_caseroot, new_inputdir
        )

        # Phase 2: guided YAML review — prompt for each key field, offer editor
        config = self._guide_yaml_review(config)

        # Phase 3: resolve which non-standard CESM items to copy
        self._resolve_copy_plan(plan)

        # Phase 4: create the case
        logger.info("Creating new case from YAML...")
        self.case = create_case_from_yaml(config, override=True)

        # Phase 5: copy bundle ocnice files then apply non-standard CESM state
        logger.info("Copying forcing files from bundle...")
        bundle_ocnice = self.bundle_location / "ocnice"
        for src in bundle_ocnice.iterdir():
            dst = Path(self.case.inputdir) / "ocnice" / src.name
            if not dst.exists():
                shutil.copy(src, dst)

        logger.info("Applying non-standard CESM state per plan...")
        self.apply_copy_plan()

        self.case.validate_case()

        print(
            "\nYou're ready! Remember to run the extract_forcings driver to "
            "regenerate any forcing files for the new domain."
        )
        return self.case

    def _configure_yaml_for_forked_case_args(
        self, cesmroot, machine, project_number, new_caseroot, new_inputdir
    ):
        """Return a copy of bundle_yaml with destination fields configured for the forked case."""
        config = copy.deepcopy(self.bundle_yaml)
        config["case"]["cesmroot"] = str(cesmroot)
        config["case"]["machine"] = machine
        config["case"]["project"] = project_number
        config["case"]["caseroot"] = str(new_caseroot)
        config["case"]["inputdir"] = str(new_inputdir)
        # Point grid/topo/vgrid at bundle ocnice copies
        bundle_ocnice = str(self.bundle_location / "ocnice")
        if "supergrid_path" in config.get("grid", {}):
            config["grid"]["supergrid_path"] = str(
                self.bundle_location
                / "ocnice"
                / Path(config["grid"]["supergrid_path"]).name
            )
        if config.get("topo", {}).get("source", {}).get("type") == "from_file":
            config["topo"]["source"]["topo_file_path"] = str(
                self.bundle_location
                / "ocnice"
                / Path(config["topo"]["source"]["topo_file_path"]).name
            )
        if config.get("vgrid", {}).get("type") == "from_file":
            config["vgrid"]["filename"] = str(
                self.bundle_location / "ocnice" / Path(config["vgrid"]["filename"]).name
            )
        return config

    def _guide_yaml_review(self, config):
        """Walk the user through key YAML fields and offer $EDITOR for deeper edits."""
        print("\n=== Fork: Review Case Configuration ===")
        print(
            "The following fields have been pre-filled. Press Enter to keep each value.\n"
        )

        fields = [
            ("case.caseroot", ["case", "caseroot"]),
            ("case.inputdir", ["case", "inputdir"]),
            ("case.cesmroot", ["case", "cesmroot"]),
            ("case.machine", ["case", "machine"]),
            ("case.project", ["case", "project"]),
            ("case.compset", ["case", "compset"]),
        ]
        if "forcings" in config:
            fields += [
                ("forcings.date_range", ["forcings", "date_range"]),
                ("forcings.boundaries", ["forcings", "boundaries"]),
            ]

        for label, keys in fields:
            obj = config
            for k in keys[:-1]:
                obj = obj[k]
            current = obj[keys[-1]]
            response = ask_string(f"  {label} [{current}]: ", default=str(current))
            if response != str(current):
                if keys[-1] in ("date_range", "boundaries"):
                    obj[keys[-1]] = yaml.safe_load(response)
                else:
                    obj[keys[-1]] = response

        editor = os.environ.get("EDITOR", "")
        if editor and ask_yes_no("\nOpen $EDITOR for full YAML review?", default=False):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as tmp:
                yaml.dump(config, tmp, default_flow_style=False, sort_keys=False)
                tmp_path = tmp.name
            subprocess.call([editor, tmp_path])
            with open(tmp_path) as f:
                config = yaml.safe_load(f)
            Path(tmp_path).unlink()

        print("\nFinal configuration:")
        print(yaml.dump(config, default_flow_style=False, sort_keys=False))
        if not ask_yes_no("Proceed with this configuration?", default=True):
            raise RuntimeError("Fork cancelled by user.")

        return config

    def _resolve_copy_plan(self, plan):
        if plan is not None:
            self.plan = plan
            return

        self.plan = {}
        if self.differences.xml_files_missing_in_new:
            self.plan["xml_files"] = ask_yes_no(
                f"The following non-default XML files are missing in the new case:\n"
                f"{self.differences.xml_files_missing_in_new}\nCopy them over?"
            )

        if self.differences.user_nl_missing_params and any(
            self.differences.user_nl_missing_params.values()
        ):
            self.plan["user_nl"] = ask_yes_no(
                f"Non-default user_nl parameters detected:\n"
                f"{self.differences.user_nl_missing_params}\nCopy them over?"
            )

        if self.differences.source_mods_missing_files:
            self.plan["source_mods"] = ask_yes_no(
                f"The following source mods files exist in the old case:\n"
                f"{self.differences.source_mods_missing_files}\nCopy them over?"
            )

        if self.differences.xmlchanges_missing:
            self.plan["xmlchanges"] = ask_yes_no(
                f"Non-default xmlchange parameters detected:\n"
                f"{self.differences.xmlchanges_missing}\nApply them?"
            )

    def apply_copy_plan(self):
        if self.plan.get("xml_files"):
            copy_xml_files_from_case(
                self.bundle_location / "xml_files",
                self.case.caseroot,
                self.differences.xml_files_missing_in_new,
            )

        if self.plan.get("user_nl"):
            copy_user_nl_params_from_case(
                self.bundle_location,
                self.differences.user_nl_missing_params,
            )

        if self.plan.get("source_mods"):
            copy_source_mods_from_case(
                self.bundle_location,
                self.case.caseroot,
                self.differences.source_mods_missing_files,
            )

        if self.plan.get("xmlchanges"):
            apply_xmlchanges_to_case(
                self.bundle_location,
                self.differences.xmlchanges_missing,
            )

        # Forcing files are copied in fork() before apply_copy_plan is called.


def ask_string(prompt: str, default="") -> str:
    """
    Prompt the user for a string input and return it.

    Parameters:
    -----------
    prompt : str
        The message to display to the user.

    Returns:
    --------
    str
        The input string from the user.
    """
    try:
        response = input(prompt).strip()
        if response:
            return response
        else:
            return default
    except EOFError:
        print("\nNo input detected, returning empty string.")
        return ""


def ask_yes_no(prompt: str, default=True) -> bool:
    """
    Prompt the user with a yes/no question and return True for 'yes' and False for 'no'.

    Works in both command-line and Jupyter notebooks.

    Parameters:
    -----------
    prompt : str
        The question to present to the user.

    Returns:
    --------
    bool
        True if the user answers 'yes', False if 'no'.
    """
    try:
        answer = input(f"{prompt} (yes/no): ").strip().lower()
    except EOFError:
        print("No input available, assuming 'no'.")
        return False
    if answer in ("yes", "y"):
        return True
    elif answer in ("no", "n"):
        return False
    else:
        return default


def create_case(
    init_args, caseroot, inputdir, machine, project_number, cesmroot, compset
):
    initial_inputdir = Path(init_args["inputdir_ocnice"])
    # Create Grids
    grid = Grid.from_supergrid(initial_inputdir / init_args["supergrid_path"])

    # Read Topo
    topo_ds = xr.open_dataset(initial_inputdir / init_args["topo_path"])
    topo = Topo.from_topo_file(
        grid, initial_inputdir / init_args["topo_path"], topo_ds.attrs["min_depth"]
    )

    # Read Vgrid
    vgrid = VGrid.from_file(str(initial_inputdir / init_args["vgrid_path"]))

    case = Case(
        cesmroot=cesmroot,
        caseroot=caseroot,
        inputdir=inputdir,
        ocn_grid=grid,
        ocn_vgrid=vgrid,
        ocn_topo=topo,
        project=project_number,
        override=True,
        machine=machine,
        compset=compset,
        atm_grid_name=init_args["atm_grid_name"],
    )
    return case
