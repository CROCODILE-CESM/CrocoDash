import pytest
from CrocoDash.rm6 import regional_mom6 as rm6
from CrocoDash.case import Case
from pathlib import Path
from uuid import uuid4


@pytest.fixture
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
def get_case_with_cf(CrocoDash_case_factory, tmp_path_factory):
    case = CrocoDash_case_factory(tmp_path_factory.mktemp("case"))
    case.configure_forcings(date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"])
    return case


@pytest.fixture
def get_CrocoDash_case(
    tmp_path_factory,
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
    caseroot = tmp_path_factory.mktemp(f"case-{uuid4().hex}")
    inputdir = tmp_path_factory.mktemp(f"inputdir-{uuid4().hex}")
    project_num = "NCGD0011"
    override = True
    compset = "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    atm_grid_name = "TL319"
    ninst = 1
    glade_bool = is_glade_file_system

    if is_github_actions:
        machine = "ubuntu-latest"
    elif glade_bool:
        machine = "derecho"
    else:
        machine = "homebrew"

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
        ninst=ninst,
    )
    return case


@pytest.fixture(scope="session")
def CrocoDash_case_factory(
    gen_grid_topo_vgrid,
    is_github_actions,
    get_cesm_root_path,
    is_glade_file_system,
):
    cesmroot = get_cesm_root_path
    project_num = "NCGD0011"
    override = True
    ninst = 1

    def _CrocoDash_case_factory(
        directory,
        configure_forcings=False,
        compset: str = "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV",
        atm_grid_name: str = "TL319",
    ):
        """
        Factory function to create a CrocoDash Case object with sensible defaults.
        Can be called from pytest fixtures or standalone scripts.
        """
        directory = Path(directory)
        directory.mkdir(exist_ok=True)
        # Set Grid Info
        grid, topo, vgrid = gen_grid_topo_vgrid

        # Set paths
        caseroot = directory / f"case-{uuid4().hex}"
        inputdir = directory / "inputdir"

        # Decide machine
        if is_github_actions:
            machine = "ubuntu-latest"
        elif is_glade_file_system:
            machine = "derecho"
        else:
            machine = "homebrew"

        # Create the case
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
            ninst=ninst,
        )
        if configure_forcings:
            case.configure_forcings(
                date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"]
            )
        return case

    return _CrocoDash_case_factory


@pytest.fixture
def fake_cime():
    class DummyCaseCIME:
        def get_mesh_path(self, comp, grid):
            return f"/dummy/meshes/{comp}/{grid}"

    return DummyCaseCIME()
