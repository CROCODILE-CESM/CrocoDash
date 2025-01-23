import pytest 
import CrocoDash
from CrocoDash.case import Case
import os
from pathlib import Path

def file_with_prefix_exists(directory, prefix):
    for filename in os.listdir(directory):
        if filename.startswith(prefix):
            return True
    return False

def test_case_init(gen_grid_topo_vgrid, tmp_path, is_github_actions, get_cesm_root_path, is_glade):

    # Set Grid Info
    grid, topo, vgrid = gen_grid_topo_vgrid

    # Find CESM Root
    cesmroot = "/glade/u/home/manishrv/work/installs/CROCESM_beta04"
    assert cesmroot is not None, "CESMROOT environment variable is not set"

    # Set some defaults
    caseroot, inputdir =  tmp_path/"case", tmp_path/"inputdir"
    project_num = "NCGD0011"
    override = True
    inittime = "1850"
    datm_mode = "JRA"
    datm_grid_name = "TL319"
    ninst = 2
    if is_github_actions:
        machine = "ubuntu-latest"
    elif is_glade:
        machine = "derecho"
    else:
        machine = None

    # Setup Case
    case = Case(
        cesmroot = cesmroot,
        caseroot = caseroot,
        inputdir = inputdir,
        ocn_grid = grid,
        ocn_vgrid = vgrid,
        ocn_topo = topo,
        project = project_num,
        override = override,
        machine = machine,
        inittime = inittime,
        datm_mode = datm_mode,
        datm_grid_name=datm_grid_name,
        ninst = ninst
    )

    # Check some basics
    assert case is not None
    assert os.path.exists(caseroot)
    assert os.path.exists(inputdir)
    assert case.ninst == ninst
    assert file_with_prefix_exists(inputdir/"ocnice", "ocean_hgrid")
    assert file_with_prefix_exists(caseroot,"README")

def test_init_arg_check():
    """
    For now, this check just triggers all of the stated exceptions coded up. In the future, we may want to be a little more methodological about these
    """
    Case._init_args_check(None,)
    return

def test_create_grid_input():
    return

def test_create_newcase():
    return

def test_configure_forcings():
    return

def test_process_forcing():
    return

def test_initialize_vcg():
    return

def test_assign_configvar_values():
    return

def test_update_forcing_variables():
    return
