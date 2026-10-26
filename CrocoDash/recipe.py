"""
recipe.py — Creating a Case directly from a YAML config dict or file.

Built on top of case.py, which handles the actual case creation through API calls,
This module adds the layer for creating a case from a yaml file, which is a convenient way to create a case without having to write a script.
The YAML file can be generated from an existing case using the case_to_yaml function, which reads the case's state files and reconstructs a config dict suitable for passing to create_case_from_yaml.

"""

from pathlib import Path

import xarray as xr
import yaml

from CrocoDash.case import Case, _CHANGE_KINDS
from CrocoDash import case_state
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid

_TOPO_SOURCE_TYPES = {"flat", "dataset", "from_file"}
_VGRID_TYPES = {"uniform", "hyperbolic", "from_file"}

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
    required_top = {"grid", "topo", "vgrid", "case"}
    missing = required_top - set(config.keys())
    if missing:
        raise ValueError(f"Config missing required top-level sections: {missing}")

    case_cfg = config["case"]
    for key in ("cesmroot", "caseroot", "inputdir", "compset", "machine"):
        if key not in case_cfg:
            raise ValueError(f"case.{key} is required")

    topo_cfg = config.get("topo", {})
    source_cfg = topo_cfg.get("source", {})
    if "source" in topo_cfg and source_cfg.get("type") not in _TOPO_SOURCE_TYPES:
        raise ValueError(f"topo.source.type must be one of {_TOPO_SOURCE_TYPES}")

    vgrid_cfg = config.get("vgrid", {})
    vgrid_type = vgrid_cfg.get("type")
    if vgrid_type is not None and vgrid_type not in _VGRID_TYPES:
        raise ValueError(f"vgrid.type must be one of {_VGRID_TYPES}")

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


def build_grid(grid_cfg):
    """Build a Grid from a config dict. Uses supergrid_path for file-based grids."""
    if "supergrid_path" in grid_cfg:
        grid = Grid.from_supergrid(grid_cfg["supergrid_path"])
        if grid_cfg.get("name"):
            grid.name = grid_cfg["name"]
        return grid
    return Grid(**grid_cfg)


def build_topo(topo_cfg, grid):
    """Build a Topo from a config dict. Dispatches on topo.source.type."""
    min_depth = topo_cfg["min_depth"]
    source = topo_cfg.get("source", {})
    source_type = source.get("type", "flat")

    if source_type == "from_file":
        return Topo.from_topo_file(grid, source["topo_file_path"], min_depth=min_depth)

    topo = Topo(grid, min_depth)

    if source_type == "flat":
        topo.set_flat(source["depth"])
    elif source_type == "dataset":
        topo.set_from_dataset(**{k: v for k, v in source.items() if k != "type"})
    else:
        raise ValueError(f"Unknown topo.source.type: '{source_type}'")

    return topo


def build_vgrid(vgrid_cfg, topo):
    """Build a VGrid from a config dict. If depth is omitted, uses topo.max_depth."""
    vgrid_type = vgrid_cfg.get("type", "uniform")

    if vgrid_type == "from_file":
        return VGrid.from_file(**{k: v for k, v in vgrid_cfg.items() if k != "type"})

    depth = vgrid_cfg.get("depth") or topo.max_depth
    kwargs = {k: v for k, v in vgrid_cfg.items() if k not in ("type", "depth")}
    kwargs["depth"] = depth

    if vgrid_type == "uniform":
        return VGrid.uniform(**kwargs)
    elif vgrid_type == "hyperbolic":
        return VGrid.hyperbolic(**kwargs)
    else:
        raise ValueError(f"Unknown vgrid.type: '{vgrid_type}'")


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

    Builds Grid, Topo, and VGrid objects, creates the CESM case, then calls
    configure_forcings and process_forcings. Returns the Case.

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
    grid = build_grid(config["grid"])
    topo = build_topo(config["topo"], grid)
    vgrid = build_vgrid(config["vgrid"], topo)

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
    The create config of an existing case: its grid files, the arguments it
    was created with and its forcing arguments, as a dict for
    create_case_from_yaml() or yaml.dump().

    ``caseroot`` is a caseroot, a bundle (whose files it names in the bundle),
    or a Case read from either.
    """
    case = caseroot if isinstance(caseroot, Case) else Case.from_caseroot(caseroot)
    state = case_state.read(case.caseroot)
    with xr.open_dataset(case.topo_path) as topo_ds:
        min_depth = float(topo_ds.attrs.get("min_depth", 0.0))
    # A bundle's case is named by the caseroot it was bundled from.
    bundled_from = case.bundled_from or {}

    config = {
        "grid": {
            "supergrid_path": case.supergrid_path,
            "name": case.grid_name,
        },
        "topo": {
            "min_depth": min_depth,
            "source": {
                "type": "from_file",
                "topo_file_path": case.topo_path,
            },
        },
        "vgrid": {
            "type": "from_file",
            "filename": case.vgrid_path,
        },
        "case": {
            # Derived/resolved fields — require explicit mapping from state keys
            "cesmroot": str(case.cesmroot),
            "caseroot": bundled_from.get("caseroot", str(case.caseroot)),
            "inputdir": bundled_from.get("inputdir", str(case.inputdir)),
            "compset": case.compset_lname,
            "machine": case.machine,
            # Scalar init args stored verbatim by Case._init_args — pull dynamically
            # so new Case.__init__ params flow through without touching this function.
            **{k: v for k, v in state.items() if k not in case_state.DERIVED_KEYS},
        },
    }

    forcings = case.forcing_args()
    if forcings:
        config["forcings"] = forcings

    return config
