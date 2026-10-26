"""
recipe.py — Creating a Case directly from a YAML config dict or file.

Built on top of case.py, which handles the actual case creation through API calls,
This module adds the layer for creating a case from a yaml file, which is a convenient way to create a case without having to write a script.
The YAML file can be generated from an existing case using the case_to_yaml function, which reads the case's state files and reconstructs a config dict suitable for passing to create_case_from_yaml.
A config has two sections: case, the arguments of Case(), with the grids as the files mom6_forge writes (ocn_grid, ocn_topo and ocn_vgrid), and forcings, the arguments of configure_forcings().

"""

from pathlib import Path

import xarray as xr
import yaml

from CrocoDash.case import Case, _CHANGE_KINDS
from CrocoDash import case_state
from CrocoDash.forcing.utils import read_min_depth
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid

# The source's own run, rather than how it is set up: how far it got and where
# it builds, runs and archives. A case made from it starts a run of its own
# (CONTINUE_RUN=TRUE would look for restart files it doesn't have) and must
# not share the source's directories.
_SOURCE_RUN_VARIABLES = ("CONTINUE_RUN", "RESUBMIT", "EXEROOT", "RUNDIR", "DOUT_S_ROOT")

# A source's settings for how it runs on its machine; wrong on another.
_MACHINE_ARGS = ("ntasks_ocn", "job_queue", "job_wallclock_time")


def load_config(path):
    """Read a YAML case config file, validate its structure, and return the config dict."""
    with open(path) as f:
        config = yaml.safe_load(f)
    validate_config_structure(config)
    return config


def validate_config_structure(config):
    """Fast pre-flight structural checks on a config dict before any expensive work."""
    if "case" not in config:
        raise ValueError("Config missing required top-level section: case")
    if built := sorted({"grid", "topo", "vgrid"} & config.keys()):
        raise ValueError(
            f"The config's {', '.join(built)} sections are no longer read: write "
            "the grid files with mom6_forge (CrocoDash.grid, CrocoDash.topo and "
            "CrocoDash.vgrid) and name them in case: as ocn_grid, ocn_topo and "
            "ocn_vgrid."
        )

    case_cfg = config["case"]
    for key in (
        "cesmroot",
        "caseroot",
        "inputdir",
        "compset",
        "machine",
        "ocn_grid",
        "ocn_topo",
        "ocn_vgrid",
    ):
        if key not in case_cfg:
            raise ValueError(f"case.{key} is required")

    # Without a forcings section, create_case_from_yaml() asks for them.
    if "forcings" not in config:
        return
    forcings_cfg = config["forcings"]
    if "date_range" not in forcings_cfg:
        raise ValueError("forcings.date_range is required")
    dr = forcings_cfg["date_range"]
    if not (isinstance(dr, list) and len(dr) == 2):
        raise ValueError("forcings.date_range must be a list of exactly 2 date strings")
    if "boundaries" in forcings_cfg:
        valid_boundaries = {"north", "south", "east", "west"}
        bad = set(forcings_cfg["boundaries"]) - valid_boundaries
        if bad:
            raise ValueError(f"Invalid boundary values: {bad}")
    if "tidal_constituents" in forcings_cfg:
        for tide_key in ("tpxo_elevation_filepath", "tpxo_velocity_filepath"):
            if tide_key not in forcings_cfg:
                raise ValueError(
                    f"forcings.{tide_key} is required when tidal_constituents is set"
                )


def read_grids(ocn_grid, ocn_topo, ocn_vgrid):
    """The Grid, Topo and VGrid in the grid files a config names, as mom6_forge
    writes them. The grid takes the name written in its file (or else the
    file's name), and the topography its min_depth."""
    with xr.open_dataset(ocn_grid) as ds:
        name = ds.attrs.get("name")
    grid = Grid.from_supergrid(ocn_grid, name=name)
    topo = Topo.from_topo_file(
        grid, ocn_topo, min_depth=read_min_depth(ocn_topo), git=False
    )
    return grid, topo, VGrid.from_file(str(ocn_vgrid))


def check_new_case(case_config, source):
    """Raise ValueError if the new case ``case_config`` (a create config's
    case: section) would clash with ``source``, the case it is made from: an
    inputdir inside the source's, the source's own caseroot, or the source's
    name on the source's machine, where CIME would give both the same build
    and run directories."""
    caseroot, inputdir = Path(case_config["caseroot"]), Path(case_config["inputdir"])
    source_name = Path(
        (source.bundled_from or {}).get("caseroot", source.caseroot)
    ).name
    if inputdir.resolve().is_relative_to(source.inputdir.resolve()):
        raise ValueError(
            f"The new inputdir {inputdir} is inside the source's, {source.inputdir}."
        )
    if caseroot.resolve() == source.caseroot.resolve() or (
        caseroot.name == source_name and case_config["machine"] == source.machine
    ):
        raise ValueError(
            f"The new case would be named {source_name} on {source.machine}, like "
            "its source, so CIME would give both the same build and run "
            "directories. Give the new caseroot another name."
        )


def create_case_from_yaml(
    config, override=False, configure_only=False, ask=False, source=None
):
    """
    Run the full case creation workflow from a config dict.

    Reads the grid files the case: section names, creates the CESM case, then
    calls configure_forcings and process_forcings. Returns the Case.

    Parameters
    ----------
    configure_only : bool
        If True, skip process_forcings. Useful when you only need the case
        configured (e.g. to diff against a reference case) without running
        the expensive forcing extraction step.
    ask : bool
        Ask for the forcings at the terminal once the case exists
        (configure_forcings(ask=True)), offering the config's forcings section
        as the answers. Without ask, the config needs a forcings section; if it
        has none, a ValueError, raised before anything is created.
    source : Case, optional
        The case this one is made from (crocodash create --from), read with
        Case.from_caseroot() from its caseroot or a bundle; the config is then
        case_to_yaml(source) with the new case's changes. The source's own xml,
        user_nl and SourceMods changes are carried over, except those specific
        to its machine on another machine and its run's CONTINUE_RUN, RESUBMIT
        and directories. The new case takes its session id, and, on the same
        machine, its PE layout and batch job. Its forcing files whose settings
        still match are copied (Case.copy_forcing_files()), so processing makes
        only the rest.
    """
    if "forcings" not in config and not ask:
        raise ValueError(
            "The config has no forcings section: add one, or run "
            "'crocodash create' on a terminal to be asked for them."
        )
    case_args = dict(config["case"])
    if source is not None:
        check_new_case(case_args, source)
        # The source's grid and forcing files then apply unrenamed.
        case_args.setdefault("session_id", source.session_id)
        if case_args["machine"] != source.machine:
            for key in _MACHINE_ARGS:
                case_args.pop(key, None)
    grid, topo, vgrid = read_grids(
        case_args.pop("ocn_grid"), case_args.pop("ocn_topo"), case_args.pop("ocn_vgrid")
    )

    case = Case(
        ocn_grid=grid,
        ocn_topo=topo,
        ocn_vgrid=vgrid,
        override=override,
        **case_args,
    )

    if source is not None:
        changes = source.user_changes(target_machine=case.machine)
        for var in _SOURCE_RUN_VARIABLES:
            changes["xmlchanges"].pop(var, None)
        case.apply_user_changes(changes)
    if ask:
        case.configure_forcings(ask=True, **config.get("forcings", {}))
    else:
        case.configure_forcings(**config["forcings"])
    if source is not None:
        copied = case.copy_forcing_files(source)
        left_out = sorted(
            source.user_changes()["xmlchanges"].keys() - changes["xmlchanges"].keys()
        )
        print(f"Created {case.caseroot} from {source.caseroot}.")
        for kind in _CHANGE_KINDS:
            if changes[kind]:
                print(f"  Carried over its {kind}: {', '.join(changes[kind])}")
        if left_out:
            print(f"  Left out as its machine's or its run's: {', '.join(left_out)}")
        print(f"  Forcing files copied for: {', '.join(sorted(copied)) or 'none'}")
    if not configure_only:
        case.process_forcings()

    return case


def case_to_yaml(caseroot):
    """
    The create config of an existing case: the arguments it was created with,
    its grid files among them, and its forcing arguments, as a dict for
    create_case_from_yaml() or yaml.dump().

    ``caseroot`` is a caseroot, a bundle (whose files it names in the bundle),
    or a Case read from either.
    """
    case = caseroot if isinstance(caseroot, Case) else Case.from_caseroot(caseroot)
    state = case_state.read(case.caseroot)
    # A bundle's case is named by the caseroot it was bundled from.
    bundled_from = case.bundled_from or {}

    config = {
        "case": {
            # Derived/resolved fields — require explicit mapping from state keys
            "cesmroot": str(case.cesmroot),
            "caseroot": bundled_from.get("caseroot", str(case.caseroot)),
            "inputdir": bundled_from.get("inputdir", str(case.inputdir)),
            "compset": case.compset_lname,
            "machine": case.machine,
            "ocn_grid": case.supergrid_path,
            "ocn_topo": case.topo_path,
            "ocn_vgrid": case.vgrid_path,
            # Scalar init args stored verbatim by Case._init_args — pull dynamically
            # so new Case.__init__ params flow through without touching this function.
            **{k: v for k, v in state.items() if k not in case_state.DERIVED_KEYS},
        },
    }

    forcings = case.forcing_args()
    if forcings:
        config["forcings"] = forcings

    return config
