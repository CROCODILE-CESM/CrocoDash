import pytest
import CrocoDash
from CrocoDash.case import Case
import os
from pathlib import Path
import regional_mom6 as rmom6
import datetime as dt
from conftest import is_glade_file_system

def file_with_prefix_exists(directory, prefix):
    for filename in os.listdir(directory):
        if filename.startswith(prefix):
            return True
    return False


def test_case_init(
    gen_grid_topo_vgrid, tmp_path, is_github_actions, get_cesm_root_path
):

    # Set Grid Info
    grid, topo, vgrid = gen_grid_topo_vgrid

    # Find CESM Root
    cesmroot = get_cesm_root_path
    assert cesmroot is not None, "CESMROOT environment variable is not set"

    # Set some defaults
    caseroot, inputdir = tmp_path / "case", tmp_path / "inputdir"
    project_num = "NCGD0011"
    override = True
    inittime = "1850"
    datm_mode = "JRA"
    datm_grid_name = "TL319"
    ninst = 2
    if is_github_actions:
        machine = "ubuntu-latest"
    elif is_glade_file_system():
        machine = "derecho"
    else:
        machine = None

    # Setup Case
    case = Case(
        cesmroot=cesmroot,
        caseroot=caseroot,
        inputdir=inputdir,
        ocn_grid=grid,
        ocn_vgrid=vgrid,
        ocn_topo=topo,
        project=project_num,
        override=override,
        machine=machine,
        inittime=inittime,
        datm_mode=datm_mode,
        datm_grid_name=datm_grid_name,
        ninst=ninst,
    )

    # Check some basics
    assert case is not None
    assert os.path.exists(caseroot)
    assert os.path.exists(inputdir)
    assert case.ninst == ninst
    assert file_with_prefix_exists(inputdir / "ocnice", "ocean_hgrid")
    assert file_with_prefix_exists(caseroot, "README")


def test_create_grid_input(get_CrocoDash_case):
    case = get_CrocoDash_case
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_hgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_topog_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_vgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"scrip_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ESMF_mesh_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    if "CICE" in case.compset:
        files = [
            f
            for f in os.listdir(case.inputdir / "ocnice")
            if f.startswith(f"cice_grid_{case.ocn_grid.name}")
        ]
        assert len(files) > 0


def test_configure_forcings(get_CrocoDash_case, tmp_path):
    """
    Test that the setup for the forcings works
    """
    case = get_CrocoDash_case
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath=tmp_path,
        tpxo_velocity_filepath=tmp_path,
        boundaries=["north", "south", "east"],
    )

    assert case.expt.date_range[0].year == 2020
    assert case.tidal_constituents == ["M2"]
    assert case.boundaries == ["north", "south", "east"]

    return


def test_process_forcing(get_CrocoDash_case, tmp_path):
    """
    Test that the setup for the forcings works
    """
    case = get_CrocoDash_case
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath=tmp_path,
        tpxo_velocity_filepath=tmp_path,
        boundaries=["north"],
    )
    path = case.inputdir / "glorys"
    filenames = ["ic_unprocessed.nc", "north_unprocessed.nc"]
    for name in filenames:
        with open(path / name, "w") as file:
            pass
    with pytest.raises(ValueError):
        case.process_forcings()


def test_update_forcing_variables(get_CrocoDash_case):
    case = get_CrocoDash_case

    search_string = "OBC_NUMBER_OF_SEGMENTS"
    found_user_nl_mom_adjusted_var = False
    case.tidal_constituents = ["M2"]
    case.expt = rmom6.experiment.create_empty(
        boundaries=[],
        date_range=[
            dt.datetime.strptime("2020-01-01", "%Y-%m-%d"),
            dt.datetime.strptime("2020-02-01", "%Y-%m-%d"),
        ],
    )
    case.date_range
    case.boundaries = []
    case._update_forcing_variables()
    with open(case.caseroot / "user_nl_mom_0001", "r", encoding="utf-8") as file:
        for line in file:
            if search_string in line:
                found_user_nl_mom_adjusted_var = True
                break
    return found_user_nl_mom_adjusted_var
