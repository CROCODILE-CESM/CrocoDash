"""
Identify is inordinately hard-coded, and probably can't be changed. Robust testing is needed to ensure we are picking up the correct information
"""

from pathlib import Path
import json
import tempfile
from mom6_bathy.grid import *
from mom6_bathy.topo import *
from mom6_bathy.vgrid import *
import xarray as xr
from CrocoDash.shareable.prompt import create_case
from uuid import uuid4

def identify_non_standard_case_information(caseroot, cesmroot, machine, project_number):

    # 1. Read in where to find CrocoDash init args
    init_args = identify_CrocoDashCase_init_args(caseroot)

    # 2. Read in where to find CrocoDash forcing_config args
    forcing_config = identify_CrocoDashCase_forcing_config_args(caseroot)

    with tempfile.TemporaryDirectory() as tmp_dir:

        tmp_path = Path(tmp_dir)
        print("Temporary directory:", tmp_path)
        caseroot_tmp = tmp_path / f"temp_case-{uuid4().hex}"
        inputdir = tmp_path / "temp_inputdir"
        case = create_case(init_args, caseroot_tmp, inputdir, machine, project_number, cesmroot, compset=init_args["compset"])

        start_str = forcing_config["basic"]["dates"]["start"]  # e.g., "20000101"
        end_str = forcing_config["basic"]["dates"]["end"]  # e.g., "20000201"
        date_format = forcing_config["basic"]["dates"]["format"]  # e.g., "%Y%m%d"

        start_dt = datetime.strptime(start_str, date_format)
        end_dt = datetime.strptime(end_str, date_format)

        date_range = [
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        ]

        configure_forcing_args = {
            "date_range": date_range,
            "boundaries": forcing_config["basic"]["general"]["boundary_number_conversion"].keys(),
            "product_name": forcing_config["basic"]["forcing"]["product_name"],
            "function_name": forcing_config["basic"]["forcing"]["function_name"],
        }
        for key in forcing_config:
            if key == "basic":
                continue
            for subkey in forcing_config[key]["inputs"]:
                if not key.startswith("case_"):
                    configure_forcing_args[subkey] = forcing_config[key]["inputs"][
                        subkey
                    ]

        case.configure_forcings(**configure_forcing_args)
        differences = diff_CESM_cases(original=caseroot, new=caseroot_tmp)

    return {
        "differences": differences,
        "init_args": init_args,
        "forcing_config": forcing_config,
    }

    pass


def identify_CrocoDashCase_init_args(caseroot):

    # 1. Read in where to find CrocoDash init args
    caseroot = Path(caseroot)
    # You need compset & grids at a minimum
    init_args = {}

    user_nl_mom_lines = read_user_nl_mom_lines(caseroot)
    for line in user_nl_mom_lines:
        if "inputdir" in line:
            init_args["inputdir"] = Path(line.split("=")[1].strip())
        if "GRID_FILE" in line:
            init_args["supergrid_path"] = Path(line.split("=")[1].strip())
        if "ALE_COORDINATE_CONFIG" in line:
            init_args["vgrid_path"] = Path(
                line.split("=")[1].strip().replace("FILE:", "").strip()
            )
        if "TOPO_FILE" in line:
            init_args["topo_path"] = Path(line.split("=")[1].strip())

    # Get compset
    with open(caseroot / "replay.sh", "r") as f:
        replay_lines = f.readlines()

    for line in replay_lines:
        if "--compset" in line:
            init_args["compset"] = line.split("--compset")[1].split()[0].strip()

    required_keys = ["inputdir", "supergrid_path", "vgrid_path", "topo_path", "compset"]
    assert all(
        key in init_args for key in required_keys
    ), "Not all required init args found"

    return init_args


def identify_CrocoDashCase_forcing_config_args(caseroot):

    # The input directory is where the forcing config is.

    # Read in user_nl_mom
    user_nl_mom_lines = read_user_nl_mom_lines(caseroot)

    # Find the input directory
    inputdir = None
    for line in user_nl_mom_lines:
        if "inputdir" in line:
            inputdir = Path(line.split("=")[1].strip())
            break

    # Read in forcing config file
    forcing_config_path = (
        inputdir.parent / "extract_forcings" / "config.json"
    )  # Hardcoded path, at least one test needed for this

    with open(forcing_config_path, "r") as f:
        forcing_config = json.load(f)
    return forcing_config


def diff_CESM_cases(original, new):
    """
    Compare two CESM case directories and return what existed in `original` but is missing in `new`.

    Parameters:
    -----------
    original : Path
    new : Path

    Returns:
    --------
    dict
        {
            "xml_files_missing_in_new": [...],
            "user_nl_missing_params": {filename: [missing_parameters]},
            "source_mods_missing_files": [...],
            "xmlchanges_missing": [parameters_missing_in_new]
        }
    """
    original = Path(original)
    new = Path(new)

    diffs = {
        "xml_files_missing_in_new": [],
        "user_nl_missing_params": {},
        "source_mods_missing_files": [],
        "xmlchanges_missing": [],
    }

    # --- 1. XML files missing in new ---
    xml_orig = {f.name for f in original.glob("*.xml")}
    xml_new = {f.name for f in new.glob("*.xml")}
    diffs["xml_files_missing_in_new"] = sorted(
        list(xml_orig - xml_new)
    )  # files in original not in new

    # --- 2. user_nl_* files ---
    user_nl_orig = {f.name: f for f in original.glob("user_nl_*")}
    user_nl_new = {f.name: f for f in new.glob("user_nl_*")}

    for fname, f_orig in user_nl_orig.items():
        f_new = user_nl_new.get(fname)
        # Extract parameter names
        orig_lines = [extract_param(l) for l in f_orig.read_text().splitlines()]
        orig_params = {l for l in orig_lines if l}
        new_params = set()
        if f_new:
            new_lines = [extract_param(l) for l in f_new.read_text().splitlines()]
            new_params = {l for l in new_lines if l}
        missing_params = sorted(list(orig_params - new_params))
        if missing_params:
            diffs["user_nl_missing_params"][fname] = missing_params

    # --- 3. SourceMods (files only, recursively) ---
    src_orig = {
        f.relative_to(original / "SourceMods")
        for f in (original / "SourceMods").rglob("*")
        if f.is_file()
    }
    src_new = {
        f.relative_to(new / "SourceMods")
        for f in (new / "SourceMods").rglob("*")
        if f.is_file()
    }
    diffs["source_mods_missing_files"] = sorted([str(f) for f in src_orig - src_new])

    # --- 4. Parse replay.sh for missing xmlchange parameters ---
    replay_orig = original / "replay.sh"
    replay_new = new / "replay.sh"

    if replay_orig.exists():
        orig_lines = replay_orig.read_text().splitlines()
        new_lines = replay_new.read_text().splitlines() if replay_new.exists() else []

        orig_params = {
            extract_param(l, replay_sh=True)
            for l in orig_lines
            if extract_param(l, replay_sh=True)
        }
        new_params = {
            extract_param(l, replay_sh=True)
            for l in new_lines
            if extract_param(l, replay_sh=True)
        }

        diffs["xmlchanges_missing"] = sorted(list(orig_params - new_params))

    return diffs


def read_user_nl_mom_lines(caseroot):

    caseroot = Path(caseroot)
    user_nl_mom_path = caseroot / "user_nl_mom"

    with open(user_nl_mom_path, "r") as f:
        user_nl_mom_lines = f.readlines()

    return user_nl_mom_lines


# --- Helper function to extract parameter name from a line ---
def extract_param(line: str, replay_sh=False):
    if replay_sh:
        if not line.startswith("./xmlchange"):
            return None
        line = line[len("./xmlchange"):].strip()
    else:
        if not line or line.startswith("!"):
            return None
    line = line.strip()
    if "=" in line:
        return line.split("=", 1)[0].strip()
    return None  # Ignore lines without '='
