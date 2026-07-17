"""
shareable — case portability across user boundaries.

Built on top of recipe.py, which handles programmatic case creation from YAML.
This module adds the layer for sharing a configured case with another user:

  Person A (sender)
    CaseBundle(caseroot)
      → identifies what makes the case non-standard beyond a plain CrocoDash setup
        (SourceMods, xmlchanges, extra XML files, user_nl tweaks)
      → bundle(output_dir) packages everything into a portable folder

  Person B (recipient)
    ForkBundle(bundle_dir)
      → guides the user through updating paths, machine, compset, and forcings
      → recreates the case via recipe.py
      → applies the captured non-standard CESM state

The bundle folder is the artifact that crosses the user boundary.
duplicate_case() is a convenience for copying a case within the same user context.
"""

import copy
import dataclasses
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import yaml
from visualCaseGen.custom_widget_types.case_tools import xmlchange, append_user_nl
from CrocoDash.forcing_configurations.base import *
from CrocoDash.forcing_configurations import *
from CrocoDash.logging import setup_logger
from CrocoDash.recipe import case_to_yaml, create_case_from_yaml
from CrocoDash import case_state

logger = setup_logger(__name__)

INPUTDIR_FILE_PREFIXES = ("forcing_obc_segment_", "init_")


# ---------------------------------------------------------------------------
# Helpers for applying non-standard CESM state from a bundle
# ---------------------------------------------------------------------------


def copy_xml_files_from_case(old_caseroot, new_caseroot, filenames):
    old_caseroot = Path(old_caseroot)
    new_caseroot = Path(new_caseroot)
    for name in filenames:
        logger.info(f"Copying {old_caseroot / name} into new caseroot")
        shutil.copy(old_caseroot / name, new_caseroot / name)


def copy_user_nl_params_from_case(old_caseroot, usernlparams):
    for key in usernlparams:
        usernl = Path(old_caseroot) / f"user_nl_{key}"
        with usernl.open() as f:
            for line in f:
                line = line.strip()
                if line.startswith("!") or "=" not in line:
                    continue
                param, value = line.split("=", 1)
                param = param.split()[0]
                if param in usernlparams[key]:
                    logger.info(f"Adding {param}={value} into user_nl_{key}")
                    append_user_nl(key, [(param, value)], do_exec=True)


def copy_source_mods_from_case(old_caseroot, new_caseroot, short_filepaths):
    old_caseroot = Path(old_caseroot)
    new_caseroot = Path(new_caseroot)
    for path in short_filepaths:
        path = Path(path)
        logger.info(f"Adding {old_caseroot / 'SourceMods' / path} into new caseroot")
        shutil.copy(
            old_caseroot / "SourceMods" / path, new_caseroot / "SourceMods" / path
        )


def apply_xmlchanges_to_case(old_caseroot, xmlchangeparams):
    replay = Path(old_caseroot) / "replay.sh"
    with replay.open() as f:
        for line in f:
            line = line.strip()
            if not line.startswith("./xmlchange"):
                continue
            _, kv = line.split(None, 1)
            param, value = kv.split("=", 1)
            if param in xmlchangeparams:
                logger.info(f"Running {param}={value} xmlchange to new caseroot")
                xmlchange(param, value, is_non_local=True)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BundleDifferences:
    """Non-standard CESM state in a case beyond what recipe.py would produce."""

    xml_files_missing_in_new: list = field(default_factory=list)
    user_nl_missing_params: dict = field(default_factory=dict)
    source_mods_missing_files: list = field(default_factory=list)
    xmlchanges_missing: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# CaseBundle
# ---------------------------------------------------------------------------


class CaseBundle:
    """
    Sender-side entry point for sharing a CrocoDash case.

    Reads a live case and identifies everything that makes it non-standard beyond
    what recipe.py would produce by default: extra XML files, user_nl tweaks,
    SourceMods, and xmlchanges. Packages all of it into a portable bundle folder
    that can be handed off to another user.

    Typical usage::

        bundle = CaseBundle(caseroot)
        bundle.identify_non_standard_case_info(cesmroot, machine, project)
        bundle_path = bundle.bundle(output_dir)
        # hand bundle_path to the recipient
    """

    def __init__(self, caseroot):
        self.caseroot = Path(caseroot)
        # Load YAML first — cesmroot, machine, project come from there
        self._load_state_from_crocodash()
        # CIME object needed only for user_nl parsing
        self._case = _get_case_obj(caseroot)
        self._read_user_nls()
        self._read_xmlchanges()
        self._read_xmlfiles()
        self._read_sourcemods()

    def _load_state_from_crocodash(self):
        logger.info(f"Loading CrocoDash state from {self.caseroot}")
        self.case_yaml = case_to_yaml(self.caseroot)
        self.cesmroot = Path(self.case_yaml["case"]["cesmroot"])
        self.case_machine = self.case_yaml["case"]["machine"]
        self.case_project = self.case_yaml["case"].get("project")

        # init_args needed for bundle() grid-file copying (esmf_mesh via glob)
        state = case_state.read(self.caseroot)
        inputdir_ocnice = str(Path(state["inputdir"]) / "ocnice")
        esmf_file = next(Path(inputdir_ocnice).glob("ESMF_mesh_*.nc"), None)
        self.init_args = {
            "inputdir_ocnice": inputdir_ocnice,
            "supergrid_path": Path(state["supergrid_path"]).name,
            "vgrid_path": Path(state["vgrid_path"]).name,
            "topo_path": Path(state["topo_path"]).name,
            "esmf_mesh_path": esmf_file.name if esmf_file else None,
        }

        forcing_config_path = (
            Path(state["inputdir"]) / "extract_forcings" / "config.json"
        )
        if forcing_config_path.exists():
            with open(forcing_config_path) as f:
                self.forcing_config = json.load(f)
        else:
            self.forcing_config = {}

    def _read_xmlchanges(self):
        replay_path = self.caseroot / "replay.sh"
        self.xmlchanges = {}
        for line in replay_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "xmlchange" not in line:
                continue
            parts = line.split("xmlchange", 1)[1].strip()
            if "=" not in parts:
                continue
            left, right = parts.split("=", 1)
            self.xmlchanges[left.strip()] = right.strip().strip('"').strip("'")
        return self.xmlchanges

    def _read_user_nls(self):
        self.user_nl_objs = {}
        models = self._case.get_values("COMP_CLASSES")
        for model in models:
            model_str = model.lower()
            compname = self._case.get_value("COMP_{}".format(model_str.upper()))
            if not compname.startswith("s"):
                self.user_nl_objs[compname] = self._read_user_nl_lines_as_obj(compname)

    def _read_xmlfiles(self):
        self.xmlfiles = {f.name for f in self.caseroot.glob("*.xml")}

    def _read_sourcemods(self):
        self.sourcemods = {
            str(f.relative_to(self.caseroot / "SourceMods"))
            for f in (self.caseroot / "SourceMods").rglob("*")
            if f.is_file()
        }

    def get_user_nl_value(self, component, param):
        return (
            self.user_nl_objs[component.lower()]["Global"][param.upper()]["value"]
        ).replace("FILE:", "")

    def _read_user_nl_lines_as_obj(self, user_nl_comp="mom"):
        if not hasattr(self, "user_nl_reader"):
            mod_path = str(
                self.cesmroot
                / "components"
                / "mom"
                / "cime_config"
                / "MOM_RPS"
                / "FType_MOM_params.py"
            )
            spec = importlib.util.spec_from_file_location("FType_MOM_params", mod_path)
            self.user_nl_reader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.user_nl_reader)
        return self.user_nl_reader.FType_MOM_params.from_MOM_input(
            str(self.caseroot / f"user_nl_{user_nl_comp}")
        )._data

    def diff(self, other_case):
        """Return a BundleDifferences of what this case has that other_case does not."""
        user_nl_missing = {}
        for key, value in self.user_nl_objs.items():
            user_nl_missing[key] = []
            for subkey, subvalue in value.items():
                if isinstance(subvalue, dict):
                    for subsubkey in subvalue:
                        if subsubkey not in other_case.user_nl_objs[key][subkey]:
                            user_nl_missing[key].append(subsubkey)
        return BundleDifferences(
            xml_files_missing_in_new=sorted(list(self.xmlfiles - other_case.xmlfiles)),
            source_mods_missing_files=sorted(self.sourcemods - other_case.sourcemods),
            xmlchanges_missing=sorted(
                k for k in self.xmlchanges if k not in other_case.xmlchanges
            ),
            user_nl_missing_params=user_nl_missing,
        )

    def identify_non_standard_case_info(self, cesmroot, machine, project_number):
        """
        Diff this case against a freshly created reference case to find what's non-standard.

        Uses recipe.py to spin up a temporary reference case with the same grid, topo,
        vgrid, and forcing configuration (configure_only=True, so forcings are not
        processed). Anything in this case that the reference case lacks is captured in
        self.non_standard_case_info as a BundleDifferences. Called automatically by
        bundle() if not already run.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logger.info("Create temporary case for comparison in " + str(tmp_path))
            caseroot_tmp = tmp_path / f"temp_case-{uuid4().hex}"
            inputdir = tmp_path / "temp_inputdir"

            config = copy.deepcopy(self.case_yaml)
            config["case"]["cesmroot"] = str(cesmroot)
            config["case"]["machine"] = machine
            config["case"]["project"] = project_number
            config["case"]["caseroot"] = str(caseroot_tmp)
            config["case"]["inputdir"] = str(inputdir)

            with open(os.devnull, "w") as devnull, redirect_stdout(
                devnull
            ), redirect_stderr(devnull):
                create_case_from_yaml(config, override=True, configure_only=True)

            logger.info("Taking the diff...")
            self.non_standard_case_info = self.diff(CaseBundle(caseroot_tmp))
            return self.non_standard_case_info

    def bundle(self, output_folder_location, machine=None, project=None):
        """
        Package this case into a portable bundle folder.

        Runs identify_non_standard_case_info() automatically if not already called.
        The bundle contains the full recipe YAML, the non-standard diff, all ocnice
        input files, user_nl files, replay.sh, and any SourceMods or extra XML files.
        """
        if not hasattr(self, "non_standard_case_info"):
            self.identify_non_standard_case_info(
                self.cesmroot,
                machine if machine is not None else self.case_machine,
                project if project is not None else self.case_project,
            )
        ocnice_dir = self.get_user_nl_value("mom", "INPUTDIR")
        case_subfolder = (
            Path(output_folder_location) / f"{self.caseroot.name}_case_bundle"
        )
        case_subfolder.mkdir(parents=True, exist_ok=True)

        logger.info("Copying user_nl files...")
        for user_nl_file in self.caseroot.glob("user_nl_*"):
            shutil.copy(user_nl_file, case_subfolder / user_nl_file.name)

        logger.info("Copying replay.sh...")
        shutil.copy(self.caseroot / "replay.sh", case_subfolder / "replay.sh")

        ocnice_target = case_subfolder / "ocnice"
        ocnice_target.mkdir(parents=False, exist_ok=True)

        for f in Path(ocnice_dir).iterdir():
            if f.name.startswith(INPUTDIR_FILE_PREFIXES):
                logger.info(f"Copying {f}")
                shutil.copy(f, ocnice_target)

        for config, value in self.forcing_config.items():
            if config in {"conditions", "caseroot"}:
                continue
            configurator = ForcingConfigRegistry.get_configurator(value)
            for path in configurator.get_output_filepaths(ocnice_dir):
                logger.info(f"Copying {config} file: {path}...")
                shutil.copy(path, ocnice_target)

        for key in ("supergrid_path", "topo_path", "vgrid_path", "esmf_mesh_path"):
            filename = self.init_args.get(key)
            if filename:
                src = Path(ocnice_dir) / filename
                if src.exists():
                    logger.info(f"Copying grid file: {src}")
                    shutil.copy(src, ocnice_target / src.name)

        logger.info("Writing out crocodash_case.yaml...")
        with open(case_subfolder / "crocodash_case.yaml", "w") as f:
            yaml.dump(self.case_yaml, f, default_flow_style=False, sort_keys=False)

        logger.info("Writing out non standard CrocoDash information...")
        with open(case_subfolder / "non_standard_case_info.json", "w") as f:
            json.dump(
                dataclasses.asdict(self.non_standard_case_info),
                f,
                indent=2,
                default=str,
            )

        xml_files_dir = case_subfolder / "xml_files"
        xml_files_dir.mkdir(exist_ok=True)
        for xml_file in self.non_standard_case_info.xml_files_missing_in_new:
            src = self.caseroot / xml_file
            logger.info(f"Copying non-standard xml files {src}")
            if src.exists():
                shutil.copy(src, xml_files_dir / xml_file)

        source_mods_dst = case_subfolder / "SourceMods"
        source_mods_dst.mkdir(exist_ok=True)
        for mod_file in self.non_standard_case_info.source_mods_missing_files:
            src = self.caseroot / "SourceMods" / mod_file
            logger.info(f"Copying sourcemods files {src}")
            if src.exists():
                dst = source_mods_dst / mod_file
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
        return case_subfolder

    def duplicate_case(self, new_caseroot, new_inputdir, bundle_dir=None):
        return duplicate_case(
            self.caseroot, new_caseroot, new_inputdir, bundle_dir=bundle_dir
        )


def duplicate_case(caseroot, new_caseroot, new_inputdir, bundle_dir=None):
    """
    Copy a CrocoDash case to a new location within the same user context.

    Reads machine, project, and cesmroot from the original case's crocodash_state.json,
    identifies any non-standard CESM state, recreates the case via recipe.py, and
    transfers the non-standard state to the new location. Pass bundle_dir to also save
    a portable bundle as a side effect.
    """
    rcc = CaseBundle(caseroot)
    rcc.identify_non_standard_case_info(
        rcc.cesmroot, rcc.case_machine, rcc.case_project
    )

    config = rcc.case_yaml.copy()
    config["case"] = config["case"].copy()
    config["case"]["caseroot"] = str(new_caseroot)
    config["case"]["inputdir"] = str(new_inputdir)

    result = create_case_from_yaml(config, override=True, configure_only=True)

    old_ocnice = Path(rcc.init_args["inputdir_ocnice"])
    if old_ocnice.exists():
        new_ocnice = Path(new_inputdir) / "ocnice"
        new_ocnice.mkdir(parents=True, exist_ok=True)
        for src in old_ocnice.iterdir():
            dst = new_ocnice / src.name
            if not dst.exists():
                shutil.copy(src, dst)

    if rcc.non_standard_case_info.xml_files_missing_in_new:
        copy_xml_files_from_case(
            rcc.caseroot,
            result.caseroot,
            rcc.non_standard_case_info.xml_files_missing_in_new,
        )
    if rcc.non_standard_case_info.user_nl_missing_params and any(
        rcc.non_standard_case_info.user_nl_missing_params.values()
    ):
        copy_user_nl_params_from_case(
            rcc.caseroot, rcc.non_standard_case_info.user_nl_missing_params
        )
    if rcc.non_standard_case_info.source_mods_missing_files:
        copy_source_mods_from_case(
            rcc.caseroot,
            result.caseroot,
            rcc.non_standard_case_info.source_mods_missing_files,
        )
    if rcc.non_standard_case_info.xmlchanges_missing:
        apply_xmlchanges_to_case(
            rcc.caseroot, rcc.non_standard_case_info.xmlchanges_missing
        )

    if bundle_dir is not None:
        rcc.bundle(bundle_dir)

    return result


# ---------------------------------------------------------------------------
# ForkBundle
# ---------------------------------------------------------------------------


class ForkBundle:
    """
    Recipient-side entry point for creating a case from a bundle.

    Takes a bundle folder produced by CaseBundle and recreates the case for a new
    user or environment. Guides the recipient through updating destination paths,
    machine, and optionally the compset and forcing configuration interactively.
    Uses recipe.py to rebuild the case from the (possibly modified) YAML, then
    applies any non-standard CESM state that was captured at bundle time.

    Typical usage::

        fork = ForkBundle(bundle_dir)
        case = fork.fork(
            cesmroot="/path/to/cesm",
            machine="derecho",
            project_number="PROJ123",
            new_caseroot="/path/to/new_case",
            new_inputdir="/path/to/new_inputdir",
        )
    """

    def __init__(self, bundle_location):
        self.bundle_location = Path(bundle_location)

        yaml_file = self.bundle_location / "crocodash_case.yaml"
        assert yaml_file.exists(), f"Bundle is missing crocodash_case.yaml: {yaml_file}"
        with open(yaml_file) as f:
            self.bundle_yaml = yaml.safe_load(f)

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
            if not (self.bundle_location / "xml_files" / f).exists():
                missing.append(str(self.bundle_location / "xml_files" / f))

        for f in self.differences.source_mods_missing_files:
            if not (self.bundle_location / "SourceMods" / f).exists():
                missing.append(str(self.bundle_location / "SourceMods" / f))

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
        Recreate the bundled case for a new user or environment.

        Guides the recipient through an interactive YAML review — prompting for
        destination paths, machine, project, and optionally compset and forcing
        date range. Offers $EDITOR for deeper changes (e.g. swapping the compset
        or adjusting forcing kwargs). After confirmation, creates the case via
        recipe.py and applies the non-standard CESM state captured at bundle time.

        Parameters
        ----------
        cesmroot : str or Path
            CESM root on the recipient's machine.
        machine : str
            Machine name for the new case.
        project_number : str
            Project/account number for the new case.
        new_caseroot : str or Path
            Destination path for the new case root.
        new_inputdir : str or Path
            Destination path for the new input directory.
        plan : dict, optional
            Which non-standard CESM state to transfer, keyed by
            ``"xml_files"``, ``"user_nl"``, ``"source_mods"``, ``"xmlchanges"``.
            When omitted the recipient is asked interactively for each category.
        """
        config = self._configure_yaml_for_forked_case_args(
            cesmroot, machine, project_number, new_caseroot, new_inputdir
        )
        config = self._guide_yaml_review(config)
        self._resolve_copy_plan(plan)

        logger.info("Creating new case from YAML...")
        self.case = create_case_from_yaml(config, override=True, configure_only=True)

        logger.info("Copying forcing files from bundle...")
        bundle_ocnice = self.bundle_location / "ocnice"
        for src in bundle_ocnice.iterdir():
            dst = Path(self.case.inputdir) / "ocnice" / src.name
            if not dst.exists():
                shutil.copy(src, dst)

        logger.info("Applying non-standard CESM state per plan...")
        self.apply_copy_plan()

        self.case.validate_case()

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


# ---------------------------------------------------------------------------
# CLI input helpers
# ---------------------------------------------------------------------------


def ask_string(prompt: str, default="") -> str:
    try:
        response = input(prompt).strip()
        return response if response else default
    except EOFError:
        print(f"\nNo input detected, using default: {default!r}")
        return default


def ask_yes_no(prompt: str, default=True) -> bool:
    try:
        answer = input(f"{prompt} (yes/no): ").strip().lower()
    except EOFError:
        print("No input available, assuming 'no'.")
        return False
    if answer in ("yes", "y"):
        return True
    if answer in ("no", "n"):
        return False
    return default


# ---------------------------------------------------------------------------
# CIME utilities
# ---------------------------------------------------------------------------


def _get_case_obj(caseroot):
    cimeroot = _run_xmlquery(caseroot, "CIMEROOT")
    sys.path.append(cimeroot)
    from CIME.case import Case

    return Case(caseroot, read_only=True, non_local=True)


def _run_xmlquery(caseroot, param):
    res = subprocess.run(
        ["./xmlquery", param, "-N"], cwd=str(caseroot), capture_output=True
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"xmlquery {param} failed in {caseroot}:\n{res.stderr.decode().strip()}"
        )
    return res.stdout.decode().strip().split(":")[1].strip()
