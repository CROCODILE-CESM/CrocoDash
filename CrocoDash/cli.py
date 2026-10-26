import argparse
import sys
from pathlib import Path


class CrocoDashCliError(Exception):
    """A deliberate, user-facing CLI error.

    main() prints this cleanly and exits(1) instead of showing a traceback.
    Only raise this for conditions a user can act on (e.g. "run this other
    command first") -- never to blanket-catch unexpected bugs, which should
    keep their real traceback.
    """


def _interactive(args):
    """Whether to ask: on a terminal, unless --no-input."""
    return not args.no_input and sys.stdin.isatty()


# The new case's fields that flags set and that create --from asks for, in
# this order: the compset decides which forcings there are.
_CASE_FIELDS = ("caseroot", "inputdir", "cesmroot", "machine", "project", "compset")


def _create(args):
    from CrocoDash.case import Case
    from CrocoDash.prompts import ask_case
    from CrocoDash.recipe import (
        case_to_yaml,
        check_new_case,
        create_case_from_yaml,
        load_config,
    )

    ask = _interactive(args)
    source = None
    if args.source:
        source = Case.from_caseroot(args.source)
        config = case_to_yaml(source)
    else:
        config = load_config(args.config)
    flags = {
        field: getattr(args, field)
        for field in _CASE_FIELDS
        if getattr(args, field) is not None
    }
    config["case"] |= flags

    if "forcings" not in config and not ask:
        raise CrocoDashCliError(
            f"{args.config or args.source} has no forcings to configure the case "
            "with. Run on a terminal (without --no-input) to be asked for them."
        )
    if source is None:
        # A config's forcings are used as they are.
        ask = ask and "forcings" not in config
    else:
        if ask:
            ask_case(config["case"], _CASE_FIELDS)
        elif not {"caseroot", "inputdir"} <= set(flags):
            raise CrocoDashCliError(
                "Without prompts, create --from needs the new case's --caseroot "
                "and --inputdir."
            )
        try:
            check_new_case(config["case"], source)
        except ValueError as e:
            raise CrocoDashCliError(str(e)) from e

    create_case_from_yaml(
        config,
        override=args.override,
        configure_only=args.configure_only,
        ask=ask,
        source=source,
    )


def _dump(args):
    from CrocoDash.recipe import case_to_yaml
    import yaml

    config = case_to_yaml(args.caseroot)
    yaml.dump(config, sys.stdout, default_flow_style=False, sort_keys=False)


def _configure(args):
    from CrocoDash.case import Case
    import yaml

    case = Case.from_caseroot(args.caseroot)
    if not (args.config or args.set) and _interactive(args):
        case.configure_forcings(ask=True)
        print(
            "Forcings configured. Process them with: "
            f"crocodash process --caseroot {case.caseroot} --all"
        )
        return
    # The changes, --config then --set, over the arguments it was configured with.
    changes = {}
    if args.config:
        with open(args.config) as f:
            forcings = (yaml.safe_load(f) or {}).get("forcings")
        if not isinstance(forcings, dict):
            raise CrocoDashCliError(f"{args.config} has no forcings: section.")
        changes |= forcings
    for setting in args.set:
        key, sep, value = setting.partition("=")
        if not sep:
            raise CrocoDashCliError(f"--set takes key=value, not {setting!r}.")
        changes[key.strip()] = yaml.safe_load(value)
    kwargs = case.forcing_args(changes)
    if "date_range" not in kwargs:
        raise CrocoDashCliError(
            f"The forcings of {case.caseroot} were never configured, so give "
            "them with --config or --set (date_range at least)."
        )

    case.configure_forcings(**kwargs)
    print(
        "Forcings configured. Process them with: "
        f"crocodash process --caseroot {case.caseroot} --all"
    )


def _process(args):
    from CrocoDash.case import Case
    from CrocoDash.forcing.driver import run_workflow, resolve_components
    from CrocoDash.forcing.base import (
        CONFIG_FILENAME,
        ForcingConfigRegistry,
        read_config,
    )

    # A config.json (given, or found in the current directory) names its case.
    if args.config:
        caseroot = Path(read_config(args.config)["caseroot"])
    elif args.caseroot:
        caseroot = Path(args.caseroot)
    elif (Path.cwd() / CONFIG_FILENAME).exists():
        # Ran directly from inside the extract_forcings/ directory
        caseroot = Path(read_config(Path.cwd() / CONFIG_FILENAME)["caseroot"])
    else:
        raise CrocoDashCliError(
            "No config.json found in the current directory and no --config or --caseroot provided.\n"
            "Run from inside an extract_forcings/ directory, or pass --caseroot <path> or --config <path>."
        )

    case = Case.from_caseroot(caseroot)
    if not case._configure_forcings_called:
        raise CrocoDashCliError(
            "Forcing configuration not found at "
            f"{case.extract_forcings_path / CONFIG_FILENAME}\n"
            "Run case.configure_forcings() or 'crocodash configure' before calling "
            "'crocodash process'."
        )
    config = case.forcing_config

    args = resolve_components(args, config)

    flag_names = ForcingConfigRegistry.all_process_flags()
    if not any(getattr(args, name) for name in flag_names):
        args.subparser.print_help()
        return

    run_workflow(
        case,
        **{name: getattr(args, name) for name in flag_names},
        preview=args.preview,
        force=args.force,
    )


def _bundle(args):
    from CrocoDash.case import Case  # lazy import for faster startup

    case = Case.from_caseroot(args.caseroot)
    bundle_path = case.bundle(Path(args.output_dir) / f"{case.name}_case_bundle")
    print(f"Bundle written to: {bundle_path}")


def _template(args):
    """Thin wrapper over crocogallery's template renderer.

    The gallery owns the template sources -- notebooks, known_paths.json, and
    the loose pbs/yaml assets -- so it owns the rendering too. This only maps
    CLI arguments onto that call and keeps the error output friendly.
    """
    from crocogallery import list_notebooks, write_template
    from crocogallery.template import DEFAULT_TEMPLATE_NOTEBOOK_ID, uses_notebook

    try:
        if args.list_notebooks:
            for nb_id in sorted(list_notebooks()):
                print(nb_id)
            return

        if not args.output:
            args.subparser.error(
                "--output is required unless --list-notebooks is given."
            )

        if args.notebook != DEFAULT_TEMPLATE_NOTEBOOK_ID and not uses_notebook(
            args.output, args.kind
        ):
            print(
                f"[info] --notebook is ignored for --kind={args.kind!r} output "
                f"{Path(args.output).suffix!r}; those templates are standalone files."
            )

        output = write_template(
            args.output,
            notebook_id=args.notebook,
            machine=args.machine,
            kind=args.kind,
        )
        print(f"Template written to: {output}")
        if not args.machine:
            print("Tip: rerun with --machine glade to pre-fill known dataset paths.")
    except KeyError as e:
        # KeyError.__str__ reprs its (possibly multi-line) argument, which
        # turns embedded newlines into literal "\n" -- print the original
        # message instead so multi-line "available options" listings stay
        # readable, then exit cleanly instead of a raw traceback.
        print(e.args[0] if e.args else str(e), file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="crocodash")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- create ---
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new CrocoDash case from a YAML config file or another case.",
        description="Create a new CrocoDash case from a YAML config file, or from "
        "another case (--from). On a terminal it asks for the forcings once the "
        "case exists: from a config without a forcings: section, offering the "
        "defaults, or with --from, offering the source's, after asking for the "
        "new case's fields.",
    )
    create_from = create_parser.add_mutually_exclusive_group(required=True)
    create_from.add_argument("--config", help="Path to the YAML case config file.")
    create_from.add_argument(
        "--from",
        dest="source",
        metavar="CASE",
        help="Start from an existing case: its caseroot, or a bundle (crocodash "
        "bundle). The new case gets its grids, settings and forcing arguments, "
        "the changes its user made to it, and its forcing files whose settings "
        "still match.",
    )
    for field in _CASE_FIELDS:
        create_parser.add_argument(
            f"--{field}",
            default=None,
            help=f"The new case's {field}, instead of the config's or the source's.",
        )
    create_parser.add_argument(
        "--override",
        action="store_true",
        default=False,
        help="Overwrite existing caseroot and inputdir if they exist.",
    )
    create_parser.add_argument(
        "--configure-only",
        action="store_true",
        default=False,
        dest="configure_only",
        help="Configure forcings but skip process_forcings — for cases that need to "
        "stage custom input data before running the forcing extraction.",
    )
    create_parser.add_argument(
        "--no-input",
        dest="no_input",
        action="store_true",
        help="Never ask, even on a terminal.",
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

    # --- configure ---
    configure_parser = subparsers.add_parser(
        "configure",
        help="Configure the forcings of an existing CrocoDash case again.",
    )
    configure_parser.add_argument(
        "--caseroot", required=True, help="Path to the existing CESM caseroot."
    )
    configure_parser.add_argument(
        "--config",
        default=None,
        help="YAML file whose forcings: section replaces the matching arguments "
        "(e.g. one written by 'crocodash dump').",
    )
    configure_parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set one configure_forcings() argument, after --config. VALUE is "
        "read as YAML, e.g. --set boundaries=[north,east]. Repeatable.",
    )
    configure_parser.add_argument(
        "--no-input",
        dest="no_input",
        action="store_true",
        help="Never ask, even on a terminal: configure with the case's current "
        "arguments, changed by --config and --set.",
    )
    configure_parser.set_defaults(func=_configure)

    # --- process ---
    ef_parser = subparsers.add_parser(
        "process",
        help="Run the forcing extraction workflow for an existing CrocoDash case.",
    )
    ef_parser.add_argument(
        "--config",
        default=None,
        help="Path to a case's config.json; that case is processed. Takes precedence over --caseroot.",
    )
    ef_parser.add_argument(
        "--caseroot",
        default=None,
        help="Path to the CESM caseroot.",
    )
    ef_top = ef_parser.add_argument_group("Top-level actions")
    ef_top.add_argument("--all", action="store_true", help="Run all components")
    ef_components = ef_parser.add_argument_group("Forcing components")
    # One flag per process-component any registered forcing type declares --
    # adding a new forcing type's process_components entry surfaces its flag
    # here automatically, no hand-added add_argument() call needed.
    from CrocoDash.forcing.base import ForcingConfigRegistry

    for flag_name in sorted(ForcingConfigRegistry.all_process_flags()):
        ef_components.add_argument(
            f"--{flag_name}", action="store_true", help=f"Run {flag_name}"
        )
    ef_top.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Skip components by name (e.g. --skip tides runoff)",
    )
    ef_top.add_argument(
        "--preview",
        action="store_true",
        help="Show whether each component is finished or would run, and its "
        "files, present or missing, without running anything",
    )
    ef_top.add_argument(
        "--force",
        action="store_true",
        help="Rerun components even when they are finished",
    )
    ef_parser.set_defaults(func=_process, subparser=ef_parser)

    # --- bundle ---
    bundle_parser = subparsers.add_parser(
        "bundle",
        help="Write a case to a bundle, which crocodash create --from reads, "
        "here or on another machine.",
    )
    bundle_parser.add_argument(
        "--caseroot", required=True, help="Path to the existing CESM caseroot."
    )
    bundle_parser.add_argument(
        "--output-dir",
        required=True,
        dest="output_dir",
        help="Directory to write the bundle into, as <case name>_case_bundle/.",
    )
    bundle_parser.set_defaults(func=_bundle)

    # --- template ---
    template_parser = subparsers.add_parser(
        "template",
        help="Write a starter CrocoDash case file, or a PBS submission script.",
    )
    template_parser.add_argument(
        "--kind",
        choices=["case", "pbs"],
        default="case",
        help=(
            "Kind of template to write. 'case' (default) writes a case definition "
            "-- format picked by --output's suffix (.yaml for a config, .ipynb for "
            "a notebook, .py for a script). 'pbs' writes a PBS batch script for "
            "submitting `crocodash process` to an HPC queue."
        ),
    )
    template_parser.add_argument(
        "--output",
        default=None,
        help="Output path. For --kind case: .yaml, .ipynb, or .py. For --kind pbs: any path, or a .pbs suffix (which also selects the pbs template without needing --kind pbs). Required unless --list-notebooks is given.",
    )
    template_parser.add_argument(
        "--machine",
        default=None,
        help="Pre-fill known dataset paths for this machine (e.g. glade). Omit to leave <KEY> placeholders.",
    )
    from crocogallery.template import DEFAULT_TEMPLATE_NOTEBOOK_ID

    template_parser.add_argument(
        "--notebook",
        default=DEFAULT_TEMPLATE_NOTEBOOK_ID,
        help=(
            "Gallery notebook ID to use as the template source "
            f"(default: {DEFAULT_TEMPLATE_NOTEBOOK_ID}). "
            "Pass --list-notebooks to see all available IDs."
        ),
    )
    template_parser.add_argument(
        "--list-notebooks",
        action="store_true",
        default=False,
        dest="list_notebooks",
        help="Print all available gallery notebook IDs and exit.",
    )
    template_parser.set_defaults(func=_template, subparser=template_parser)

    args = parser.parse_args()
    try:
        args.func(args)
    except CrocoDashCliError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
