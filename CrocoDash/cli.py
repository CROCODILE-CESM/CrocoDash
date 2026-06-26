import argparse
import json
import sys
from pathlib import Path


def _create(args):
    from CrocoDash.recipe import load_config, create_case_from_yaml

    config = load_config(args.config)
    create_case_from_yaml(config, override=args.override)


def _dump(args):
    from CrocoDash.recipe import case_to_yaml
    import yaml

    config = case_to_yaml(args.caseroot)
    yaml.dump(config, sys.stdout, default_flow_style=False, sort_keys=False)


def _process(args):
    from CrocoDash import case_state
    from CrocoDash.extract_forcings.driver import run_workflow, resolve_components

    if args.config:
        config_path = Path(args.config)
    elif args.caseroot:
        caseroot = Path(args.caseroot)
        state = case_state.read(caseroot)
        config_path = Path(state["inputdir"]) / "extract_forcings" / "config.json"
    elif (Path.cwd() / "config.json").exists():
        # Ran directly from inside the extract_forcings/ directory
        config_path = Path.cwd() / "config.json"
    else:
        # Default: treat cwd as caseroot
        state = case_state.read(Path.cwd())
        config_path = Path(state["inputdir"]) / "extract_forcings" / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Forcing configuration not found at {config_path}\n"
            "Run case.configure_forcings() before calling 'crocodash process'."
        )

    with open(config_path) as f:
        config = json.load(f)

    args = resolve_components(args, config)

    run_workflow(
        config_path=config_path,
        ic=args.ic,
        bc=args.bc,
        bgcic=args.bgcic,
        bgcironforcing=args.bgcironforcing,
        tides=args.tides,
        chl_=args.chl,
        runoff=args.runoff,
        bgcrivernutrients=args.bgcrivernutrients,
        preview=config["conditions"]["general"].get("preview", False),
    )


def _bundle(args):
    from CrocoDash.shareable import CaseBundle  # lazy import for faster startup

    case = CaseBundle(args.caseroot)
    case.identify_non_standard_case_info(
        cesmroot=args.cesmroot,
        machine=args.machine,
        project_number=args.project,
    )
    bundle_path = case.bundle(args.output_dir)
    print(f"Bundle written to: {bundle_path}")


def _duplicate_case(args):
    from CrocoDash.shareable import duplicate_case

    new_case = duplicate_case(
        caseroot=args.source,
        new_caseroot=args.case,
        new_inputdir=args.inputdir,
        bundle_dir=args.bundle_dir,
    )
    print(f"Duplicated case created at: {new_case.caseroot}")


def _fork(args):
    from CrocoDash.shareable import ForkBundle

    plan = json.loads(args.plan) if args.plan else None

    forker = ForkBundle(args.bundle)
    forker.fork(
        cesmroot=args.cesmroot,
        machine=args.machine,
        project_number=args.project,
        new_caseroot=args.caseroot,
        new_inputdir=args.inputdir,
        plan=plan,
    )


def main():
    parser = argparse.ArgumentParser(prog="crocodash")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- create ---
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new CrocoDash case from a YAML config file.",
    )
    create_parser.add_argument(
        "--config", required=True, help="Path to the YAML case config file."
    )
    create_parser.add_argument(
        "--override",
        action="store_true",
        default=False,
        help="Overwrite existing caseroot and inputdir if they exist.",
    )
    create_parser.set_defaults(func=_create)

    # --- dump ---
    dump_parser = subparsers.add_parser(
        "dump",
        help="Print a YAML representation of an existing CrocoDash case to stdout.",
    )
    dump_parser.add_argument(
        "--caseroot", required=True, help="Path to the existing CESM caseroot."
    )
    dump_parser.set_defaults(func=_dump)

    # --- process ---
    ef_parser = subparsers.add_parser(
        "process",
        help="Run the forcing extraction workflow for an existing CrocoDash case.",
    )
    ef_parser.add_argument(
        "--config",
        default=None,
        help="Direct path to config.json. Takes precedence over --caseroot.",
    )
    ef_parser.add_argument(
        "--caseroot",
        default=None,
        help="Path to the CESM caseroot. Defaults to the current working directory.",
    )
    ef_top = ef_parser.add_argument_group("Top-level actions")
    ef_top.add_argument("--all", action="store_true", help="Run all components")
    ef_components = ef_parser.add_argument_group("Forcing components")
    ef_components.add_argument(
        "--ic", action="store_true", help="Run initial conditions"
    )
    ef_components.add_argument(
        "--bc", action="store_true", help="Run boundary conditions"
    )
    ef_components.add_argument(
        "--bgcic", action="store_true", help="Run BGC initial conditions"
    )
    ef_components.add_argument(
        "--bgcironforcing", action="store_true", help="Run BGC iron forcing"
    )
    ef_components.add_argument(
        "--bgcrivernutrients", action="store_true", help="Run BGC river nutrients"
    )
    ef_components.add_argument(
        "--runoff", action="store_true", help="Run runoff mapping"
    )
    ef_components.add_argument("--tides", action="store_true", help="Run tidal forcing")
    ef_components.add_argument(
        "--chl", action="store_true", help="Run chlorophyll processing"
    )
    ef_top.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Skip components by name (e.g. --skip tides runoff)",
    )
    ef_parser.set_defaults(func=_process)

    # --- bundle ---
    bundle_parser = subparsers.add_parser(
        "bundle",
        help="Read an existing CrocoDash case and produce a shareable bundle.",
    )
    bundle_parser.add_argument(
        "--caseroot", required=True, help="Path to the existing CESM caseroot."
    )
    bundle_parser.add_argument(
        "--output-dir",
        required=True,
        dest="output_dir",
        help="Directory to write the bundle into.",
    )
    bundle_parser.add_argument(
        "--cesmroot", required=True, help="Path to the CESM source root."
    )
    bundle_parser.add_argument(
        "--machine", required=True, help="Machine name (e.g. derecho)."
    )
    bundle_parser.add_argument(
        "--project", required=True, help="Project/account number."
    )
    bundle_parser.set_defaults(func=_bundle)

    # --- duplicate ---
    duplicate_parser = subparsers.add_parser(
        "duplicate", help="Duplicate an existing CrocoDash case to a new location."
    )
    duplicate_parser.add_argument(
        "--source",
        required=True,
        help="Path to the existing CESM caseroot to duplicate from.",
    )
    duplicate_parser.add_argument(
        "--case",
        required=True,
        help="Path for the new duplicated caseroot.",
    )
    duplicate_parser.add_argument(
        "--inputdir",
        required=True,
        help="Path for the new input directory.",
    )
    duplicate_parser.add_argument(
        "--bundle-dir",
        default=None,
        dest="bundle_dir",
        help="Where to keep the bundle (default: inside new caseroot).",
    )
    duplicate_parser.set_defaults(func=_duplicate_case)

    # --- fork ---
    fork_parser = subparsers.add_parser(
        "fork", help="Create a new case from a CrocoDash bundle."
    )
    fork_parser.add_argument(
        "--bundle", required=True, help="Path to the bundle directory."
    )
    fork_parser.add_argument(
        "--caseroot", required=True, help="Path for the new caseroot."
    )
    fork_parser.add_argument(
        "--inputdir", required=True, help="Path for the new input directory."
    )
    fork_parser.add_argument(
        "--cesmroot", required=True, help="Path to the CESM source root."
    )
    fork_parser.add_argument(
        "--machine", required=True, help="Machine name (e.g. derecho)."
    )
    fork_parser.add_argument("--project", required=True, help="Project/account number.")
    fork_parser.add_argument(
        "--plan",
        default=None,
        help='JSON object controlling what non-standard CESM state to copy, e.g. \'{"xml_files": true, "user_nl": true, "source_mods": false, "xmlchanges": true}\'.',
    )
    fork_parser.set_defaults(func=_fork)

    args = parser.parse_args()
    args.func(args)
