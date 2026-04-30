#!/usr/bin/env python
"""End-to-end Derecho-only smoke / profiling script.

Runs the full CrocoDash workflow for a small Panama domain with:

- **CR_JRA_GLOFAS** compset → exercises the **runoff mapping** code path
  (``rof_esmf_mesh_filepath`` → ESMF / SCRIP mapping files in ``process_forcings``)
- GLORYS OBCs pulled from **RDA** (``get_glorys_data_from_rda``) → exercises the
  **piecewise get / regrid / merge OBC** pipeline end-to-end

This mirrors the ``demos/gallery/notebooks/CrocoDash/projects/sample_crocodash_projects/DROF.ipynb``
tutorial, but collapsed into a single script so you can:

- run it directly (``python dev_tools/run_derecho_drof_e2e.py``)
- submit it to a batch queue

Profiling with Scalene
----------------------
Scalene's signal-based sampler interferes with the subprocesses CIME spawns
during ``Case(...)`` construction (you'll see spurious "Error running
./xmlchange" failures). The workaround is to split the two phases:

.. code-block:: bash

    # Phase 1: build the case & write config.json (NOT under scalene)
    python dev_tools/run_derecho_drof_e2e.py --phase setup

    # Phase 2: run only the expensive processing UNDER scalene
    scalene --profile-only CrocoDash --no-browser \\
        --outfile scalene_drof.html \\
        dev_tools/run_derecho_drof_e2e.py --phase process

It is **Derecho-specific** because it hard-codes Glade paths. It will exit early
on any other system.

Usage
-----
::

    # Default (small Panama domain, 1-month forcing)
    python dev_tools/run_derecho_drof_e2e.py

    # Override any knob via CLI
    python dev_tools/run_derecho_drof_e2e.py \\
        --casename pan.drof.profile \\
        --start 2000-01-01 --end 2000-01-10 \\
        --project UCSG0000

Outputs
-------
- ``caseroot`` = ``$HOME/croc_cases/<casename>``
- ``inputdir`` = ``$HOME/scratch/croc_input/<casename>``

Both are overwritten on every run (``override=True``).
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("drof_e2e")


# ---------------------------------------------------------------------------
# Glade-only paths. Keep these in ONE place so future moves are painless.
# ---------------------------------------------------------------------------
GLADE_PATHS = {
    "cesmroot": "/glade/u/home/manishrv/work/installs/CROCESM_workshop_2025",
    "gebco": "/glade/work/altuntas/croc/input/GEBCO_2024_coarse_x4.nc",
    "glofas_esmf_mesh": (
        "/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/"
        "rof/glofas/dis24/GLOFAS_esmf_mesh_v4.nc"
    ),
}


def on_glade() -> bool:
    """Detect whether this script is running on a Glade-equipped host."""
    return ("ucar" in socket.getfqdn()) and Path("/glade").exists()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--casename",
        default="pan.drof.e2e",
        help="Case name (used for both caseroot and inputdir).",
    )
    p.add_argument(
        "--project",
        default=os.environ.get("PROJECT", "UCSG0000"),
        help="CESM project/account code (default: $PROJECT or UCSG0000).",
    )
    p.add_argument(
        "--start",
        default="2000-01-01",
        help="Forcing start date (YYYY-MM-DD).",
    )
    p.add_argument(
        "--end",
        default="2000-02-01",
        help="Forcing end date (YYYY-MM-DD).",
    )
    p.add_argument(
        "--resolution",
        type=float,
        default=0.05,
        help="Horizontal resolution in degrees (default 0.05 = small Panama).",
    )
    p.add_argument(
        "--phase",
        choices=["all", "setup", "process"],
        default="all",
        help=(
            "Which phase to run: 'setup' = Case + configure_forcings only, "
            "'process' = only process_forcings on an existing inputdir, "
            "'all' = everything (default). Split into two phases when "
            "profiling with Scalene (see module docstring)."
        ),
    )
    p.add_argument(
        "--cesmroot",
        default=GLADE_PATHS["cesmroot"],
        help="Override CESM root (defaults to Glade install).",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
def main() -> int:
    args = parse_args()

    if not on_glade():
        log.error(
            "This script is Derecho/Casper only — it hard-codes /glade paths. "
            "Host %r is not on glade.",
            socket.getfqdn(),
        )
        return 2

    casename = args.casename
    caseroot = Path.home() / "croc_cases" / casename
    inputdir = Path.home() / "scratch" / "croc_input" / casename

    log.info("casename  = %s", casename)
    log.info("caseroot  = %s", caseroot)
    log.info("inputdir  = %s", inputdir)
    log.info("phase     = %s", args.phase)

    if args.phase in ("all", "setup"):
        _run_setup_phase(args, casename, caseroot, inputdir)

    if args.phase in ("all", "process"):
        _run_process_phase(inputdir)

    log.info("Done.")
    if args.phase in ("all", "setup"):
        log.info("Next: cd %s && qcmd -- ./case.build && ./case.submit", caseroot)
    return 0


def _run_setup_phase(
    args: argparse.Namespace,
    casename: str,
    caseroot: Path,
    inputdir: Path,
) -> None:
    """Steps 1, 2, 3a: grids + Case + configure_forcings.

    Kept out of the ``process`` phase because CIME's ``./xmlchange`` calls
    spawn subprocesses that misbehave under Scalene's signal-based profiler.
    """
    # Imports deferred so --help works without CrocoDash being importable.
    from CrocoDash.grid import Grid
    from CrocoDash.topo import Topo
    from CrocoDash.vgrid import VGrid
    from CrocoDash.case import Case

    log.info("cesmroot  = %s", args.cesmroot)
    log.info("project   = %s", args.project)
    log.info("date range= %s → %s", args.start, args.end)

    # -------------------------------------------------------------------
    # STEP 1: Grids
    # -------------------------------------------------------------------
    log.info("=== STEP 1: Grids ===")
    grid = Grid(
        resolution=args.resolution,
        xstart=278.0,  # Panama
        lenx=3.0,
        ystart=7.0,
        leny=3.0,
        name=casename.replace(".", "_"),
    )
    log.info("Grid: %s (%dx%d)", grid.name, grid.nx, grid.ny)

    topo = Topo(
        grid=grid,
        min_depth=9.5,
        version_control_dir=inputdir.parent / "TopoLibrary",
    )
    log.info("Setting bathymetry from GEBCO: %s", GLADE_PATHS["gebco"])
    topo.set_from_dataset(
        bathymetry_path=GLADE_PATHS["gebco"],
        longitude_coordinate_name="lon",
        latitude_coordinate_name="lat",
        vertical_coordinate_name="elevation",
    )

    vgrid = VGrid.hyperbolic(nk=75, depth=topo.max_depth, ratio=20.0)
    log.info("Vertical grid: nk=75, max_depth=%.1f m", topo.max_depth)

    # -------------------------------------------------------------------
    # STEP 2: Case setup — with DROF%GLOFAS so runoff mapping is exercised
    # -------------------------------------------------------------------
    log.info("=== STEP 2: Case setup (compset=CR_JRA_GLOFAS) ===")
    case = Case(
        cesmroot=args.cesmroot,
        caseroot=caseroot,
        inputdir=inputdir,
        ocn_grid=grid,
        ocn_vgrid=vgrid,
        ocn_topo=topo,
        project=args.project,
        override=True,
        machine="derecho",
        compset="CR_JRA_GLOFAS",
    )

    # -------------------------------------------------------------------
    # STEP 3a: Configure forcings — GLORYS via RDA + GLOFAS runoff mesh
    # -------------------------------------------------------------------
    log.info("=== STEP 3a: configure_forcings ===")
    case.configure_forcings(
        date_range=[f"{args.start} 00:00:00", f"{args.end} 00:00:00"],
        product_name="GLORYS",
        function_name="get_glorys_data_from_rda",
        rof_esmf_mesh_filepath=GLADE_PATHS["glofas_esmf_mesh"],
    )

    # Leave a pointer file so the process phase can find the driver easily.
    log.info("Setup phase complete. Inputdir ready at %s", inputdir)


def _run_process_phase(inputdir: Path) -> None:
    """Step 3b: run the standalone extract_forcings driver.

    This phase does NOT import CrocoDash.case, so it's safe to run under
    Scalene — no CIME subprocess calls in the hot path.
    """
    driver_dir = inputdir / "extract_forcings"
    driver_py = driver_dir / "driver.py"

    if not driver_py.exists():
        raise FileNotFoundError(
            f"{driver_py} not found. Did you run `--phase setup` first?"
        )

    log.info("=== STEP 3b: process_forcings (driver.py --all) ===")
    log.info("driver_dir = %s", driver_dir)

    # Invoke the driver in-process so Scalene sees every line of CrocoDash.
    # Equivalent to: `cd <driver_dir> && python driver.py --all`
    import runpy

    old_cwd = Path.cwd()
    old_argv = sys.argv[:]
    try:
        os.chdir(driver_dir)
        sys.argv = ["driver.py", "--all"]
        runpy.run_path(str(driver_py), run_name="__main__")
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv


if __name__ == "__main__":
    sys.exit(main())
