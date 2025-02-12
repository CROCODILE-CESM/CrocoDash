import pytest
from CrocoDash.grid import Grid
from CrocoDash.topo import Topo
from CrocoDash.vgrid import VGrid
from pathlib import Path
from CrocoDash.case import Case
import os
import numpy as np
from conftest import is_github_actions
#     os.environ["CESMROOT"] = "/Users/manishrv/Documents/CESM/"
#    os.environ["CIME_MACHINE"] = "ubuntu-latest"

@pytest.mark.workflow
@pytest.mark.skipif(not is_github_actions(), reason="Not Github Action, which sets the correct CESM vars")
def test_full_workflow(tmp_path, dummy_tidal_data):

    """Tests if the full CrocoDash workflow runs successfully."""

    # 2. Run the full workflow
    result = run_full_workflow(tmp_path, dummy_tidal_data)
    
    # 3. Verify workflow completion
    assert result["success"], f"Workflow failed: {result["logs"]}"
    
def run_full_workflow(tmp_path, dummy_tidal_data):
    """Run the entire CrocoDash workflow (lightly)"""

    logs = ""
    
    ## Set Up Requirements ##
    os.makedirs(tmp_path/"croc_input", exist_ok=True)
    os.makedirs(tmp_path/"croc_cases", exist_ok=True)
    h,u = dummy_tidal_data
    h.to_netcdf(tmp_path/"h.nc")
    u.to_netcdf(tmp_path/"u.nc")

    # Run Workflow

    # Grid Generation
    grid = Grid(
        resolution = 0.1,
        xstart = 278.0,
        lenx = 1.0,
        ystart = 7.0,
        leny = 1.0,
        name = "panama1",
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
    casename = "panama-1"


    cesmroot = os.getenv("CESMROOT")
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
    case.process_forcings(process_initial_condition = False, process_velocity_tracers=False)

    return {
        "success": True,
        "logs":logs
    }