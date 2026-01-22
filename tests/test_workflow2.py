"This should only be run explicitly, it's not a unit test"

import pytest
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from pathlib import Path
from CrocoDash.case import Case
import os
import logging
import dask
import shutil
import json
import subprocess
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
dask.config.set(num_workers=4)

def full_workflow_with_cirrus(
    case_path,
    cesm_root_path,
    machine = "derecho",
):
    """Tests if the full CrocoDash workflow runs successfully."""

    # Set Grid Info
    grid = Grid.from_supergrid("/glade/campaign/cesm/cesmdata/inputdata/ocn/mom/croc/testing_data/panama-bgc/ocean_hgrid_panama1_5490e0.nc")
    topo = Topo.from_topo_file(
        grid = grid,
        topo_file_path="/glade/campaign/cesm/cesmdata/inputdata/ocn/mom/croc/testing_data/panama-bgc/ocean_topog_panama1_5490e0.nc",
        min_depth = 9.5,
    )
    vgrid = VGrid.from_file("/glade/campaign/cesm/cesmdata/inputdata/ocn/mom/croc/testing_data/panama-bgc/ocean_vgrid_panama1_5490e0.nc")

    # Find CESM Root
    cesmroot = cesm_root_path

    # Set some defaults
    caseroot, inputdir = case_path / "test_workflow_case", case_path / "test_workflow_case_inputdir"
    project_num = "NCGD0011"
    override = True
    compset = "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    atm_grid_name = "TL319"

    # Setup Case
    case = Case(
        cesmroot=cesmroot,
        caseroot=caseroot,
        inputdir=inputdir,
        compset=compset,
        ocn_grid=grid,
        ocn_vgrid=vgrid,
        ocn_topo=topo,
        project=project_num,
        override=override,
        machine=machine,
        atm_grid_name=atm_grid_name,
    )
    case.configure_forcings(
        date_range=["2000-01-01 00:00:00", "2000-01-06 00:00:00"],
    )

    # Slide the raw data into the extract_forcings workflow from inputdata
    dst_dir = case.inputdir/"extract_forcings"/"raw_data"
    dst_dir.mkdir(exist_ok=True)
    src = Path("/glade/campaign/cesm/cesmdata/inputdata/ocn/mom/croc/testing_data/panama-raw-data")
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dst_dir / item.name)
    
    subprocess.run(
        [ "./xmlchange", "NTASKS=10"],
        cwd=caseroot,
        check=True,
    )

    subprocess.run(
        [ "./case.setup", "--reset"],
        cwd=caseroot,
        check=True,
    )
    
    subprocess.run(
        ["./case.build"],
        cwd=caseroot,
        check=True,
    )

    subprocess.run(
        ["./case.submit", "--no-batch"],
        cwd=caseroot,
        check=True,
    )
    



if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Run full CrocoDash workflow with cirrus (EXPLICIT ONLY)"
    )
    parser.add_argument(
        "--case-path",
        required=True,
        type=Path,
        help="Directory where the case and inputdir will be created",
    )
    parser.add_argument(
        "--cesm-root",
        required=True,
        type=Path,
        help="Path to CESM root directory",
    )
    parser.add_argument(
        "--machine",
        required=True,
        type=str,
        help="machine to run case",
    )


    args = parser.parse_args()

    full_workflow_with_cirrus(
        case_path=args.case_path,
        cesm_root_path=args.cesm_root,
        machine = args.machine
    )
