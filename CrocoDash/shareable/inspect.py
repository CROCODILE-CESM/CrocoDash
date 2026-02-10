"""
Identify is inordinately hard-coded, and probably can't be changed. Robust testing is needed to ensure we are picking up the correct information
"""

from pathlib import Path
import json
import tempfile
from mom6_bathy.grid import *
from mom6_bathy.topo import *
from mom6_bathy.vgrid import *
from CrocoDash.shareable.fork import create_case
from uuid import uuid4
import subprocess
from CrocoDash.logging import setup_logger
from contextlib import redirect_stdout, redirect_stderr
import logging
from CrocoDash.forcing_configurations import *
import importlib
import sys

logger = setup_logger(__name__)


class ReadCase:
    """
    This class is a support case for reading CrocoDash-CESM Cases that uses CIME's case object
    This design started with individual functions, and got a bit too unwieldy!
    """

    def __init__(self, caseroot):
        self.caseroot = Path(caseroot)
        self.case = get_case_obj(caseroot)
        self.case_exists = True
        self._identify_CrocoDashCase_init_args()
        self._identify_CrocoDashCase_forcing_config_args()
        self._read_user_nls()
        self._read_xmlchanges()
        self._read_xmlfiles()
        self._read_SourceMods()

    @classmethod
    def from_manifest(cls, manifest):
        obj = cls.__new__(cls)  # bypass __init__
        obj.caseroot = manifest["paths"]["casefiles"]
        obj.case = None
        obj.case_exists = False
        obj.init_args = manifest["init_args"]
        obj.forcing_config = manifest["forcing_config"]
        obj.xmlchanges = manifest["xmlchanges"]
        obj.SourceMods = manifest["SourceMods"]
        obj.user_nl_objs = manifest["user_nl_info"]
        for key in manifest["user_nl_info"]:
            obj.user_nl_objs = ParamGen()
        return obj

    def generate_manifest(self):
        manifest = {
            "paths": {
                "casefiles": self.caseroot,
                "inputfiles": self.init_args["inputdir_ocnice"],
            },
            "user_nl_info": self.user_nl_objs,
            "init_args": self.init_args,
            "forcing_config": self.forcing_config,
            "SourceMods": self.SourceMods,
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
        models = [
            token.split("%", 1)[0]
            for token in self.init_args["compset"].split("_")
            if token.split("%", 1)[0]
        ]
        for model in models:
            model_str = model.lower()
            if not model_str.startswith("s"):  # Represents stub component
                self.user_nl_objs[model_str] = read_user_nl_lines_as_obj(
                    self.caseroot, model_str
                )

    def _read_xmlfiles(self):
        self.xmlfiles = {f.name for f in original.caseroot.glob("*.xml")}

    def _read_SourceMods(self):
        self.sourcemods = {
            f.relative_to(original.caseroot / "SourceMods")
            for f in (original.caseroot / "SourceMods").rglob("*")
            if f.is_file()
        }

    def _identify_CrocoDashCase_init_args(self):

        logger.info(f"Finding initialization arguments from {self.caseroot}")

        self.init_args = {
            "inputdir_ocnice": self.user_nl_mom_obj["Global"]["INPUTDIR"]["value"],
            "supergrid_path": self.user_nl_mom_obj["Global"]["GRID_FILE"]["value"],
            "vgrid_path": self.user_nl_mom_obj["Global"]["ALE_COORDINATE_CONFIG"][
                "value"
            ],
            "topo_path": self.user_nl_mom_obj["Global"]["TOPO_FILE"]["value"],
            "compset": self.case.get_value("COMPSET"),
            "atm_grid_name": self.case.get_value("ATM_GRID"),
        }

        return self.init_args

    def _identify_CrocoDashCase_forcing_config_args(self):

        logger.info(f"Loading forcing configuration from {self.caseroot}")
        # The input directory is where the forcing config is.

        # Find the input directory
        inputdir = self.user_nl_mom_obj["Global"]["INPUTDIR"]["value"]

        # Read in forcing config file
        forcing_config_path = inputdir.parent / "extract_forcings" / "config.json"

        with open(forcing_config_path, "r") as f:
            self.forcing_config = json.load(f)
        return self.forcing_config

    def diff(self, other_case):
        """
        Diff this case (as the original) against another ReadCase (which is assumed to have been initialized the same). The diff indicates what unique features in the original are not in the new

        Returns a structured diff of:
        - xmlchanges
        - xml files
        - user_nls
        - SourceMods
        """
        diffs = {
            "xml_files_missing_in_new": sorted(
                list(self.xmlfiles - other_case.xmlfiles)
            ),
            "source_mods_missing_files": sorted(
                [str(f) for f in self.SourceMods - other_case.SourceMods]
            ),
            "xmlchanges_missing": sorted(
                k for k in self.xmlchanges.keys() if k not in othercase.xmlchanges
            ),
        }
        diffs["user_nl_missing_params"] = {}
        for key in self.user_nl_objs:
            diffs["user_nl_missing_params"][key] = sorted(
                k
                for k in self.user_nl_objs[key].keys()
                if k not in othercase.user_nl_objs[key]
            )

        return diffs

    def generate_configure_forcing_args(self):
        logger.info("Setup configuration arguments...")

        start_str = self.forcing_config["basic"]["dates"]["start"]
        end_str = self.forcing_config["basic"]["dates"]["end"]
        date_format = self.forcing_config["basic"]["dates"]["format"]
        start_dt = datetime.strptime(start_str, date_format)
        end_dt = datetime.strptime(end_str, date_format)

        date_range = [
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        ]

        configure_forcing_args = {
            "date_range": date_range,
            "boundaries": self.forcing_config["basic"]["general"][
                "boundary_number_conversion"
            ].keys(),
            "product_name": self.forcing_config["basic"]["forcing"]["product_name"],
            "function_name": self.forcing_config["basic"]["forcing"]["function_name"],
        }
        for key in self.forcing_config:
            if key == "basic":
                continue
            user_args = ForcingConfigRegistry.get_user_args(
                ForcingConfigRegistry.get_configurator_from_name(key)
            )
            for arg in user_args:
                if not arg.startswith("case_"):
                    configure_forcing_args[arg] = self.forcing_config[key]["inputs"][
                        arg
                    ]
        return configure_forcing_args

    def identify_non_standard_case_information_and_generate_manifest(
        self, cesmroot, machine, project_number
    ):

        og_case = ReadCase(self.caseroot)

        # Create fake "identical" case
        with tempfile.TemporaryDirectory() as tmp_dir:
            logger.info("Create temporary case for comparison...")
            logger.info("Init Args: " + json.dumps(og_case.init_args))
            tmp_path = Path(tmp_dir)
            logger.info("Temporary directory:", tmp_path)
            caseroot_tmp = tmp_path / f"temp_case-{uuid4().hex}"
            inputdir = tmp_path / "temp_inputdir"
            with open(os.devnull, "w") as devnull, redirect_stdout(
                devnull
            ), redirect_stderr(devnull):
                case = create_case(
                    og_case.init_args,
                    caseroot_tmp,
                    inputdir,
                    machine,
                    project_number,
                    cesmroot,
                    compset=og_case.init_args["compset"],
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
                case.configure_forcings(**og_case.generate_configure_forcing_args())
                config_logger.disabled = False

            # Diff
            logger.info("Taking the diff...")
            return og_case.diff(ReadCase(caseroot_tmp))

    def bundle(self, differences):
        pass


def read_user_nl_lines_as_obj(caseroot, user_nl_comp="mom"):

    # Import the CESM MOM_interface user_nl_mom reader
    cesmroot = Path(get_cesmroot_from_caseroot(caseroot))
    mod_path = (
        cesmroot
        / "components"
        / "mom"
        / "cime_config"
        / "MOM_RPS"
        / "FType_MOM_params.py"
    )
    spec = importlib.util.spec_from_file_location("FType_MOM_params", mod_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FType_MOM_params.from_MOM_input(
        Path(caseroot) / f"user_nl_{user_nl_comp}"
    )._data


def get_case_obj(caseroot):
    res = subprocess.run(
        ["./xmlquery", "CIMEROOT", "-N"], cwd=str(caseroot), capture_output=True
    )
    cimeroot = res.stdout.decode().strip().split(":")[1].strip()
    sys.path.append(os.path.join(cimeroot, "CIME", "Tools"))
    from CIME.case import Case

    return Case(caseroot, read_only=True, non_local=True)
