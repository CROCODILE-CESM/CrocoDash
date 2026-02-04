from pathlib import Path
import CrocoDash.forcing_configurations
from CrocoDash.forcing_configurations import *
from CrocoDash.shareable.apply import *
import json
from datetime import datetime
from CrocoDash.case import Case
from CrocoDash.grid import Grid
from CrocoDash.vgrid import VGrid
from CrocoDash.topo import Topo
import xarray as xr

# -----------------------------------------------------------------------------
# Top-level orchestration
# -----------------------------------------------------------------------------


def fork_case_from_bundle(
    bundle_location, cesmroot, machine, project_number, new_caseroot, new_inputdir
):
    """
    Share a CESM case by inspecting an existing case, optionally copying
    non-standard components, resolving forcing configurations, and creating
    a new case with equivalent forcings.
    """

    json_file = Path(bundle_location) / "identify_output.json"
    assert json_file.exists()
    with open(json_file) as f:
        manifest = json.load(f)

    copy_plan = ask_copy_questions(manifest["differences"])

    compset = resolve_compset(manifest)

    case = create_case(
        manifest["init_args"],
        new_caseroot,
        new_inputdir,
        compset=compset,
        machine=machine,
        project_number=project_number,
        cesmroot=cesmroot,
    )

    requested_configs, remove_configs = resolve_forcing_configurations(
        manifest["forcing_config"], compset
    )

    configure_forcing_args = build_general_configure_forcing_args(
        manifest["forcing_config"], remove_configs
    )

    configure_forcing_args = request_any_additional_forcing_args_from_user(
        configure_forcing_args, requested_configs
    )

    case.configure_forcings(**configure_forcing_args)

    apply_copy_plan(
        plan=copy_plan,
        manifest=manifest,
        old_caseroot=manifest["case_info"]["caseroot"],
        new_caseroot=new_caseroot,
        case=case,
    )

    print(
        "\nYou're ready! If you requested any additional forcings, remember to "
        "run them with your extract_forcings driver script."
    )
    return case


# -----------------------------------------------------------------------------
# Interactive decisions
# -----------------------------------------------------------------------------


def ask_copy_questions(differences):
    plan = {}

    if differences.get("xml_files_missing_in_new"):
        plan["xml_files"] = ask_yes_no(
            f"The following non-default XML files are missing in the new case:\n"
            f"{differences['xml_files_missing_in_new']}\nCopy them over?"
        )

    if differences.get("user_nl_missing_params"):
        plan["user_nl"] = ask_yes_no(
            f"Non-default user_nl parameters detected:\n"
            f"{differences['user_nl_missing_params']}\nCopy them over?"
        )

    if differences.get("source_mods_missing_files"):
        plan["source_mods"] = ask_yes_no(
            f"The following source mods files exist in the old case:\n"
            f"{differences['source_mods_missing_files']}\nCopy them over?"
        )

    if differences.get("xmlchanges_missing"):
        plan["xmlchanges"] = ask_yes_no(
            f"Non-default xmlchange parameters detected:\n"
            f"{differences['xmlchanges_missing']}\nApply them?"
        )

    return plan


def resolve_compset(manifest):
    init_args = manifest["init_args"]
    current = init_args["compset"]

    if ask_yes_no(f"Want to change compset? Current compset: {current}", default=False):
        new_compset = ask_string("Enter the new compset")
        print(
            "Warning: Changing compset may have unintended consequences and "
            "may require additional data."
        )
        init_args["compset"] = new_compset
        return new_compset

    return current


# -----------------------------------------------------------------------------
# Forcing configuration resolution
# -----------------------------------------------------------------------------


def resolve_forcing_configurations(forcing_config, compset):
    requested = []

    # Required configurators
    required = ForcingConfigRegistry.find_required_configurators(compset)
    for cfg in required:
        if cfg.name.lower() not in forcing_config:
            print("Missing required configurator:", cfg)
            requested.append(cfg)

    # Valid configurators
    valid = ForcingConfigRegistry.find_valid_configurators(compset)
    already_ran = []

    for cfg in forcing_config:
        if cfg == "basic":
            continue
        config_class = ForcingConfigRegistry.get_configurator_from_name(cfg)
        if config_class not in valid:
            print(f"Forcing config '{cfg}' is no longer valid for this compset")
        else:
            already_ran.append(config_class)
            valid.remove(config_class)

    extra = ask_string(
        f"Enter any other configurations you want "
        f"(comma-separated) from: {[obj.name for obj in valid]}",
        default="[]",
    )
    remove = ask_string(
        f"Enter any configs you don't want "
        f"(comma-separated) from: {[obj.name for obj in already_ran]}",
        default="[]",
    )

    extra = {x.strip() for x in extra.split(",") if x.strip()}
    remove = {x.strip() for x in remove.split(",") if x.strip()}

    for thing in ForcingConfigRegistry.registered_types:
        if thing.name in extra:
            requested.append(thing.name)

    return requested, remove


# -----------------------------------------------------------------------------
# Forcing argument construction
# -----------------------------------------------------------------------------


def build_general_configure_forcing_args(forcing_config, remove_configs):
    basic = forcing_config["basic"]

    start_dt = datetime.strptime(basic["dates"]["start"], basic["dates"]["format"])
    end_dt = datetime.strptime(basic["dates"]["end"], basic["dates"]["format"])

    args = {
        "date_range": [
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        ],
        "boundaries": list(basic["general"]["boundary_number_conversion"].keys()),
        "product_name": basic["forcing"]["product_name"],
        "function_name": basic["forcing"]["function_name"],
    }

    for cfg, cfg_data in forcing_config.items():
        if cfg == "basic" or cfg in remove_configs:
            continue
        if cfg.startswith("case_"):
            continue

        for key, value in cfg_data["inputs"].items():
            if not key.startswith("case_"):
                args[key] = value

    return args


# -----------------------------------------------------------------------------
# Optional interactive augmentation
# -----------------------------------------------------------------------------


def request_any_additional_forcing_args_from_user(args, requested_configs):
    if not requested_configs:
        return args

    print(
        "\nYou requested or are required to add the following configurations:",
        requested_configs,
    )
    print("Provide additional arguments as a JSON dict (or press Enter to skip).")
    print('Example: {"tides_file": "ne30", "tides": true}')

    user_input = input("> ").strip()
    if not user_input:
        return args

    try:
        new_args = json.loads(user_input)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from None

    if not isinstance(new_args, dict):
        raise ValueError("Input must be a JSON object")

    for config in requested_configs:
        for user_arg in ForcingConfigRegistry.get_user_args(
            ForcingConfigRegistry.get_configurator_from_name(config)
        ):
            if user_arg not in new_args:
                raise ValueError("Missing arg: " + user_arg + " for " + config)

    args.update(new_args)
    return args


# -----------------------------------------------------------------------------
# Copy execution
# -----------------------------------------------------------------------------


def apply_copy_plan(plan, manifest, old_caseroot, new_caseroot, case):
    if plan.get("xml_files"):
        copy_xml_files_from_case(
            old_caseroot,
            new_caseroot,
            manifest["differences"]["xml_files_missing_in_new"],
        )

    if plan.get("user_nl"):
        copy_user_nl_params_from_case(
            old_caseroot,
            new_caseroot,
            manifest["differences"]["user_nl_missing_params"],
        )

    if plan.get("source_mods"):
        copy_source_mods_from_case(
            old_caseroot,
            new_caseroot,
            manifest["differences"]["source_mods_missing_files"],
        )

    if plan.get("xmlchanges"):
        apply_xmlchanges_to_case(
            old_caseroot,
            manifest["differences"]["xmlchanges_missing"],
        )

    copy_configurations_to_case(
        manifest["forcing_config"], case, Path(manifest["case_info"]["inputdir_ocnice"])
    )


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
    # Read input
    try:
        answer = input(f"{prompt} (yes/no): ").strip().lower()
    except EOFError:
        # If input is not available (e.g., script redirected), default to no
        print("No input available, assuming 'no'.")
        return False
    # Validate
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
