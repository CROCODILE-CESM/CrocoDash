#!/usr/bin/env python3
"""
CESM Regional Ocean Case Setup Script

Configures and runs a MOM6 regional ocean case using CrocoDash,
including grid definition, topography, vertical grid, and CESM case setup.
Flat bathymetry and the synthetic reference ocean: nothing is downloaded.
"""

import argparse
import os
from pathlib import Path
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from CrocoDash.case import Case


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
        "--depth", type=float, default=1000.0, help="Flat ocean depth in meters"
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
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Fill in derived default paths that depend on --casename."""
    if args.inputdir is None:
        args.inputdir = Path.home() / "croc_input" / args.casename
    if args.caseroot is None:
        args.caseroot = Path.home() / "croc_cases" / args.casename
    return args


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
    topo.set_flat(args.depth)

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
        product_name="reference_ocean",
        function_name="get_reference_ocean_data",
    )
    case.process_forcings()
    print("\nDone.")


if __name__ == "__main__":
    main()
