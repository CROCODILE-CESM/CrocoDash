import argparse
import json


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
    import sys
    import nbformat
    from pathlib import Path

    demos_tools = Path(__file__).parent.parent / "demos" / "tools"
    sys.path.insert(0, str(demos_tools))
    from inject_paths import load_paths, inject_into_text

    paths = (
        load_paths(demos_tools / "known_paths.json", args.machine)
        if args.machine
        else {}
    )
    output = Path(args.output)

    nb_path = (
        demos_tools.parent
        / "gallery"
        / "notebooks"
        / "CrocoDash"
        / "tutorials"
        / "crocodash_tutorial.ipynb"
    )
    nb = nbformat.read(nb_path, as_version=4)

    if output.suffix == ".ipynb":
        for cell in nb.cells:
            if cell.cell_type == "code":
                cell.source = inject_into_text(cell.source, paths)
        nbformat.write(nb, output)
    else:
        code_cells = [cell.source for cell in nb.cells if cell.cell_type == "code"]
        text = "\n\n# %%\n".join(code_cells)
        output.write_text(inject_into_text(text, paths))

    print(f"Template written to: {output}")
    if not args.machine:
        print("Tip: rerun with --machine derecho to pre-fill known dataset paths.")


def _fork(args):

    from CrocoDash.shareable.fork import ForkCrocoDashBundle

    plan = json.loads(args.plan) if args.plan else None
    extra_configs = (
        [x.strip() for x in args.extra_configs.split(",") if x.strip()]
        if args.extra_configs
        else None
    )
    remove_configs = (
        [x.strip() for x in args.remove_configs.split(",") if x.strip()]
        if args.remove_configs
        else None
    )

    forker = ForkCrocoDashBundle(args.bundle)
    forker.fork(
        cesmroot=args.cesmroot,
        machine=args.machine,
        project_number=args.project,
        new_caseroot=args.caseroot,
        new_inputdir=args.inputdir,
        plan=plan,
        compset=args.compset,
        extra_configs=extra_configs,
        remove_configs=remove_configs,
        extra_forcing_args_path=args.extra_forcing_args,
    )


def main():
    parser = argparse.ArgumentParser(prog="crocodash")
    subparsers = parser.add_subparsers(dest="command", required=True)

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
    # optional bypass flags
    fork_parser.add_argument(
        "--compset", default=None, help="Override the compset from the bundle."
    )
    fork_parser.add_argument(
        "--plan",
        default=None,
        help='JSON object controlling what to copy, e.g. \'{"xml_files": true, "user_nl": true, "source_mods": false, "xmlchanges": true}\'.',
    )
    fork_parser.add_argument(
        "--extra-configs",
        default=None,
        dest="extra_configs",
        help="Comma-separated forcing configs to add.",
    )
    fork_parser.add_argument(
        "--remove-configs",
        default=None,
        dest="remove_configs",
        help="Comma-separated forcing configs to drop.",
    )
    fork_parser.add_argument(
        "--extra-forcing-args",
        default=None,
        dest="extra_forcing_args",
        help="Path to JSON file with extra forcing arguments.",
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
        help="Output path. Use .ipynb for a notebook or .py for a Python script.",
    )
    template_parser.add_argument(
        "--machine",
        default=None,
        help="Pre-fill known dataset paths for this machine (e.g. derecho). Omit to leave <KEY> placeholders.",
    )
    template_parser.set_defaults(func=_template)

    args = parser.parse_args()
    args.func(args)
