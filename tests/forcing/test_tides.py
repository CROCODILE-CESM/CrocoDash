from types import SimpleNamespace
from unittest.mock import patch

from ProConPy.config_var import cvars

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.tides import TidesConfigurator


def _make_ctx(tmp_path, grid, topo, vgrid_path):
    (tmp_path / "ocn").mkdir()
    ctx = WorkflowContext(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=vgrid_path,
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path / "ocn",
        config={},
    )
    # Inject the real fixture objects directly rather than round-tripping
    # through real grid/topo files -- cached_property allows a plain
    # attribute set to short-circuit the lazy file-based computation.
    ctx.grid = grid
    ctx.ocn_topo = topo
    return ctx


@patch("regional_mom6.regional_mom6.experiment.setup_boundary_tides", autospec=True)
def test_tides_process(mock_tides, tmp_path, gen_grid_topo_vgrid, dummy_tidal_data):
    grid, topo, vgrid = gen_grid_topo_vgrid
    elev, vel = dummy_tidal_data
    grid.write_supergrid(tmp_path / "grid.nc")
    vgrid_path = tmp_path / "vgrid.nc"
    vgrid.write(vgrid_path)

    configurator = TidesConfigurator(
        tpxo_elevation_filepath=elev,
        tpxo_velocity_filepath=vel,
        tidal_constituents=["M2"],
        boundaries=["east"],
        start_date="2000, 1, 1",
    )
    ctx = _make_ctx(tmp_path, grid, topo, vgrid_path)

    configurator.process(ctx)

    assert mock_tides.called


def test_tides_configure_turns_on_each_requested_constituent(tmp_path, monkeypatch):
    """MOM6 applies interior tidal forcing only at constituents whose
    TIDE_<C> is True, so those must match tidal_constituents."""
    monkeypatch.setitem(cvars, "CASEROOT", SimpleNamespace(value=tmp_path))
    monkeypatch.setitem(cvars, "NINST", SimpleNamespace(value=1))
    (tmp_path / "user_nl_mom").touch()

    TidesConfigurator(
        tpxo_elevation_filepath=tmp_path / "h.nc",
        tpxo_velocity_filepath=tmp_path / "u.nc",
        tidal_constituents=["K1", "O1"],
        boundaries=["east"],
        start_date="2000, 1, 1",
    ).configure()

    mom = (tmp_path / "user_nl_mom").read_text()
    assert "TIDE_K1 = True" in mom
    assert "TIDE_O1 = True" in mom
    assert "TIDE_M2" not in mom
