import pytest
from CrocoDash.rm6 import regional_mom6 as rm6
from CrocoDash.case import Case


@pytest.fixture(scope="session")
def setup_sample_rm6_expt(tmp_path):
    expt = rm6.experiment(
        longitude_extent=[10, 12],
        latitude_extent=[10, 12],
        date_range=["2000-01-01 00:00:00", "2000-01-01 00:00:00"],
        resolution=0.05,
        number_vertical_layers=75,
        layer_thickness_ratio=10,
        depth=4500,
        minimum_depth=25,
        mom_run_dir=tmp_path / "light_rm6_run",
        mom_input_dir=tmp_path / "light_rm6_input",
        toolpath_dir=Path(""),
        hgrid_type="even_spacing",
        vgrid_type="hyperbolic_tangent",
        expt_name="test",
    )
    return expt


@pytest.fixture
def get_CrocoDash_case(
    tmp_path,
    gen_grid_topo_vgrid,
    is_github_actions,
    get_cesm_root_path,
    is_glade_file_system,
):
    # Set Grid Info
    grid, topo, vgrid = gen_grid_topo_vgrid

    # Find CESM Root
    cesmroot = get_cesm_root_path

    # Set some defaults
    caseroot, inputdir = tmp_path / "case", tmp_path / "inputdir"
    project_num = "NCGD0011"
    override = True
    compset = "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    datm_grid_name = "TL319"
    ninst = 2
    glade_bool = is_glade_file_system

    if is_github_actions:
        machine = "ubuntu-latest"
    elif glade_bool:
        machine = "derecho"
    else:
        machine = None

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
        datm_grid_name=datm_grid_name,
        ninst=ninst,
    )
    return case
