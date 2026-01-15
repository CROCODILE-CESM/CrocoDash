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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
dask.config.set(num_workers=4)

@pytest.mark.workflow
def test_full_workflow_with_cirrus(
    tmp_path,
    skip_if_not_glade,
    get_cesm_root_path,
):
    """Tests if the full CrocoDash workflow runs successfully."""

    # Set Grid Info
    grid = Grid.from_supergrid("/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama-bgc/ocean_hgrid_panama1_5490e0.nc")
    topo = Topo.from_topo_file(
        grid = grid,
        topo_file_path="/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama-bgc/ocean_topog_panama1_5490e0.nc",
        min_depth = 9.5,
    )
    vgrid = VGrid.from_file("/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama-bgc/ocean_vgrid_panama1_5490e0.nc")

    # Find CESM Root
    cesmroot = get_cesm_root_path

    # Set some defaults
    caseroot, inputdir = tmp_path / "case", tmp_path / "inputdir"
    project_num = "NCGD0011"
    override = True
    compset = "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    atm_grid_name = "TL319"
    machine = "derecho"

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
        date_range=["2000-01-01 00:00:00", "2000-02-01 00:00:00"],
    )

    # Slide the raw data into the extract_forcings workflow from inputdata
    dst_dir = case.inputdir/"extract_forcings"/"raw_data"
    dst_dir.mkdir(exist_ok=True)
    src = Path("/glade/campaign/cesm/cesmdata/inputdata/ocn/mom/croc/testing_data/panama-raw-data")
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dst_dir / item.name)
    

    # Open Config File change step to 5 -> what the raw data is at
    config_path  = case.inputdir/"extract_forcings"/"config.json"
    with config_path.open("r") as f:
        config = json.load(f)

    config["basic"]["general"]["step"] = 5
    # write back to same destination
    with config_path.open("w") as f:
        json.dump(config, f, indent=2)


    case.process_forcings()
    
    assert True



