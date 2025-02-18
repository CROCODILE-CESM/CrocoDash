import pytest
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from pathlib import Path
from CrocoDash.case import Case
import os
#from Crocodash.data_access import driver as dv
import numpy as np
import xarray as xr
import subprocess
import logging
import dask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
dask.config.set(num_workers=4)

# os.environ["CESMROOT"] = "/glade/u/home/manishrv/work/installs/CROCESM_beta04_clean"
# os.environ["CIME_MACHINE"] = "derecho"

@pytest.mark.workflow
def test_full_workflow(tmp_path, is_github_actions, get_cesm_root_path, dummy_tidal_data, dummy_forcing_factory):

    """Tests if the full CrocoDash workflow runs successfully."""

    if not is_github_actions:
        if os.getenv("CIME_MACHINE") == None and os.getenv("CESMROOT") == None:
            pytest.skip("The test is only to be run if CIME_MACHINE and CESMROOT env vars are set")
        

    cesmroot = get_cesm_root_path
    result = run_full_workflow(tmp_path, cesmroot,dummy_tidal_data,dummy_forcing_factory)
    assert result["success"], f"Workflow failed: {result["logs"]}"
    
def run_full_workflow(tmp_path, cesmroot,dummy_tidal_data, dummy_forcing_factory):
    """Run the entire CrocoDash workflow (lightly)"""

    logs = ""
    logger.info("Running Workflow")
    ## Set Up Directories & Tidal Data ##
    os.makedirs(tmp_path/"croc_input", exist_ok=True)
    os.makedirs(tmp_path/"croc_cases", exist_ok=True)
    h,u = dummy_tidal_data
    h.to_netcdf(tmp_path/"h.nc")
    u.to_netcdf(tmp_path/"u.nc")

    ## Run Workflow ##

    # Grid Generation
    grid = Grid(
        resolution = 0.1,
        xstart = 278.0,
        lenx = 1.0,
        ystart = 7.0,
        leny = 1.0,
        name = "test1",
    )

    topo = Topo(
        grid = grid,
        min_depth = 9.5,
    )

    topo._depth = np.random.uniform(0, 3000, (10, 10))

    vgrid  = VGrid.hyperbolic(
        nk = 75,
        depth = topo.max_depth,
        ratio=20.0
        )
    
    # CESM case setup
    casename = "test-1"
    inputdir = tmp_path / "croc_input" / casename
    caseroot = tmp_path / "croc_cases" / casename
    case = Case(
    cesmroot = cesmroot,
    caseroot = caseroot,
    inputdir = inputdir,
    ocn_grid = grid,
    ocn_vgrid = vgrid,
    ocn_topo = topo,
    project = 'NCGD0011',
    override = True,
    machine = "ubuntu-latest"
)

    # Forcing setup
    case.configure_forcings(
    date_range = ["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
    tidal_constituents = ['M2'],
    tpxo_elevation_filepath = tmp_path/"h.nc",
    tpxo_velocity_filepath = tmp_path/"u.nc"
    )

    # Create dummy forcings
    grid.write_supergrid(tmp_path/"temphgrid.nc")
    hgrid = xr.open_dataset(tmp_path/"temphgrid.nc")
    ds = dummy_forcing_factory(hgrid.y.min(),hgrid.y.max(),hgrid.x.min(),hgrid.x.max())
    # bounds = dv.get_rectangular_boundary_info(grid)
    # ic = dummy_forcing_factory(bounds["ic"]["lat_min"],bounds["ic"]["lat_max"],bounds["ic"]["lon_min"],bounds["ic"]["lon_max"])
    # east = dummy_forcing_factory(bounds["east"]["lat_min"],bounds["east"]["lat_max"],bounds["east"]["lon_min"],bounds["east"]["lon_max"])
    # west = dummy_forcing_factory(bounds["west"]["lat_min"],bounds["west"]["lat_max"],bounds["west"]["lon_min"],bounds["west"]["lon_max"])
    # north = dummy_forcing_factory(bounds["north"]["lat_min"],bounds["north"]["lat_max"],bounds["north"]["lon_min"],bounds["north"]["lon_max"])
    # south = dummy_forcing_factory(bounds["south"]["lat_min"],bounds["south"]["lat_max"],bounds["south"]["lon_min"],bounds["south"]["lon_max"])
    ds.to_netcdf(case.inputdir / "glorys"/"ic_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"east_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"west_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"north_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"south_unprocessed.nc")

    # Process Forcings   
    case.process_forcings()


    # Build & Submit
    logger.info("Building Case")
    command = "./case.build"
    result = subprocess.run(command, shell=True, cwd=case.caseroot, text=True)
    logs += "Output:" + result.stdout + "Error: " + result.stderr
    logger.info("Submitting Case")
    command = "./case.submit"
    result = subprocess.run(command, shell=True, cwd=case.caseroot, text=True)
    logs += "Output:" + result.stdout + "Error: " + result.stderr
    return {
        "success": True,
        "logs":logs
    }

def test_dummy_forcing_data_fixture(dummy_forcing_factory,tmp_path):
    ic = dummy_forcing_factory()
    ic.to_netcdf(tmp_path/"ic_unprocessed.nc")
    assert os.path.exists(tmp_path/"ic_unprocessed.nc")