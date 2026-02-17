"""
Inspect is inordinately hard-coded, and probably can't be changed. Robust testing is needed to ensure we are picking up the correct information
"""

from pathlib import Path
import json
import tempfile
from mom6_bathy.grid import *
from mom6_bathy.topo import *
from mom6_bathy.vgrid import *
from CrocoDash.shareable.fork import create_case, generate_configure_forcing_args
from uuid import uuid4
import subprocess
from CrocoDash.logging import setup_logger
from contextlib import redirect_stdout, redirect_stderr
import logging
from CrocoDash.forcing_configurations.base import *
import importlib
import sys
import shutil

logger = setup_logger(__name__)


class ReadCrocoDashCase:
    """
    This class is a support case for reading CrocoDash-CESM Cases that uses CIME's case object
    This design started with individual functions, and got a bit too unwieldy!
    """

    def __init__(self, caseroot):
        self.caseroot = Path(caseroot)
        self._case = get_case_obj(caseroot)
        self.case_exists = True
        self._get_cesmroot()
        self._read_user_nls()
        self._identify_CrocoDashCase_init_args()
        self._identify_CrocoDashCase_forcing_config_args()
        self._read_xmlchanges()
        self._read_xmlfiles()
        self._read_sourcemods()

    def reread(self):
        self._read_user_nls()
        self._identify_CrocoDashCase_init_args()
        self._identify_CrocoDashCase_forcing_config_args()
        self._read_xmlchanges()
        self._read_xmlfiles()
        self._read_sourcemods()

    @property
    def case(self):
        if self._case is None:
            self._case = get_case_obj(self.caseroot)
        return self._case

    def generate_manifest(self):
        manifest = {
            "paths": {
                "casefiles": self.caseroot,
                "inputfiles": self.init_args["inputdir_ocnice"],
            },
            "user_nl_info": self.user_nl_objs,
            "init_args": self.init_args,
            "forcing_config": self.forcing_config,
            "sourcemods": self.sourcemods,
            "xmlchanges": self.xmlchanges,
        }
        return manifest

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

    def _identify_CrocoDashCase_init_args(self):

        logger.info(f"Finding initialization arguments from {self.caseroot}")

        self.init_args = {
            "inputdir_ocnice": self.get_user_nl_value("mom", "INPUTDIR"),
            "supergrid_path": self.get_user_nl_value("mom", "GRID_FILE"),
            "vgrid_path": self.get_user_nl_value("mom", "ALE_COORDINATE_CONFIG"),
            "topo_path": self.get_user_nl_value("mom", "TOPO_FILE"),
            "compset": self.case.get_value("COMPSET"),
            "atm_grid_name": self.case.get_value("ATM_GRID"),
        }

        return self.init_args

    def _identify_CrocoDashCase_forcing_config_args(self):

        logger.info(f"Loading forcing configuration from {self.caseroot}")
        # The input directory is where the forcing config is.

        # Find the input directory
        inputdir = self.get_user_nl_value("mom", "INPUTDIR")

        # Read in forcing config file
        forcing_config_path = Path(inputdir).parent / "extract_forcings" / "config.json"

        with open(forcing_config_path, "r") as f:
            self.forcing_config = json.load(f)
        return self.forcing_config

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

    def diff(self, other_case):
        """
        Diff this case (as the original) against another ReadCase (which is assumed to have been initialized the same). The diff indicates what unique features in the original are not in the new

        Returns a structured diff of:
        - xmlchanges
        - xml files
        - user_nls
        - sourcemods
        """
        diffs = {
            "xml_files_missing_in_new": sorted(
                list(self.xmlfiles - other_case.xmlfiles)
            ),
            "source_mods_missing_files": sorted(
                [str(f) for f in self.sourcemods - other_case.sourcemods]
            ),
            "xmlchanges_missing": sorted(
                k for k in self.xmlchanges.keys() if k not in other_case.xmlchanges
            ),
        }
        diffs["user_nl_missing_params"] = {}
        for key, value in self.user_nl_objs.items():
            diffs["user_nl_missing_params"][key] = []
            for subkey, subvalue in value.items():
                if isinstance(subvalue, dict):
                    for subsubkey, subsubvalue in subvalue.items():
                        if subsubkey not in other_case.user_nl_objs[key][subkey]:
                            diffs["user_nl_missing_params"][key].append((subsubkey))

        return diffs

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
            self.non_standard_case_info = self.diff(ReadCrocoDashCase(caseroot_tmp))
            return self.non_standard_case_info

    def bundle(self, output_folder_location):
        assert hasattr(
            self, "non_standard_case_info"
        ), "To bundle your case, you need to indentify non-standard CrocoDash first."
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
            if f.name.startswith(("forcing_", "init_")):
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

        # Write out manifest
        logger.info(f"Writing out ReadCrocoDashCase manifest...")
        with open(case_subfolder / "manifest.json", "w") as f:
            json.dump(self.generate_manifest(), f, indent=2, default=str)

        # Write out differences
        logger.info(f"Writing out non standard CrocoDash information...")
        with open(case_subfolder / "non_standard_case_info.json", "w") as f:
            json.dump(self.non_standard_case_info, f, indent=2, default=str)

        # From differences["xml_files"] and copy "sourceMods"
        xml_files_dir = case_subfolder / "xml_files"
        xml_files_dir.mkdir(exist_ok=True)
        for xml_file in self.non_standard_case_info["xml_files_missing_in_new"]:

            src = self.caseroot / xml_file
            logger.info(f"Copying non-standard xml files {src}")
            if src.exists():
                shutil.copy(src, xml_files_dir / xml_file)

            # Copy sourceMods
        source_mods_orig = self.caseroot / "SourceMods"
        source_mods_dst = case_subfolder / "SourceMods"
        source_mods_dst.mkdir(exist_ok=True)
        for mod_file in self.non_standard_case_info["source_mods_missing_files"]:
            src = source_mods_orig / mod_file
            logger.info(f"Copying sourcemods files {src}")
            if src.exists():
                dst = source_mods_dst / mod_file
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
        return case_subfolder


def get_case_obj(caseroot):
    cimeroot = run_xmlquery(caseroot, "CIMEROOT")
    sys.path.append(os.path.join(cimeroot, "CIME", "Tools"))
    from CIME.case import Case

    return Case(caseroot, read_only=True, non_local=True)


def run_xmlquery(caseroot, param):
    res = subprocess.run(
        ["./xmlquery", param, "-N"], cwd=str(caseroot), capture_output=True
    )
    return res.stdout.decode().strip().split(":")[1].strip()
