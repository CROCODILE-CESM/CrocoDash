import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_TEMPLATE_NOTEBOOK_ID = "crocodash.tutorials.crocodash_tutorial"

# known_paths.json keys that hold placeholder tokens rather than real
# dataset paths -- injecting them would silently overwrite an obvious
# <KEY> placeholder with something equally uninformative (e.g. "Checkout").
_NON_PATH_KEYS = {"CESM", "inputdir", "casedir"}


class CrocoDashCliError(Exception):
    """A deliberate, user-facing CLI error.

    main() prints this cleanly and exits(1) instead of showing a traceback.
    Only raise this for conditions a user can act on (e.g. "run this other
    command first") -- never to blanket-catch unexpected bugs, which should
    keep their real traceback.
    """


def _comment_out_magics(source):
    """Comment out IPython magic/shell lines (jupytext convention) so
    extracted code cells are valid, runnable Python."""
    return "\n".join(
        "# " + line if re.match(r"^\s*[%!]", line) else line
        for line in source.split("\n")
    )


def _create(args):
    from CrocoDash.recipe import load_config, create_case_from_yaml

    config = load_config(args.config)
    create_case_from_yaml(
        config, override=args.override, configure_only=args.configure_only
    )


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
        if not config_path.exists():
            raise CrocoDashCliError(
                f"Forcing configuration not found at {config_path}\n"
                "Run case.configure_forcings() before calling 'crocodash process'."
            )
    elif (Path.cwd() / "config.json").exists():
        # Ran directly from inside the extract_forcings/ directory
        config_path = Path.cwd() / "config.json"
    else:
        raise CrocoDashCliError(
            "No config.json found in the current directory and no --config or --caseroot provided.\n"
            "Run from inside an extract_forcings/ directory, or pass --caseroot <path> or --config <path>."
        )

    with open(config_path) as f:
        config = json.load(f)

    args = resolve_components(args, config)

    if not any(
        [
            args.ic,
            args.bc,
            args.bgcic,
            args.bgcironforcing,
            args.tides,
            args.chl,
            args.runoff,
            args.bgcrivernutrients,
        ]
    ):
        args.subparser.print_help()
        return

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
        preview=config["conditions"]["outputs"].get("preview", False),
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


def _template(args):
    from pathlib import Path
    from crocogallery import (
        get_notebook_path,
        list_notebooks,
        inject_into_text,
        load_paths,
    )

    def _paths():
        if not args.machine:
            return {}
        return {
            k: v for k, v in load_paths(args.machine).items() if k not in _NON_PATH_KEYS
        }

    try:
        if args.list_notebooks:
            for nb_id in sorted(list_notebooks()):
                print(nb_id)
            return

        if not args.output:
            args.subparser.error(
                "--output is required unless --list-notebooks is given."
            )

        output = Path(args.output)
        notebook_id = args.notebook
        output.parent.mkdir(parents=True, exist_ok=True)
        is_pbs = args.kind == "pbs" or output.suffix == ".pbs"

        if is_pbs or output.suffix in (".yaml", ".yml"):
            # The PBS script and YAML starter only live alongside the default
            # tutorial notebook, not every gallery notebook -- --notebook only
            # matters for the .ipynb/.py branch below.
            if notebook_id != DEFAULT_TEMPLATE_NOTEBOOK_ID:
                print(
                    f"[info] --notebook is ignored for --kind={args.kind!r} output "
                    f"{output.suffix!r}; using the default tutorial's template."
                )
            source_dir = get_notebook_path(DEFAULT_TEMPLATE_NOTEBOOK_ID).parent
            if is_pbs:
                template_text = (source_dir / "submit_forcings.pbs").read_text()
                template_text = inject_into_text(template_text, _paths())
                output.write_text(template_text)
                output.chmod(output.stat().st_mode | 0o111)
            else:
                template_text = (source_dir / "starter_case.yaml").read_text()
                template_text = inject_into_text(template_text, _paths())
                output.write_text(template_text)
        else:
            import nbformat

            paths = _paths()
            nb = nbformat.read(get_notebook_path(notebook_id), as_version=4)

            if output.suffix == ".ipynb":
                for cell in nb.cells:
                    if cell.cell_type == "code":
                        cell.source = inject_into_text(cell.source, paths)
                nbformat.write(nb, output)
            else:
                blocks = []
                for cell in nb.cells:
                    if cell.cell_type == "code":
                        code = _comment_out_magics(inject_into_text(cell.source, paths))
                        blocks.append("# %%\n" + code)
                    elif cell.cell_type == "markdown":
                        commented = "\n".join(
                            f"# {line}" if line else "#"
                            for line in cell.source.split("\n")
                        )
                        blocks.append("# %% [markdown]\n" + commented)
                output.write_text("\n\n".join(blocks))

        print(f"Template written to: {output}")
        if not args.machine:
            print("Tip: rerun with --machine derecho to pre-fill known dataset paths.")
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
        help="Path to the CESM caseroot.",
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
        help="Pre-fill known dataset paths for this machine (e.g. derecho). Omit to leave <KEY> placeholders.",
    )
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
