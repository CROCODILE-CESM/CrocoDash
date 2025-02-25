import pytest
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from pathlib import Path
from CrocoDash.case import Case
import os
from CrocoDash.data_access import driver as dv
import numpy as np
import xarray as xr
import logging
import dask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
dask.config.set(num_workers=4)

# os.environ["CESMROOT"] = "/glade/u/home/manishrv/work/installs/CROCESM_beta04_clean"
# os.environ["CIME_MACHINE"] = "casper"

@pytest.mark.workflow
def test_full_workflow(tmp_path, get_CrocoDash_case,is_github_actions, dummy_tidal_data, dummy_forcing_factory):

    """Tests if the full CrocoDash workflow runs successfully."""

    if not is_github_actions:
        if os.getenv("CIME_MACHINE") == None and os.getenv("CESMROOT") == None:
            pytest.skip("The test is only to be run if CIME_MACHINE and CESMROOT env vars are set")
        

    result = run_full_workflow(tmp_path, get_CrocoDash_case,dummy_tidal_data,dummy_forcing_factory)
    assert result
    
def run_full_workflow(tmp_path, get_CrocoDash_case,dummy_tidal_data, dummy_forcing_factory):
    """Run the entire CrocoDash workflow (lightly)"""

    logger.info("Running Workflow")

    case = get_CrocoDash_case
    h,u = dummy_tidal_data
    h.to_netcdf(tmp_path/"h.nc")
    u.to_netcdf(tmp_path/"u.nc")

    # Forcing setup
    case.configure_forcings(
    date_range = ["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
    tidal_constituents = ['M2'],
    tpxo_elevation_filepath = tmp_path/"h.nc",
    tpxo_velocity_filepath = tmp_path/"u.nc"
    )

    # Create dummy forcings
    bounds = dv.get_rectangular_segment_info(case.ocn_grid)
    ds = dummy_forcing_factory(bounds["ic"]["lat_min"],bounds["ic"]["lat_max"],bounds["ic"]["lon_min"],bounds["ic"]["lon_max"])
    ds.to_netcdf(case.inputdir / "glorys"/"ic_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"east_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"west_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"north_unprocessed.nc")
    ds.to_netcdf(case.inputdir / "glorys"/"south_unprocessed.nc")

    # Process Forcings   
    case.process_forcings()

    ## Need to figure out how to test a small CESM run here.
    return True

def test_dummy_forcing_data_fixture(dummy_forcing_factory,tmp_path):
    ic = dummy_forcing_factory()
    ic.to_netcdf(tmp_path/"ic_unprocessed.nc")
    assert os.path.exists(tmp_path/"ic_unprocessed.nc")