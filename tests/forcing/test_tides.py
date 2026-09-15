from unittest.mock import patch

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.tides import TidesConfigurator


def _make_ctx(tmp_path, grid, topo, vgrid_path):
    (tmp_path / "ocnice").mkdir()
    ctx = WorkflowContext(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=vgrid_path,
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path / "ocnice",
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
