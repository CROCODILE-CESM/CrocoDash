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
    valid_topo_types = {"flat", "dataset", "from_file"}
    if "source" in topo_cfg and source_cfg.get("type") not in valid_topo_types:
        raise ValueError(f"topo.source.type must be one of {valid_topo_types}")

    vgrid_cfg = config.get("vgrid", {})
    valid_vgrid_types = {"uniform", "hyperbolic", "from_file"}
    if vgrid_cfg.get("type") not in valid_vgrid_types:
        raise ValueError(f"vgrid.type must be one of {valid_vgrid_types}")

    forcings_cfg = config["forcings"]
    for key in ("date_range", "boundaries", "product_name", "function_name"):
        if key not in forcings_cfg:
            raise ValueError(f"forcings.{key} is required")
    dr = forcings_cfg["date_range"]
    if not (isinstance(dr, list) and len(dr) == 2):
        raise ValueError("forcings.date_range must be a list of exactly 2 date strings")
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
    return Grid(
        lenx=grid_cfg["lenx"],
        leny=grid_cfg["leny"],
        nx=grid_cfg.get("nx"),
        ny=grid_cfg.get("ny"),
        resolution=grid_cfg.get("resolution"),
        xstart=grid_cfg.get("xstart", 0.0),
        ystart=grid_cfg.get("ystart"),
        cyclic_x=grid_cfg.get("cyclic_x", False),
        name=grid_cfg.get("name"),
        type=grid_cfg.get("type", "uniform_spherical"),
    )


def build_topo(topo_cfg, grid):
    """Build a Topo from a config dict. Dispatches on topo.source.type."""
    min_depth = topo_cfg["min_depth"]
    source = topo_cfg.get("source", {})
    source_type = source.get("type", "flat")

    if source_type == "from_file":
        return Topo.from_topo_file(
            grid, source["topo_file_path"], min_depth=min_depth, git=False
        )

    topo = Topo(grid, min_depth, git=False)

    if source_type == "flat":
        topo.set_flat(source["depth"])
    elif source_type == "dataset":
        topo.set_from_dataset(
            bathymetry_path=source["bathymetry_path"],
            longitude_coordinate_name=source.get("longitude_coordinate_name", "lon"),
            latitude_coordinate_name=source.get("latitude_coordinate_name", "lat"),
            vertical_coordinate_name=source.get(
                "vertical_coordinate_name", "elevation"
            ),
            fill_channels=source.get("fill_channels", False),
            is_input_positive_below_msl=source.get(
                "is_input_positive_below_msl", False
            ),
        )
    else:
        raise ValueError(f"Unknown topo.source.type: '{source_type}'")

    return topo


def build_vgrid(vgrid_cfg, topo):
    """Build a VGrid from a config dict. If depth is omitted, uses topo.max_depth."""
    vgrid_type = vgrid_cfg.get("type", "uniform")

    if vgrid_type == "from_file":
        return VGrid.from_file(
            filename=vgrid_cfg["filename"],
            variable_name=vgrid_cfg.get("variable_name", "dz"),
            variable_type=vgrid_cfg.get("variable_type", "layer_thickness"),
            name=vgrid_cfg.get("name"),
        )

    depth = vgrid_cfg.get("depth") or topo.max_depth

    if vgrid_type == "uniform":
        return VGrid.uniform(
            nk=vgrid_cfg["nk"],
            depth=depth,
            name=vgrid_cfg.get("name"),
        )
    elif vgrid_type == "hyperbolic":
        return VGrid.hyperbolic(
            nk=vgrid_cfg["nk"],
            depth=depth,
            ratio=vgrid_cfg["ratio"],
            name=vgrid_cfg.get("name"),
        )
    else:
        raise ValueError(f"Unknown vgrid.type: '{vgrid_type}'")


def create_case_from_yaml(config, override=False):
    """
    Run the full case creation workflow from a config dict.

    Builds Grid, Topo, and VGrid objects, creates the CESM case, and (if a
    forcings section is present) calls configure_forcings. Returns the Case.
    """
    grid = build_grid(config["grid"])
    topo = build_topo(config["topo"], grid)
    vgrid = build_vgrid(config["vgrid"], topo)

    case_cfg = config["case"]
    case = Case(
        cesmroot=case_cfg["cesmroot"],
        caseroot=case_cfg["caseroot"],
        inputdir=case_cfg["inputdir"],
        compset=case_cfg["compset"],
        ocn_grid=grid,
        ocn_topo=topo,
        ocn_vgrid=vgrid,
        atm_grid_name=case_cfg.get("atm_grid_name", "TL319"),
        rof_grid_name=case_cfg.get("rof_grid_name"),
        ninst=case_cfg.get("ninst", 1),
        machine=case_cfg["machine"],
        project=case_cfg.get("project"),
        override=override,
        ntasks_ocn=case_cfg.get("ntasks_ocn"),
        job_queue=case_cfg.get("job_queue"),
        job_wallclock_time=case_cfg.get("job_wallclock_time"),
    )

    if "forcings" in config:
        forcings_cfg = config["forcings"]
        extra_kwargs = {
            k: v
            for k, v in forcings_cfg.items()
            if k not in ("date_range", "boundaries", "product_name", "function_name")
        }
        case.configure_forcings(
            date_range=forcings_cfg["date_range"],
            boundaries=forcings_cfg["boundaries"],
            product_name=forcings_cfg["product_name"],
            function_name=forcings_cfg["function_name"],
            **extra_kwargs,
        )
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
            "cesmroot": state["cesmroot"],
            "caseroot": str(caseroot),
            "inputdir": state["inputdir"],
            "compset": state["compset_lname"],
            "machine": state["machine"],
            "project": state.get("project"),
            "atm_grid_name": state.get("atm_grid_name", "TL319"),
        },
    }

    forcing_config_path = Path(state["inputdir"]) / "extract_forcings" / "config.json"
    if forcing_config_path.exists():
        with open(forcing_config_path) as f:
            forcing_config = json.load(f)
        config["forcings"] = generate_configure_forcing_args(forcing_config)

    return config
