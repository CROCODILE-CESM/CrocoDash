from pathlib import Path
from CrocoDash.forcing_configurations.base import *
from CrocoDash.shareable.apply import *
import json
from datetime import datetime
from CrocoDash.case import Case
from CrocoDash.grid import Grid
from CrocoDash.vgrid import VGrid
from CrocoDash.topo import Topo
import xarray as xr
from CrocoDash.logging import setup_logger

logger = setup_logger(__name__)


class ForkCrocoDashBundle:
    """
    Share a CESM case by inspecting an existing CrocoDash bundle, optionally copying
    non-standard components, resolving forcing configurations, and creating
    a new case with equivalent forcings.
    """

    def __init__(
        self,
        bundle_location,
        cesmroot,
        machine,
        project_number,
        new_caseroot,
        new_inputdir,
    ):
        self.bundle_location = Path(bundle_location)
        json_file = Path(bundle_location) / "manifest.json"
        assert json_file.exists()
        with open(json_file) as f:
            self.manifest = json.load(f)
        json_file = Path(bundle_location) / "non_standard_case_info.json"
        assert json_file.exists()
        with open(json_file) as f:
            self.differences = json.load(f)
        self.cesmroot = cesmroot
        self.machine = machine
        self.project_number = project_number
        self.caseroot = new_caseroot
        self.inputdir = new_inputdir

    def fork(self):
        """
        Share a CESM case by inspecting an existing case, optionally copying
        non-standard components, resolving forcing configurations, and creating
        a new case with equivalent forcings.
        """

        self.plan = self.ask_copy_questions()

        self.compset = self.resolve_compset()

        logger.info(f"Creating new case...")
        self.case = create_case(
            self.manifest["init_args"],
            self.caseroot,
            self.inputdir,
            compset=self.compset,
            machine=self.machine,
            project_number=self.project_number,
            cesmroot=self.cesmroot,
        )

        requested_configs, remove_configs = self.resolve_forcing_configurations()

        logger.info(f"Building configuration args")

        configure_forcing_args = self.request_any_additional_forcing_args_from_user(
            self.forcing_config, remove_configs, requested_configs
        )

        self.case.configure_forcings(**configure_forcing_args)

        logger.info(f"Copying items to new case based on user input")
        self.apply_copy_plan()

        self.case.validate_case()

        print(
            "\nYou're ready! If you requested any additional forcings, remember to "
            "run them with your extract_forcings driver script."
        )
        return self.case

    def ask_copy_questions(self):
        self.plan = {}

        if self.differences.get("xml_files_missing_in_new"):
            self.plan["xml_files"] = ask_yes_no(
                f"The following non-default XML files are missing in the new case:\n"
                f"{self.differences['xml_files_missing_in_new']}\nCopy them over?"
            )

        if self.differences.get("user_nl_missing_params"):
            self.plan["user_nl"] = ask_yes_no(
                f"Non-default user_nl parameters detected:\n"
                f"{self.differences['user_nl_missing_params']}\nCopy them over?"
            )

        if self.differences.get("source_mods_missing_files"):
            self.plan["source_mods"] = ask_yes_no(
                f"The following source mods files exist in the old case:\n"
                f"{self.differences['source_mods_missing_files']}\nCopy them over?"
            )

        if self.differences.get("xmlchanges_missing"):
            self.plan["xmlchanges"] = ask_yes_no(
                f"Non-default xmlchange parameters detected:\n"
                f"{self.differences['xmlchanges_missing']}\nApply them?"
            )

        return self.plan

    def resolve_compset(self):
        self.compset = self.manifest["init_args"]["compset"]
        if ask_yes_no(
            f"Want to change compset? Current compset: {self.compset}", default=False
        ):
            self.compset = ask_string("Enter the new compset")
            print(
                "Warning: Changing compset may have unintended consequences and "
                "may require additional data."
            )

        return self.compset

    def resolve_forcing_configurations(self):
        requested = []

        # Required configurators
        required = ForcingConfigRegistry.find_required_configurators(self.compset)
        for cfg in required:
            if cfg.name.lower() not in self.forcing_config:
                print("Missing required configurator:", cfg)
                requested.append(cfg)

        # Valid configurators
        valid = ForcingConfigRegistry.find_valid_configurators(self.compset)
        already_ran = []

        for cfg in self.forcing_config:
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

    def request_any_additional_forcing_args_from_user(
        self, forcing_config, remove_configs, requested_configs
    ):
        args = generate_configure_forcing_args(forcing_config, remove_configs)
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

    def apply_copy_plan(self):

        if self.plan.get("xml_files"):
            copy_xml_files_from_case(
                self.bundle_location,
                self.case.caseroot,
                self.differences["xml_files_missing_in_new"],
            )

        if self.plan.get("user_nl"):
            copy_user_nl_params_from_case(
                self.bundle_location,
                self.case.caseroot,
                self.differences["user_nl_missing_params"],
            )

        if self.plan.get("source_mods"):
            copy_source_mods_from_case(
                self.bundle_location,
                self.case.caseroot,
                self.differences["source_mods_missing_files"],
            )

        if self.plan.get("xmlchanges"):
            apply_xmlchanges_to_case(
                self.bundle_location,
                self.differences["xmlchanges_missing"],
            )

        copy_configurations_to_case(
            self.manifest["forcing_config"], self.case, self.bundle_location / "ocnice"
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


def generate_configure_forcing_args(forcing_config, remove_configs=[""]):
    logger.info("Setup configuration arguments...")

    start_str = forcing_config["basic"]["dates"]["start"]
    end_str = forcing_config["basic"]["dates"]["end"]
    date_format = forcing_config["basic"]["dates"]["format"]
    start_dt = datetime.strptime(start_str, date_format)
    end_dt = datetime.strptime(end_str, date_format)

    date_range = [
        start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        end_dt.strftime("%Y-%m-%d %H:%M:%S"),
    ]

    configure_forcing_args = {
        "date_range": date_range,
        "boundaries": forcing_config["basic"]["general"][
            "boundary_number_conversion"
        ].keys(),
        "product_name": forcing_config["basic"]["forcing"]["product_name"],
        "function_name": forcing_config["basic"]["forcing"]["function_name"],
    }
    for key in forcing_config:
        if key == "basic" or key in remove_configs:
            continue
        user_args = ForcingConfigRegistry.get_user_args(
            ForcingConfigRegistry.get_configurator_from_name(key)
        )
        for arg in user_args:
            if not arg.startswith("case_"):
                configure_forcing_args[arg] = forcing_config[key]["inputs"][arg]
    return configure_forcing_args
