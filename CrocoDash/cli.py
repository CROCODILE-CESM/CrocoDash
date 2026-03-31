import argparse
import json
from CrocoDash.shareable.inspect import ReadCrocoDashCase
from CrocoDash.shareable.fork import ForkCrocoDashBundle

def _read(args):

    case = ReadCrocoDashCase(args.caseroot)
    case.identify_non_standard_CrocoDash_case_information(
        cesmroot=args.cesmroot,
        machine=args.machine,
        project_number=args.project,
    )
    bundle_path = case.bundle(args.output_dir)
    print(f"Bundle written to: {bundle_path}")


def _fork(args):
    
    plan = json.loads(args.plan) if args.plan else None
    extra_configs = [x.strip() for x in args.extra_configs.split(",") if x.strip()] if args.extra_configs else None
    remove_configs = [x.strip() for x in args.remove_configs.split(",") if x.strip()] if args.remove_configs else None

    forker = ForkCrocoDashBundle(
        bundle_location=args.bundle,
        cesmroot=args.cesmroot,
        machine=args.machine,
        project_number=args.project,
        new_caseroot=args.caseroot,
        new_inputdir=args.inputdir,
    )
    forker.fork(
        plan=plan,
        compset=args.compset,
        extra_configs=extra_configs,
        remove_configs=remove_configs,
        extra_forcing_args_path=args.extra_forcing_args,
    )


def main():
    parser = argparse.ArgumentParser(prog="crocodash")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- read ---
    read_parser = subparsers.add_parser(
        "read", help="Read an existing CrocoDash case and produce a shareable bundle."
    )
    read_parser.add_argument("--caseroot", required=True, help="Path to the existing CESM caseroot.")
    read_parser.add_argument("--output-dir", required=True, dest="output_dir", help="Directory to write the bundle into.")
    read_parser.add_argument("--cesmroot", required=True, help="Path to the CESM source root.")
    read_parser.add_argument("--machine", required=True, help="Machine name (e.g. derecho).")
    read_parser.add_argument("--project", required=True, help="Project/account number.")
    read_parser.set_defaults(func=_read)

    # --- fork ---
    fork_parser = subparsers.add_parser(
        "fork", help="Create a new case from a CrocoDash bundle."
    )
    fork_parser.add_argument("--bundle", required=True, help="Path to the bundle directory.")
    fork_parser.add_argument("--caseroot", required=True, help="Path for the new caseroot.")
    fork_parser.add_argument("--inputdir", required=True, help="Path for the new input directory.")
    fork_parser.add_argument("--cesmroot", required=True, help="Path to the CESM source root.")
    fork_parser.add_argument("--machine", required=True, help="Machine name (e.g. derecho).")
    fork_parser.add_argument("--project", required=True, help="Project/account number.")
    # optional bypass flags
    fork_parser.add_argument("--compset", default=None, help="Override the compset from the bundle.")
    fork_parser.add_argument("--plan", default=None, help='JSON object controlling what to copy, e.g. \'{"xml_files": true, "user_nl": true, "source_mods": false, "xmlchanges": true}\'.')
    fork_parser.add_argument("--extra-configs", default=None, dest="extra_configs", help="Comma-separated forcing configs to add.")
    fork_parser.add_argument("--remove-configs", default=None, dest="remove_configs", help="Comma-separated forcing configs to drop.")
    fork_parser.add_argument("--extra-forcing-args", default=None, dest="extra_forcing_args", help="Path to JSON file with extra forcing arguments.")
    fork_parser.set_defaults(func=_fork)

    args = parser.parse_args()
    args.func(args)
