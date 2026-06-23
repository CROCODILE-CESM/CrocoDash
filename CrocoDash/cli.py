import argparse
import json
import sys


def _create(args):
    from CrocoDash.recipe import load_config, create_case_from_yaml

    config = load_config(args.config)
    create_case_from_yaml(config, override=args.override)


def _dump(args):
    from CrocoDash.recipe import case_to_yaml
    import yaml

    config = case_to_yaml(args.caseroot)
    yaml.dump(config, sys.stdout, default_flow_style=False, sort_keys=False)


def _bundle(args):
    from CrocoDash.shareable.bundle import (
        BundleCrocoDashCase,
    )  # Makes loading faster when not used

    case = BundleCrocoDashCase(args.caseroot)
    case.identify_non_standard_CrocoDash_case_information(
        cesmroot=args.cesmroot,
        machine=args.machine,
        project_number=args.project,
    )
    bundle_path = case.bundle(args.output_dir)
    print(f"Bundle written to: {bundle_path}")


def _duplicate_case(args):
    from CrocoDash.shareable.bundle import duplicate_case

    new_case = duplicate_case(
        caseroot=args.source,
        new_caseroot=args.case,
        new_inputdir=args.inputdir,
        bundle_dir=args.bundle_dir,
    )
    print(f"Duplicated case created at: {new_case.caseroot}")


def _template(args):
    from pathlib import Path
    from crocogallery import get_notebook_path, inject_into_text, load_paths

    output = Path(args.output)
    notebook_id = args.notebook

    if output.suffix in (".yaml", ".yml"):
        # YAML starter lives alongside the default tutorial notebook
        yaml_path = get_notebook_path(notebook_id).parent / "starter_case.yaml"
        template_text = yaml_path.read_text()
        if args.machine:
            template_text = inject_into_text(template_text, load_paths(args.machine))
        output.write_text(template_text)
    else:
        import nbformat

        paths = load_paths(args.machine) if args.machine else {}
        nb = nbformat.read(get_notebook_path(notebook_id), as_version=4)

        if output.suffix == ".ipynb":
            for cell in nb.cells:
                if cell.cell_type == "code":
                    cell.source = inject_into_text(cell.source, paths)
            nbformat.write(nb, output)
        else:
            code_cells = [cell.source for cell in nb.cells if cell.cell_type == "code"]
            text = "# %%\n" + "\n\n# %%\n".join(code_cells)
            output.write_text(inject_into_text(text, paths))

    print(f"Template written to: {output}")
    if not args.machine:
        print("Tip: rerun with --machine derecho to pre-fill known dataset paths.")


def _fork(args):
    from CrocoDash.shareable.fork import ForkCrocoDashBundle

    plan = json.loads(args.plan) if args.plan else None

    forker = ForkCrocoDashBundle(args.bundle)
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
        help="Write a starter CrocoDash case script or notebook.",
    )
    template_parser.add_argument(
        "--output",
        required=True,
        help="Output path. Use .yaml for a config, .ipynb for a notebook, .py for a script.",
    )
    template_parser.add_argument(
        "--machine",
        default=None,
        help="Pre-fill known dataset paths for this machine (e.g. derecho). Omit to leave <KEY> placeholders.",
    )
    template_parser.add_argument(
        "--notebook",
        default="crocodash.tutorials.crocodash_tutorial",
        help=(
            "Gallery notebook ID to use as the template source "
            "(default: crocodash.tutorials.crocodash_tutorial). "
            "Run `python -c 'from crocogallery import list_notebooks; print(*list_notebooks(), sep=\"\\n\")'` "
            "to see all available IDs."
        ),
    )
    template_parser.set_defaults(func=_template)

    args = parser.parse_args()
    args.func(args)
