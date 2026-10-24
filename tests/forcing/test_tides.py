from unittest.mock import patch

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.tides import TidesConfigurator


def _make_ctx(tmp_path):
    (tmp_path / "ocn").mkdir()
    return WorkflowContext(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path / "ocn",
        config={},
    )


@patch("regional_mom6.segment.Segment.regrid_tides", autospec=True)
def test_tides_process(mock_regrid_tides, tmp_path, get_rect_grid, dummy_tidal_data):
    """Every boundary gets tides, an interior segment (given as its spec) as
    well as an edge, numbered like the conditions OBC strings that name them."""
    elev, vel = dummy_tidal_data
    get_rect_grid.write_supergrid(tmp_path / "grid.nc")
    elev.to_netcdf(tmp_path / "h.nc")
    vel.to_netcdf(tmp_path / "u.nc")
    strait = {
        "name": "strait",
        "axis": "nxp",
        "index": 11,
        "index_range": None,
        "ocean_side": "west",
    }

    configurator = TidesConfigurator(
        tpxo_elevation_filepath=tmp_path / "h.nc",
        tpxo_velocity_filepath=tmp_path / "u.nc",
        tidal_constituents=["M2"],
        boundaries=["east", strait],
        start_date="2000, 1, 1",
    )
    configurator.process(_make_ctx(tmp_path))

    segments = [call.args[0] for call in mock_regrid_tides.call_args_list]
    assert [s.segment_name for s in segments] == ["segment_001", "segment_002"]
    assert segments[1].to_spec() == {k: v for k, v in strait.items() if k != "name"}
