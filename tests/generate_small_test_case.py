#!/usr/bin/env python3
"""
CESM Regional Ocean Case Setup Script

Configures and runs a MOM6 regional ocean case via the `crocodash` CLI
(create --configure-only, then process --all), staging pre-fetched test
GEBCO/GLORYS data in between so this can run in CI without live data-access
credentials.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
import subprocess
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up a CESM MOM6 regional ocean case via CrocoDash.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # --- Grid ---
    grid = parser.add_argument_group("Grid")
    grid.add_argument(
        "--resolution", type=float, default=0.05, help="Grid resolution in degrees"
    )
    grid.add_argument(
        "--xstart", type=float, default=278.0, help="Minimum longitude [0, 360]"
    )
    grid.add_argument(
        "--lenx", type=float, default=3.0, help="Longitude extent in degrees"
    )
    grid.add_argument(
        "--ystart", type=float, default=7.0, help="Minimum latitude [-90, 90]"
    )
    grid.add_argument(
        "--leny", type=float, default=3.0, help="Latitude extent in degrees"
    )
    grid.add_argument("--name", type=str, default="panama1", help="Grid/domain name")

    # --- Topography ---
    topo = parser.add_argument_group("Topography")
    topo.add_argument(
        "--min-depth", type=float, default=9.5, help="Minimum ocean depth in meters"
    )
    topo.add_argument(
        "--bathymetry-path",
        type=Path,
        default=None,
        help="Path to existing bathymetry file (GEBCO .nc). "
        "If omitted, GEBCO data will be downloaded to ./GEBCO.nc",
    )
    topo.add_argument(
        "--lon-coord",
        type=str,
        default="lon",
        help="Longitude coordinate name in the bathymetry dataset",
    )
    topo.add_argument(
        "--lat-coord",
        type=str,
        default="lat",
        help="Latitude coordinate name in the bathymetry dataset",
    )
    topo.add_argument(
        "--elev-coord",
        type=str,
        default="elevation",
        help="Vertical/elevation coordinate name in the bathymetry dataset",
    )

    # --- Vertical grid ---
    vgrid = parser.add_argument_group("Vertical Grid")
    vgrid.add_argument("--nk", type=int, default=75, help="Number of vertical levels")
    vgrid.add_argument(
        "--vgrid-ratio",
        type=float,
        default=20.0,
        help="Target ratio of top-to-bottom layer thicknesses",
    )

    # --- CESM case ---
    case = parser.add_argument_group("CESM Case")
    case.add_argument(
        "--casename",
        type=str,
        default="panama-crocontainer",
        help="CESM experiment/case name",
    )
    case.add_argument(
        "--cesmroot",
        type=Path,
        default=None,
        help="Path to CESM source root",
    )
    case.add_argument(
        "--inputdir",
        type=Path,
        default=None,
        help="Directory for CESM input files (default: ~/croc_input/<casename>)",
    )
    case.add_argument(
        "--caseroot",
        type=Path,
        default=None,
        help="CESM case directory (default: ~/croc_cases/<casename>)",
    )
    case.add_argument(
        "--project", type=str, default="CESM0030", help="HPC project/account code"
    )
    case.add_argument(
        "--machine", type=str, default="ubuntu-latest", help="CIME machine name"
    )
    case.add_argument(
        "--compset",
        type=str,
        default="1850_DATM%NYF_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV_SESP",
        help="CESM compset alias or longname",
    )
    case.add_argument(
        "--atm_grid_name",
        type=str,
        default="T62",
        help="CESM atm grid name (T62 for NYF)",
    )
    case.add_argument(
        "--no-override",
        dest="override",
        action="store_false",
        help="Do not overwrite an existing case directory",
    )

    # --- Forcings ---
    forcings = parser.add_argument_group("Forcings")
    forcings.add_argument(
        "--date-start",
        type=str,
        default="2020-01-01 00:00:00",
        help="Forcing start date (YYYY-MM-DD HH:MM:SS)",
    )
    forcings.add_argument(
        "--date-end",
        type=str,
        default="2020-01-05 00:00:00",
        help="Forcing end date (YYYY-MM-DD HH:MM:SS)",
    )
    forcings.add_argument(
        "--forcing-fn",
        type=str,
        default="get_glorys_data_from_cds_api",
        help="Name of the forcing retrieval function",
    )

    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Fill in derived default paths that depend on --casename."""
    if args.inputdir is None:
        args.inputdir = Path.home() / "croc_input" / args.casename
    if args.caseroot is None:
        args.caseroot = Path.home() / "croc_cases" / args.casename
    return args


def get_bathymetry(args: argparse.Namespace) -> Path:
    """Return a resolved bathymetry path, downloading if necessary."""
    if args.bathymetry_path is not None:
        bathy = args.bathymetry_path
        if not bathy.exists():
            raise FileNotFoundError(
                f"Bathymetry file not found at specified path: {bathy}\n"
                "Pass a valid --bathymetry-path, or omit the flag to download GEBCO data."
            )
        print(f"Using existing bathymetry file: {bathy}")
        return bathy

    # Default: download GEBCO alongside this script
    bathy = Path("gebco_regional.nc")
    s3_path = "https://crocodile-cesm.s3.us-east-1.amazonaws.com/CrocoDash/data/testing_data/gebco_2026_n20.0_s0.0_w-90.0_e-70.0.nc"
    print(f"No --bathymetry-path provided. Downloading GEBCO data → {bathy}")
    subprocess.run(["wget", "-O", str(bathy), s3_path], check=True)

    if not bathy.exists():
        raise FileNotFoundError(
            "GEBCO download succeeded but the output file was not found. "
            "Check GEBCO credentials / connectivity, or supply --bathymetry-path manually.\n"
            "  Derecho path: <GEBCO>"
        )
    return bathy


def build_case_config(args: argparse.Namespace, bathymetry_path: Path) -> dict:
    """Assemble the recipe.py-schema config dict for this case from parsed args."""
    return {
        "grid": {
            "resolution": args.resolution,
            "xstart": args.xstart,
            "lenx": args.lenx,
            "ystart": args.ystart,
            "leny": args.leny,
            "name": args.name,
        },
        "topo": {
            "min_depth": args.min_depth,
            "source": {
                "type": "dataset",
                "bathymetry_path": str(bathymetry_path.resolve()),
                "longitude_coordinate_name": args.lon_coord,
                "latitude_coordinate_name": args.lat_coord,
                "vertical_coordinate_name": args.elev_coord,
            },
        },
        "vgrid": {
            "type": "hyperbolic",
            "nk": args.nk,
            "ratio": args.vgrid_ratio,
            # depth omitted: build_vgrid() derives it from topo.max_depth.
        },
        "case": {
            "cesmroot": str(args.cesmroot),
            "caseroot": str(Path(args.caseroot) / args.casename),
            "inputdir": str(Path(args.inputdir) / args.casename),
            "compset": args.compset,
            "atm_grid_name": args.atm_grid_name,
            "machine": args.machine,
            "project": args.project,
        },
        "forcings": {
            "date_range": [args.date_start, args.date_end],
            "function_name": args.forcing_fn,
        },
    }


def main() -> None:
    args = parse_args()
    args = resolve_paths(args)
    os.environ["CIME_MACHINE"] = args.machine

    caseroot = Path(args.caseroot) / args.casename
    inputdir = Path(args.inputdir) / args.casename

    print("[1/3] Building case config and creating case (configure-only) …")
    bathymetry_path = get_bathymetry(args)
    config = build_case_config(args, bathymetry_path)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as tmp_config:
        yaml.dump(config, tmp_config, default_flow_style=False, sort_keys=False)
        tmp_config_path = tmp_config.name

    try:
        create_cmd = ["crocodash", "create", "--config", tmp_config_path]
        if args.override:
            create_cmd.append("--override")
        create_cmd.append("--configure-only")
        subprocess.run(create_cmd, check=True)
    finally:
        os.unlink(tmp_config_path)

    print("[2/3] Staging test GLORYS OBC/IC data …")
    raw_data_dir = inputdir / "extract_forcings" / "raw_data"
    os.makedirs(raw_data_dir, exist_ok=True)
    base_url = (
        "https://crocodile-cesm.s3.us-east-1.amazonaws.com/CrocoDash/data/testing_data"
    )
    files = [
        "east_unprocessed.20200101_20200105.nc",
        "ic_unprocessed.nc",
        "north_unprocessed.20200101_20200105.nc",
        "south_unprocessed.20200101_20200105.nc",
        "west_unprocessed.20200101_20200105.nc",
    ]
    for f in files:
        url = f"{base_url}/{f}"
        dest = raw_data_dir / f
        print(f"Downloading {f}...")
        subprocess.run(["wget", "-O", str(dest), url], check=True)

    print("[3/3] Processing forcings …")
    subprocess.run(
        ["crocodash", "process", "--caseroot", str(caseroot), "--all"], check=True
    )
    print("\nDone.")


if __name__ == "__main__":
    main()
