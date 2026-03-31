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
        self.forcing_config = self.manifest["forcing_config"]
        self._validate_bundle()

    def _validate_bundle(self):
        missing = []
        ocnice = self.bundle_location / "ocnice"

        for f in self.differences.get("xml_files_missing_in_new", []):
            path = self.bundle_location / "xml_files" / f
            if not path.exists():
                missing.append(str(path))

        for f in self.differences.get("source_mods_missing_files", []):
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
        plan=None,
        compset=None,
        extra_configs=None,
        remove_configs=None,
        extra_forcing_args_path=None,
    ):
        """
        Share a CESM case by inspecting an existing case, optionally copying
        non-standard components, resolving forcing configurations, and creating
        a new case with equivalent forcings.

        All parameters are optional. When provided they bypass the interactive
        prompts; when omitted the user is asked interactively.

        Parameters
        ----------
        plan : dict, optional
            Which non-standard items to copy, e.g.
            ``{"xml_files": True, "user_nl": False, "source_mods": True, "xmlchanges": True}``.
        compset : str, optional
            Override the compset from the bundle. If not provided and differs
            from the bundle compset, the user is asked interactively.
        extra_configs : list, optional
            Additional forcing configuration names to add beyond the bundle.
        remove_configs : list, optional
            Forcing configuration names from the bundle to drop.
        extra_forcing_args_path : str or Path, optional
            Path to a JSON file supplying arguments for any new forcing configs.
        """

        self.plan = plan if plan is not None else self.ask_copy_questions()

        self.compset = self.resolve_compset(compset)

        logger.info(f"Creating new case...")
        self.manifest["init_args"]["inputdir_ocnice"] = str(
            self.bundle_location / "ocnice"
        )  # Get new grid location from bundle
        self.case = create_case(
            self.manifest["init_args"],
            self.caseroot,
            self.inputdir,
            compset=self.compset,
            machine=self.machine,
            project_number=self.project_number,
            cesmroot=self.cesmroot,
        )

        requested_configs, resolved_remove = self.resolve_forcing_configurations(
            extra_configs, remove_configs
        )

        logger.info(f"Building configuration args")

        configure_forcing_args = self.set_up_forcing_inputs(
            self.forcing_config,
            resolved_remove,
            requested_configs,
            extra_forcing_args_path,
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

        if self.differences.get("user_nl_missing_params") and any(
            self.differences["user_nl_missing_params"].values()
        ):
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

    def resolve_compset(self, compset=None):
        self.compset = self.manifest["init_args"]["compset"]
        if compset is not None:
            self.compset = compset
            print(
                "Warning: Changing compset may have unintended consequences and "
                "may require additional data."
            )
        elif ask_yes_no(
            f"Want to change compset? Current compset: {self.compset}", default=False
        ):
            self.compset = ask_string("Enter the new compset")
            print(
                "Warning: Changing compset may have unintended consequences and "
                "may require additional data."
            )

        return self.compset

    def resolve_forcing_configurations(self, extra_configs=None, remove_configs=None):
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

        if extra_configs is not None:
            extra = set(extra_configs)
            remove = set(remove_configs) if remove_configs is not None else set()
        else:
            extra_str = ask_string(
                f"Enter any other configurations you want "
                f"(comma-separated) from: {[obj.name for obj in valid]}",
                default="[]",
            )
            remove_str = ask_string(
                f"Enter any configs you don't want "
                f"(comma-separated) from: {[obj.name for obj in already_ran]}",
                default="[]",
            )
            extra = {x.strip() for x in extra_str.split(",") if x.strip()}
            remove = {x.strip() for x in remove_str.split(",") if x.strip()}

        for thing in ForcingConfigRegistry.registered_types:
            if thing.name in extra:
                requested.append(thing.name)

        return requested, remove

    def set_up_forcing_inputs(
        self,
        forcing_config,
        remove_configs,
        requested_configs,
        extra_forcing_args_path=None,
    ):
        args = generate_configure_forcing_args(forcing_config, remove_configs)
        if not requested_configs:
            return args

        print(
            "\nYou requested or are required to add the following configurations:",
            requested_configs,
        )
        required_args = [
            user_arg
            for config in requested_configs
            for user_arg in ForcingConfigRegistry.get_user_args(
                ForcingConfigRegistry.get_configurator_from_name(config)
            )
            if not user_arg.startswith("case_") and user_arg not in args
        ]
        if extra_forcing_args_path is None:
            print(f"Provide the following arguments in a JSON file: {required_args}")
            extra_forcing_args_path = ask_string(
                "Enter path to JSON file with the required arguments: "
            )
        with open(extra_forcing_args_path) as f:
            new_args = json.load(f)

        for config in requested_configs:
            for user_arg in ForcingConfigRegistry.get_user_args(
                ForcingConfigRegistry.get_configurator_from_name(config)
            ):
                if (
                    not user_arg.startswith("case_")
                    and user_arg not in args
                    and user_arg not in new_args
                ):
                    raise ValueError(f"Missing arg: '{user_arg}' for {config}")

        args.update(new_args)
        return args

    def apply_copy_plan(self):

        if self.plan.get("xml_files"):
            copy_xml_files_from_case(
                self.bundle_location / "xml_files",
                self.case.caseroot,
                self.differences["xml_files_missing_in_new"],
            )

        if self.plan.get("user_nl"):
            copy_user_nl_params_from_case(
                self.bundle_location,
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
        "boundaries": list(
            forcing_config["basic"]["general"]["boundary_number_conversion"].keys()
        ),
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
