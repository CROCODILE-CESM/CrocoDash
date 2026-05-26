#!/usr/bin/env python3
"""
CESM Regional Ocean Case Setup Script

Configures and runs a MOM6 regional ocean case using CrocoDash,
including grid definition, topography, vertical grid, and CESM case setup.
"""

import argparse
import os
import sys
from pathlib import Path
import subprocess
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.case import Case
from CrocoDash.raw_data_access.datasets.gebco import GEBCO


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
    bathy_dir = Path("bathy_dir")
    bathy = Path("GEBCO.nc")
    print(
        f"No --bathymetry-path provided. Downloading GEBCO data → {bathy_dir / bathy}"
    )
    GEBCO.get_gebco_data_with_python(bathy_dir, bathy)
    bathy = bathy_dir / bathy

    if not bathy.exists():
        raise FileNotFoundError(
            "GEBCO download succeeded but the output file was not found. "
            "Check GEBCO credentials / connectivity, or supply --bathymetry-path manually.\n"
            "  Derecho path: <GEBCO>"
        )
    return bathy


def main() -> None:
    args = parse_args()
    args = resolve_paths(args)

    # ------------------------------------------------------------------ #
    # Grid
    # ------------------------------------------------------------------ #
    print(f"\n[1/5] Building horizontal grid '{args.name}' …")
    grid = Grid(
        resolution=args.resolution,
        xstart=args.xstart,
        lenx=args.lenx,
        ystart=args.ystart,
        leny=args.leny,
        name=args.name,
    )

    # ------------------------------------------------------------------ #
    # Topography
    # ------------------------------------------------------------------ #
    print("[2/5] Setting up topography …")
    topo = Topo(grid=grid, min_depth=args.min_depth)
    bathymetry_path = get_bathymetry(args)
    topo.set_from_dataset(
        bathymetry_path=bathymetry_path,
        longitude_coordinate_name=args.lon_coord,
        latitude_coordinate_name=args.lat_coord,
        vertical_coordinate_name=args.elev_coord,
    )

    # ------------------------------------------------------------------ #
    # Vertical grid
    # ------------------------------------------------------------------ #
    print("[3/5] Building vertical grid …")
    vgrid = VGrid.hyperbolic(
        nk=args.nk,
        depth=topo.max_depth,
        ratio=args.vgrid_ratio,
    )

    # ------------------------------------------------------------------ #
    # CESM case
    # ------------------------------------------------------------------ #
    print(f"[4/5] Creating CESM case '{args.casename}' …")
    os.environ["CIME_MACHINE"] = args.machine
    case = Case(
        cesmroot=args.cesmroot,
        caseroot=Path(args.caseroot) / args.casename,
        inputdir=Path(args.inputdir) / args.casename,
        ocn_grid=grid,
        ocn_vgrid=vgrid,
        ocn_topo=topo,
        project=args.project,
        override=args.override,
        machine=args.machine,
        compset=args.compset,
        atm_grid_name=args.atm_grid_name,
    )

    # ------------------------------------------------------------------ #
    # Forcings
    # ------------------------------------------------------------------ #
    print("[5/5] Configuring and processing forcings …")
    case.configure_forcings(
        date_range=[args.date_start, args.date_end],
        function_name=args.forcing_fn,
    )

    # Get the raw data fast through AWS
    output_dir = case.extract_forcings_path / "raw_data"
    os.makedirs(output_dir, exist_ok=True)
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
        dest = os.path.join(output_dir, f)
        print(f"Downloading {f}...")
        subprocess.run(["wget", "-O", dest, url], check=True)
    case.process_forcings()
    print("\nDone.")


if __name__ == "__main__":
    main()
