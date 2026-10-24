import argparse
import json
import sys
from pathlib import Path


class CrocoDashCliError(Exception):
    """A deliberate, user-facing CLI error.

    main() prints this cleanly and exits(1) instead of showing a traceback.
    Only raise this for conditions a user can act on (e.g. "run this other
    command first") -- never to blanket-catch unexpected bugs, which should
    keep their real traceback.
    """


def _create(args):
    from CrocoDash.recipe import load_config, create_case_from_yaml

    config = load_config(args.config)
    create_case_from_yaml(
        config, override=args.override, configure_only=args.configure_only
    )


def _dump(args):
    from CrocoDash.recipe import case_to_yaml, annotated_yaml
    import yaml

    config = case_to_yaml(args.caseroot)
    if args.annotate:
        from CrocoDash.case import Case

        case = Case.from_caseroot(args.caseroot)
        sys.stdout.write(annotated_yaml(config, _param_specs(case, case.compset_lname)))
    else:
        yaml.dump(config, sys.stdout, default_flow_style=False, sort_keys=False)


def _param_specs(case, compset):
    """The ParamSpecs of compset's forcing arguments, with case's configured
    values as their defaults."""
    from CrocoDash.forcing.base import ForcingConfigRegistry

    config = case.forcing_config if case._configure_forcings_called else None
    return ForcingConfigRegistry.param_specs(compset, config=config)


def _configure(args):
    from CrocoDash.case import Case
    import yaml

    case = Case.from_caseroot(args.caseroot)
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


# What fork asks about the new case, in this order: the compset decides which
# forcing arguments there are. All but the compset depend on the machine.
_CASE_FIELDS = ("caseroot", "inputdir", "cesmroot", "machine", "project", "compset")

_FORK_YAML_HEADER = """\
# A fork of a CrocoDash case. Edit it, then run: crocodash fork --config <this file>
# case: the new case, at the source's values. Its caseroot and inputdir must not
#   exist yet; cesmroot, machine and project are this machine's.
# forcings: the source's configure_forcings() arguments; change any of them.
# plan: carry over the source's own changes of each kind (true/false), and copy
#   its forcing files: matching (if their settings still match), all, or none.
"""


def ask_string(prompt, default=""):
    """The answer typed at prompt, or default for an empty one. EOFError (the
    end of input) is left to the caller, which keeps its remaining defaults."""
    return input(prompt).strip() or default


def ask_yes_no(prompt, default=True):
    answer = ask_string(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").lower()
    if answer in ("y", "yes"):
        return True
    if answer in ("n", "no"):
        return False
    return default


def ask_value(label, default, why_not_default=None, as_yaml=True):
    """The value typed for label, or default for an empty answer, unless
    why_not_default says why it can't be used here: then Enter asks again.
    With as_yaml, the answer is read as YAML, so lists and numbers work."""
    shown = default if isinstance(default, str) else json.dumps(default, default=str)
    note = f" ({why_not_default})" if why_not_default else ""
    while True:
        answer = ask_string(f"{label} [{shown}]{note}: ")
        if answer:
            return _read_yaml(answer) if as_yaml else answer
        if not why_not_default:
            return default


def _read_yaml(text):
    """text read as YAML, with dates as strings: an unquoted 2020-01-01 reads
    as a date, but configure_forcings() takes date strings."""
    import yaml

    return json.loads(json.dumps(yaml.safe_load(text), default=str))


def _ask_case(case):
    """Ask for each of the new case's fields, offering case's values. A
    caseroot or inputdir that exists, or a cesmroot that doesn't, has to be
    replaced."""
    for field in _CASE_FIELDS:
        value = case[field]
        why_not = None
        if field in ("caseroot", "inputdir") and value and Path(value).exists():
            why_not = "exists already"
        elif field == "cesmroot" and value and not Path(value).exists():
            why_not = "not found on this machine"
        label = "compset (long name)" if field == "compset" else field
        case[field] = ask_value(label, value, why_not, as_yaml=False)


def _ask_forcings(specs, values):
    """Ask for each forcing argument specs describe, offering values' (the
    source's). A path that isn't on this machine, or a required argument
    without a value, has to be given."""
    from CrocoDash.recipe import spec_note
    import textwrap

    print("\nForcings (Enter keeps the source's value; answers are read as YAML):")
    for spec in specs:
        value = values.get(spec.name)
        why_not = None
        if spec.is_path and isinstance(value, str) and not Path(value).exists():
            why_not = "not found on this machine"
        elif spec.required and value is None:
            why_not = "required"
        print("\n".join(f"# {line}" for line in textwrap.wrap(spec_note(spec), 76)))
        values[spec.name] = ask_value(spec.name, value, why_not)


def _ask_plan(source, machine, plan):
    """Ask whether to carry over each kind of the source's own changes that it
    has, and which of its forcing files to copy."""
    from CrocoDash.case import _CHANGE_KINDS, _FORCING_FILES_PLANS

    changes = source.user_changes(target_machine=machine)
    print()
    for kind in _CHANGE_KINDS:
        if changes[kind]:
            plan[kind] = ask_yes_no(
                f"Carry over the source's {kind} ({', '.join(changes[kind])})?",
                plan[kind],
            )
    forcing_files = None
    while forcing_files not in _FORCING_FILES_PLANS:
        forcing_files = ask_value(
            f"Copy the source's forcing files: {', '.join(_FORCING_FILES_PLANS)}",
            plan["forcing_files"],
            as_yaml=False,
        )
    plan["forcing_files"] = forcing_files


def _fork(args):
    from CrocoDash.case import Case, _CHANGE_KINDS
    from CrocoDash.recipe import annotated_yaml, flatten_forcings

    config = {}
    if args.config:
        with open(args.config) as f:
            config = _read_yaml(f.read()) or {}
    source_path = args.source or config.get("source")
    if not source_path:
        raise CrocoDashCliError(
            "Give the case to fork with --source, or a --config with a source:."
        )
    flags = {
        field: getattr(args, field)
        for field in _CASE_FIELDS
        if getattr(args, field, None) is not None
    }
    interactive = (
        not (args.config or args.no_input or args.write_yaml) and sys.stdin.isatty()
    )
    if not (interactive or args.config or args.write_yaml) and not (
        "caseroot" in flags and "inputdir" in flags
    ):
        raise CrocoDashCliError(
            "Without prompts, fork needs the new case's --caseroot and --inputdir."
        )

    source = Case.from_caseroot(source_path)
    bundled = source.bundled_from or {}
    # The source's values, then the YAML's, then the flags'.
    case = (
        {
            "caseroot": bundled.get("caseroot", str(source.caseroot)),
            "inputdir": bundled.get("inputdir", str(source.inputdir)),
            "cesmroot": str(source.cesmroot),
            "machine": source.machine,
            "project": source.project,
            "compset": source.compset_lname,
        }
        | (config.get("case") or {})
        | flags
    )
    plan = (
        dict.fromkeys(_CHANGE_KINDS, True)
        | {"forcing_files": "matching"}
        | (config.get("plan") or {})
        | (json.loads(args.plan) if args.plan else {})
    )

    end_of_input = "\nEnd of input: the rest keep their defaults."
    if interactive:
        try:
            _ask_case(case)
        except EOFError:
            print(end_of_input)
            interactive = False
    # The compset's forcing arguments, at the source's values unless changed.
    specs = _param_specs(source, case["compset"])
    source_values = {spec.name: spec.default for spec in specs} | flatten_forcings(
        source.forcing_args()
    )
    values = source_values | flatten_forcings(config.get("forcings") or {})
    if interactive:
        try:
            _ask_forcings(specs, values)
            _ask_plan(source, case["machine"], plan)
        except EOFError:
            print(end_of_input)

    if args.write_yaml:
        fork = {
            "source": str(Path(source_path).absolute()),
            "case": case,
            "forcings": source.forcing_args(),
            "plan": plan,
        }
        with open(args.write_yaml, "w") as f:
            f.write(_FORK_YAML_HEADER + annotated_yaml(fork, specs))
        print(
            f"Wrote {args.write_yaml}. Edit it, then run: "
            f"crocodash fork --config {args.write_yaml}"
        )
        return

    missing = [
        spec.name for spec in specs if spec.required and values.get(spec.name) is None
    ]
    if missing:
        raise CrocoDashCliError(
            f"The new case's forcings need {', '.join(missing)}: give them at "
            "the prompts, or in the forcings: of a --config."
        )
    # Only what differs from the source's. function_overrides is one argument,
    # so a change to any of its keys passes them all.
    prefix = "function_overrides."
    changed = [
        name for name, value in values.items() if value != source_values.get(name)
    ]
    changes = {name: values[name] for name in changed if not name.startswith(prefix)}
    if len(changes) < len(changed):
        changes["function_overrides"] = {
            name.removeprefix(prefix): value
            for name, value in values.items()
            if name.startswith(prefix)
        }

    Case.fork(
        source,
        case["caseroot"],
        case["inputdir"],
        cesmroot=case["cesmroot"],
        machine=case["machine"],
        project=case["project"],
        compset=case["compset"],
        changes=changes,
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
    create_parser.add_argument(
        "--configure-only",
        action="store_true",
        default=False,
        dest="configure_only",
        help="Configure forcings but skip process_forcings — for cases that need to "
        "stage custom input data before running the forcing extraction.",
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
    dump_parser.add_argument(
        "--annotate",
        action="store_true",
        help="Comment each forcing argument (required or optional, what it is, "
        "its choices), and list the ones the case doesn't set, commented out.",
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
        help="Read an existing CrocoDash case and produce a shareable bundle.",
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
    # The bundle records the case's own; these are accepted for older scripts.
    for flag in ("--cesmroot", "--machine", "--project"):
        bundle_parser.add_argument(flag, default=None, help="Ignored.")
    bundle_parser.set_defaults(func=_bundle)

    # --- fork ---
    fork_parser = subparsers.add_parser(
        "fork",
        help="Create a new case from a case or a bundle.",
        description="Create a new case from a case or a bundle. On a terminal, "
        "without --config or --no-input, it asks for each case and forcing value, "
        "offering the source's: Enter keeps it, and the end of input (Ctrl-D) "
        "keeps the rest.",
    )
    fork_parser.add_argument(
        "--source",
        "--bundle",
        dest="source",
        default=None,
        help="The case to fork: its caseroot, or a bundle (crocodash bundle). "
        "Not needed with a --config, which names it.",
    )
    fork_parser.add_argument("--caseroot", help="Path for the new caseroot.")
    fork_parser.add_argument("--inputdir", help="Path for the new input directory.")
    fork_parser.add_argument(
        "--cesmroot", help="Path to the CESM source root (default: the source's)."
    )
    fork_parser.add_argument(
        "--machine", help="Machine name, e.g. derecho (default: the source's)."
    )
    fork_parser.add_argument(
        "--project", help="Project/account number (default: the source's)."
    )
    fork_parser.add_argument(
        "--plan",
        default=None,
        help='JSON object of what to carry over: the user\'s changes ("xml_files", "user_nl", "source_mods", "xmlchanges"; all by default) and "forcing_files": "matching" (default), "all" or "none", e.g. \'{"xmlchanges": false, "forcing_files": "none"}\'.',
    )
    fork_mode = fork_parser.add_mutually_exclusive_group()
    fork_mode.add_argument(
        "--write-yaml",
        dest="write_yaml",
        metavar="FILE",
        help="Write the fork, at the source's values, to an annotated YAML file "
        "to edit, and stop.",
    )
    fork_mode.add_argument(
        "--config",
        metavar="FILE",
        help="Fork as a YAML file from --write-yaml says, without prompts.",
    )
    fork_mode.add_argument(
        "--no-input",
        dest="no_input",
        action="store_true",
        help="Take the source's value of everything the flags don't give, "
        "without prompts.",
    )
    fork_parser.set_defaults(func=_fork)

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
