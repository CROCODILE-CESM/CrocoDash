import json
from datetime import datetime
from pathlib import Path

import xarray as xr
import yaml

from CrocoDash.case import Case
from CrocoDash.forcing_configurations.base import ForcingConfigRegistry
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.logging import setup_logger

logger = setup_logger(__name__)

_TOPO_SOURCE_TYPES = {"flat", "dataset", "from_file"}
_VGRID_TYPES = {"uniform", "hyperbolic", "from_file"}

# State keys that are derived/resolved at init time and cannot be passed straight back
# to Case.__init__ — handled explicitly in case_to_yaml's "case" section.
_STATE_DERIVED_KEYS = frozenset(
    {
        "inputdir",
        "cesmroot",
        "supergrid_path",
        "topo_path",
        "vgrid_path",
        "grid_name",
        "session_id",
        "compset_lname",
        "machine",
    }
)


def load_config(path):
    """Read a YAML case config file, validate its structure, and return the config dict."""
    with open(path) as f:
        config = yaml.safe_load(f)
    validate_config_structure(config)
    return config


def validate_config_structure(config):
    """Fast pre-flight structural checks on a config dict before any expensive work."""
    required_top = {"grid", "topo", "vgrid", "case", "forcings"}
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


def create_case_from_yaml(config, override=False, configure_only=False):
    """
    Run the full case creation workflow from a config dict.

    Builds Grid, Topo, and VGrid objects, creates the CESM case, then calls
    configure_forcings and process_forcings. A forcings section is required.
    Returns the Case.

    Parameters
    ----------
    configure_only : bool
        If True, skip process_forcings. Useful when you only need the case
        configured (e.g. to diff against a reference case) without running
        the expensive forcing extraction step.
    """
    grid = build_grid(config["grid"])
    topo = build_topo(config["topo"], grid)
    vgrid = build_vgrid(config["vgrid"], topo)

    case = Case(
        ocn_grid=grid,
        ocn_topo=topo,
        ocn_vgrid=vgrid,
        override=override,
        **config["case"],
    )

    case.configure_forcings(**config["forcings"])
    if not configure_only:
        case.process_forcings()

    return case


def generate_configure_forcing_args(forcing_config, remove_configs=None):
    """Convert a config.json forcing_config dict into configure_forcings kwargs."""
    if remove_configs is None:
        remove_configs = []
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


def case_to_yaml(caseroot):
    """
    Reconstruct a YAML config dict from an existing case's state files.

    Reads crocodash_state.json (written by Case.__init__) and, if present,
    extract_forcings/config.json (written by Case.configure_forcings).
    Returns a dict suitable for passing to create_case_from_yaml or writing
    to a YAML file with yaml.dump().
    """
    caseroot = Path(caseroot)
    state_path = caseroot / "crocodash_state.json"
    if not state_path.exists():
        raise FileNotFoundError(
            f"No crocodash_state.json found in {caseroot}. "
            "This case may not have been created with a recent version of CrocoDash."
        )
    with open(state_path) as f:
        state = json.load(f)

    topo_ds = xr.open_dataset(state["topo_path"])
    min_depth = float(topo_ds.attrs.get("min_depth", 0.0))
    topo_ds.close()

    config = {
        "grid": {
            "supergrid_path": state["supergrid_path"],
            "name": state["grid_name"],
        },
        "topo": {
            "min_depth": min_depth,
            "source": {
                "type": "from_file",
                "topo_file_path": state["topo_path"],
            },
        },
        "vgrid": {
            "type": "from_file",
            "filename": state["vgrid_path"],
        },
        "case": {
            # Derived/resolved fields — require explicit mapping from state keys
            "cesmroot": state["cesmroot"],
            "caseroot": str(caseroot),
            "inputdir": state["inputdir"],
            "compset": state["compset_lname"],
            "machine": state["machine"],
            # Scalar init args stored verbatim by Case._init_args — pull dynamically
            # so new Case.__init__ params flow through without touching this function.
            **{k: v for k, v in state.items() if k not in _STATE_DERIVED_KEYS},
        },
    }

    forcing_config_path = Path(state["inputdir"]) / "extract_forcings" / "config.json"
    if forcing_config_path.exists():
        with open(forcing_config_path) as f:
            forcing_config = json.load(f)
        config["forcings"] = generate_configure_forcing_args(forcing_config)

    return config
