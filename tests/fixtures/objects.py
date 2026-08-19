import os
import pytest
import shutil
from CrocoDash.rm6 import regional_mom6 as rm6
from CrocoDash.case import Case
from pathlib import Path
from uuid import uuid4

# Forcing configuration shared by ported_case and the fast fixtures that stand in for
# it. Kept in one place so a copy of the ported case and a freshly configured fast case
# describe the same experiment, and a test can move between them without its
# assertions changing.
FORCING_ARGS = {
    "date_range": ["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
    "boundaries": ["north", "east"],
    # Tides are configured here so that a copy of the ported case satisfies the tests
    # that assert on a tidal forcing configuration, without needing a case of its own.
    "tidal_constituents": ["M2"],
    "tpxo_elevation_filepath": "s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
    "tpxo_velocity_filepath": "s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
}


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


@pytest.fixture(scope="session")
def get_case_with_cf(CrocoDash_case_factory, tmp_path_factory):
    """A configured (not created) case with forcings. See CrocoDash_case_factory."""
    case = CrocoDash_case_factory(tmp_path_factory.mktemp(f"case-{uuid4().hex}"))
    case.configure_forcings(**FORCING_ARGS)
    return case


@pytest.fixture(scope="session")
def get_CrocoDash_case(CrocoDash_case_factory, tmp_path_factory):
    """A configured (not created) case with no forcings. See CrocoDash_case_factory."""
    return CrocoDash_case_factory(tmp_path_factory.mktemp(f"case-{uuid4().hex}"))


@pytest.fixture
def get_mutable_CrocoDash_case(CrocoDash_case_factory, tmp_path):
    """A configured (not created) case a single test may mutate freely.

    Function-scoped, unlike the session-scoped fixtures above: for tests that call
    configure_forcings() themselves, which rewrites case state and wipes the
    extract_forcings directory, so sharing one across tests makes them order-dependent.
    """
    return CrocoDash_case_factory(tmp_path / f"case-{uuid4().hex}")


@pytest.fixture(scope="session")
def ported_case(CrocoDash_case_factory, tmp_path_factory):
    """The one case in the suite that really runs CIME.

    create_newcase plus case.setup dominates the cost of building a case (seconds
    each, against a small fraction of that for everything else Case.__init__ does), so
    every other fixture here configures its case without executing CIME
    (do_exec=False) and anything that needs the artifacts only CIME writes -- the
    xmlquery/xmlchange scripts, env_*.xml, the default user_nl files, SourceMods/,
    README.case -- shares this one instead of paying for its own.

    Treat it as read-only: a test that mutates the caseroot, or writes into the
    inputdir, must take a copy via ported_case_copy instead.
    """
    case = CrocoDash_case_factory(tmp_path_factory.mktemp("ported-case"), do_exec=True)
    case.configure_forcings(**FORCING_ARGS)
    return case


def _rewrite_paths(root, replacements):
    """Substitute absolute paths inside the text files of a copied case.

    A copied case still names the original everywhere the original wrote its own path,
    and those references are load-bearing rather than cosmetic:

    - CIME resolves ./xmlchange's replay log against CASEROOT in env_case.xml, so an
      xmlchange in an unrewritten copy appends to the *original* case's replay.sh --
      the copy never records it, and the case every other test reads gets polluted.
    - CaseBundle.bundle() locates the ocnice directory from user_nl_mom's INPUTDIR
      line, so a copy given its own inputdir would still bundle the original's files.

    Symlinks are skipped and symlinked directories are never descended into: a
    caseroot's ./xmlquery and Tools/ point into CESM itself, and writing through them
    would edit the CESM installation.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not Path(dirpath, d).is_symlink()]
        for filename in filenames:
            path = Path(dirpath, filename)
            if path.is_symlink():
                continue
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue  # binary (or unreadable) file, nothing to rewrite
            rewritten = text
            for old, new in replacements:
                rewritten = rewritten.replace(str(old), str(new))
            if rewritten != text:
                path.write_text(rewritten)


@pytest.fixture
def ported_case_copy(ported_case, tmp_path_factory):
    """Factory for throwaway copies of ported_case, returning the copied caseroot.

    A copied caseroot stays a working CIME case -- ./xmlquery and ./xmlchange
    --non-local read and write the copy's own env_*.xml -- so a mutating test gets full
    isolation for the price of a directory copy rather than a second create_newcase,
    once the paths the original baked into itself are rewritten (see _rewrite_paths).

    Pass with_inputdir=True when the test also writes into the case's inputdir, so
    those writes don't land in the inputdir every other ported_case test reads.
    """

    def _copy(name="copy", with_inputdir=False):
        root = tmp_path_factory.mktemp(f"ported-copy-{name}")
        caseroot = root / "case"
        shutil.copytree(ported_case.caseroot, caseroot, symlinks=True)
        replacements = [(ported_case.caseroot, caseroot)]
        if with_inputdir:
            inputdir = root / "inputdir"
            # symlinks=True: ocnice/rundir links into the case's run directory, which
            # links back to inputdir, so following symlinks recurses forever.
            shutil.copytree(ported_case.inputdir, inputdir, symlinks=True)
            replacements.append((ported_case.inputdir, inputdir))
            # Only extract_forcings holds paths; the rest of inputdir is NetCDF.
            _rewrite_paths(inputdir / "extract_forcings", replacements)
        _rewrite_paths(caseroot, replacements)
        return caseroot

    return _copy


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
        do_exec: bool = False,
    ):
        """
        Factory function to create a CrocoDash Case object with sensible defaults.
        Can be called from pytest fixtures or standalone scripts.

        do_exec defaults to False, so the case is configured but CIME is never invoked:
        no create_newcase, no case.setup, no xmlchange, no user_nl writes. Grid input
        files, the state file, and the forcing configuration are all still produced,
        which is everything most tests actually assert on, and it is roughly an order
        of magnitude faster. Pass do_exec=True only for a case that must carry real
        CIME artifacts -- and prefer the ported_case fixture, which already provides
        one, over creating another.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
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
            do_exec=do_exec,
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


@pytest.fixture
def fake_forcing_product():
    class DummyForcingProduct:
        cf_calendar = "noleap"

    return DummyForcingProduct()
