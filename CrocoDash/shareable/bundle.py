import dataclasses
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from uuid import uuid4

import yaml
from CrocoDash.forcing_configurations.base import *
from CrocoDash.grid import *
from CrocoDash.logging import setup_logger
from CrocoDash.shareable.apply import (
    INPUTDIR_FILE_PREFIXES,
    apply_xmlchanges_to_case,
    copy_source_mods_from_case,
    copy_user_nl_params_from_case,
    copy_xml_files_from_case,
)
from CrocoDash.shareable.fork import (
    BundleDifferences,
    BundleManifest,
    ForkCrocoDashBundle,
    create_case,
)
from CrocoDash.topo import *
from CrocoDash.vgrid import *
from CrocoDash.workflow import (
    case_to_yaml,
    create_case_from_yaml,
    generate_configure_forcing_args,
)

logger = setup_logger(__name__)


class BundleCrocoDashCase:
    """
    This class is a support case for reading CrocoDash-CESM Cases that uses CIME's case object
    This design started with individual functions, and got a bit too unwieldy!
    """

    def __init__(self, caseroot):
        self.caseroot = Path(caseroot)
        self._case = get_case_obj(caseroot)
        self.case_exists = True
        self._get_cesmroot()
        self._get_case_machine()
        self._get_case_project()
        self._read_user_nls()
        self._load_state_from_crocodash()
        self._read_xmlchanges()
        self._read_xmlfiles()
        self._read_sourcemods()

    def reread(self):
        self._read_user_nls()
        self._load_state_from_crocodash()
        self._read_xmlchanges()
        self._read_xmlfiles()
        self._read_sourcemods()

    @property
    def case(self):
        if self._case is None:
            self._case = get_case_obj(self.caseroot)
        return self._case

    def _read_xmlchanges(self):
        replay_path = self.caseroot / "replay.sh"
        self.xmlchanges = {}

        for line in replay_path.read_text().splitlines():
            line = line.strip()

            # skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            if "xmlchange" not in line:
                continue

            # drop everything before xmlchange
            parts = line.split("xmlchange", 1)[1].strip()

            # handle PARAM=VALUE or PARAM = VALUE
            if "=" not in parts:
                continue

            left, right = parts.split("=", 1)

            param = left.strip()
            value = right.strip()

            # remove quotes if present
            value = value.strip('"').strip("'")

            self.xmlchanges[param] = value

        return self.xmlchanges

    def _read_user_nls(self):
        self.user_nl_objs = {}
        # Read User_Nls
        models = self.case.get_values("COMP_CLASSES")
        for model in models:
            model_str = model.lower()
            compname = self.case.get_value("COMP_{}".format(model_str.upper()))
            if not compname.startswith("s"):
                self.user_nl_objs[compname] = self._read_user_nl_lines_as_obj(compname)

    def _read_xmlfiles(self):
        self.xmlfiles = {f.name for f in self.caseroot.glob("*.xml")}

    def _read_sourcemods(self):
        self.sourcemods = {
            f.relative_to(self.caseroot / "SourceMods")
            for f in (self.caseroot / "SourceMods").rglob("*")
            if f.is_file()
        }

    def _load_state_from_crocodash(self):
        """Load case parameters from crocodash_state.json and extract_forcings/config.json."""
        logger.info(f"Loading CrocoDash state from {self.caseroot}")
        self.case_yaml = case_to_yaml(self.caseroot)

        # Populate init_args in the legacy format for identify_non_standard / fork compatibility
        state_path = self.caseroot / "crocodash_state.json"
        with open(state_path) as f:
            state = json.load(f)
        inputdir_ocnice = str(Path(state["inputdir"]) / "ocnice")
        esmf_file = next(Path(inputdir_ocnice).glob("ESMF_mesh_*.nc"), None)
        self.init_args = {
            "inputdir_ocnice": inputdir_ocnice,
            "supergrid_path": Path(state["supergrid_path"]).name,
            "vgrid_path": Path(state["vgrid_path"]).name,
            "topo_path": Path(state["topo_path"]).name,
            "esmf_mesh_path": esmf_file.name if esmf_file else None,
            "compset": state["compset_lname"],
            "atm_grid_name": state.get("atm_grid_name", "TL319"),
        }

        forcing_config_path = (
            Path(state["inputdir"]) / "extract_forcings" / "config.json"
        )
        if forcing_config_path.exists():
            with open(forcing_config_path) as f:
                self.forcing_config = json.load(f)
        else:
            self.forcing_config = {}

        return self.init_args

    def get_user_nl_value(self, component, param):
        return (
            self.user_nl_objs[component.lower()]["Global"][param.upper()]["value"]
        ).replace("FILE:", "")

    def _read_user_nl_lines_as_obj(self, user_nl_comp="mom"):

        if not hasattr(self, "user_nl_reader"):
            # Import the CESM MOM_interface user_nl_mom reader
            mod_path = (
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
            self.caseroot / f"user_nl_{user_nl_comp}"
        )._data

    def _get_cesmroot(self):
        self.cesmroot = Path(self.case.get_value("SRCROOT"))
        return self.cesmroot

    def _get_case_machine(self):
        self.case_machine = self.case.get_value("MACH")
        return self.case_machine

    def _get_case_project(self):
        project = self.case.get_value("PROJECT", subgroup="case.run")
        self.case_project = project if project else None
        return self.case_project

    def diff(self, other_case):
        """
        Diff this case (as the original) against another ReadCase (which is assumed to have been initialized the same). The diff indicates what unique features in the original are not in the new

        Returns a structured diff of:
        - xmlchanges
        - xml files
        - user_nls
        - sourcemods
        """
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
            source_mods_missing_files=sorted(
                [str(f) for f in self.sourcemods - other_case.sourcemods]
            ),
            xmlchanges_missing=sorted(
                k for k in self.xmlchanges if k not in other_case.xmlchanges
            ),
            user_nl_missing_params=user_nl_missing,
        )

    def identify_non_standard_CrocoDash_case_information(
        self, cesmroot, machine, project_number
    ):

        # Create fake "identical" case
        with tempfile.TemporaryDirectory() as tmp_dir:
            logger.info("Create temporary case for comparison...")
            logger.info("Init Args: " + json.dumps(self.init_args))
            tmp_path = Path(tmp_dir)
            logger.info("Temporary directory:" + str(tmp_path))
            caseroot_tmp = tmp_path / f"temp_case-{uuid4().hex}"
            inputdir = tmp_path / "temp_inputdir"
            with open(os.devnull, "w") as devnull, redirect_stdout(
                devnull
            ), redirect_stderr(devnull):
                case = create_case(
                    self.init_args,
                    caseroot_tmp,
                    inputdir,
                    machine,
                    project_number,
                    cesmroot,
                    compset=self.init_args["compset"],
                )

            # Configure the forcings
            logger.info("Configuring temporary case...")
            with open(os.devnull, "w") as devnull, redirect_stdout(
                devnull
            ), redirect_stderr(devnull):
                config_logger = logging.getLogger(
                    "CrocoDash.forcing_configurations.base"
                )
                config_logger.disabled = True
                case.configure_forcings(
                    **generate_configure_forcing_args(self.forcing_config)
                )
                config_logger.disabled = False

            # Diff
            logger.info("Taking the diff...")
            self.non_standard_case_info = self.diff(BundleCrocoDashCase(caseroot_tmp))
            return self.non_standard_case_info

    def bundle(self, output_folder_location, machine=None, project=None):
        if not hasattr(self, "non_standard_case_info"):
            self.identify_non_standard_CrocoDash_case_information(
                self.cesmroot,
                machine if machine is not None else self.case_machine,
                project if project is not None else self.case_project,
            )
        ocnice_dir = self.get_user_nl_value("mom", "INPUTDIR")
        case_subfolder = (
            Path(output_folder_location) / f"{self.caseroot.name}_case_bundle"
        )
        case_subfolder.mkdir(parents=True, exist_ok=True)

        # From caseroot, copy all user_nls
        logger.info("Copying user_nl files...")
        for user_nl_file in self.caseroot.glob("user_nl_*"):
            shutil.copy(user_nl_file, case_subfolder / user_nl_file.name)

        # From caseroot, copy replay.sh (not necessarily used)
        logger.info("Copying replay.sh...")
        replay_sh = self.caseroot / "replay.sh"
        shutil.copy(replay_sh, case_subfolder / "replay.sh")

        ocnice_target = case_subfolder / "ocnice"
        ocnice_target.mkdir(parents=False, exist_ok=True)

        for f in Path(ocnice_dir).iterdir():
            if f.name.startswith(INPUTDIR_FILE_PREFIXES):
                logger.info(f"Copying {f}")
                shutil.copy(f, ocnice_target)
        # We'll get the configurations and copy into bundle ocnice
        for config, value in self.forcing_config.items():
            if config == "basic":
                continue
            # Deserialize
            configurator = ForcingConfigRegistry.get_configurator(value)
            output_paths = configurator.get_output_filepaths(ocnice_dir)

            for path in output_paths:
                logger.info(f"Copying {config} file: {path}...")
                shutil.copy(path, ocnice_target)

        # Copy grid files needed to reconstruct the case exactly
        for key in ("supergrid_path", "topo_path", "vgrid_path", "esmf_mesh_path"):
            filename = self.init_args.get(key)
            if filename:
                src = Path(ocnice_dir) / filename
                if src.exists():
                    logger.info(f"Copying grid file: {src}")
                    shutil.copy(src, ocnice_target / src.name)

        # Write YAML (replaces manifest.json — init_args + forcing_config in human-readable form)
        logger.info("Writing out crocodash_case.yaml...")
        with open(case_subfolder / "crocodash_case.yaml", "w") as f:
            yaml.dump(self.case_yaml, f, default_flow_style=False, sort_keys=False)

        # Write out differences
        logger.info(f"Writing out non standard CrocoDash information...")
        with open(case_subfolder / "non_standard_case_info.json", "w") as f:
            json.dump(
                dataclasses.asdict(self.non_standard_case_info),
                f,
                indent=2,
                default=str,
            )

        # Copy non-standard xml files and sourceMods
        xml_files_dir = case_subfolder / "xml_files"
        xml_files_dir.mkdir(exist_ok=True)
        for xml_file in self.non_standard_case_info.xml_files_missing_in_new:
            src = self.caseroot / xml_file
            logger.info(f"Copying non-standard xml files {src}")
            if src.exists():
                shutil.copy(src, xml_files_dir / xml_file)

        source_mods_orig = self.caseroot / "SourceMods"
        source_mods_dst = case_subfolder / "SourceMods"
        source_mods_dst.mkdir(exist_ok=True)
        for mod_file in self.non_standard_case_info.source_mods_missing_files:
            src = source_mods_orig / mod_file
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
    Duplicate a CrocoDash case to a new location. Machine, project, and cesmroot
    are read automatically from the original caseroot's crocodash_state.json.

    Parameters
    ----------
    caseroot : str or Path
        Path to the existing case to duplicate.
    new_caseroot : str or Path
        Path for the new case.
    new_inputdir : str or Path
        Path for the new input directory.
    bundle_dir : str or Path, optional
        Where to copy the bundle for reference. If None, no bundle is saved.
    """
    rcc = BundleCrocoDashCase(caseroot)
    rcc.identify_non_standard_CrocoDash_case_information(
        rcc.cesmroot, rcc.case_machine, rcc.case_project
    )

    # Patch paths in the YAML for the new location
    config = rcc.case_yaml.copy()
    config["case"] = config["case"].copy()
    config["case"]["caseroot"] = str(new_caseroot)
    config["case"]["inputdir"] = str(new_inputdir)

    result = create_case_from_yaml(config, override=True)

    # Copy all non-standard CESM state (full plan)
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

    # Optionally save a bundle alongside the new case
    if bundle_dir is not None:
        rcc.bundle(bundle_dir)

    return result


def get_case_obj(caseroot):
    cimeroot = run_xmlquery(caseroot, "CIMEROOT")
    sys.path.append(cimeroot)
    from CIME.case import Case

    return Case(caseroot, read_only=True, non_local=True)


def run_xmlquery(caseroot, param):
    res = subprocess.run(
        ["./xmlquery", param, "-N"], cwd=str(caseroot), capture_output=True
    )
    return res.stdout.decode().strip().split(":")[1].strip()
