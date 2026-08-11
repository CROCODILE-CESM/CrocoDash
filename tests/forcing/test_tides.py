import json
from unittest.mock import patch

import xarray as xr
from regional_mom6.segment import Segment

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.tides import TidesConfigurator


def test_tides_configurator_serializes_custom_segment_boundary():
    """A live Segment boundary (a custom/non-cardinal boundary) isn't
    JSON-serializable itself -- TidesConfigurator must store only its
    boundary_key string, since the full spec is carried separately in
    config.json's conditions.outputs.custom_segments. Regression test for
    the crash this used to hit at json.dump time."""
    dummy = xr.DataArray([0.0], dims=["nx_interior_west"])
    interior = Segment(
        lon=dummy,
        lat=dummy,
        angle=dummy,
        segment_name="interior_west",
        parallel="nx",
        perpendicular="ny",
        axis_to_expand=2,
    )
    configurator = TidesConfigurator(
        tpxo_elevation_filepath="h.nc",
        tpxo_velocity_filepath="u.nc",
        tidal_constituents=["M2"],
        boundaries=["south", interior],
        start_date="2000, 01, 01",
    )
    serialized = configurator.serialize()
    assert serialized["inputs"]["boundaries"] == ["south", "interior_west"]
    json.dumps(serialized)  # must not raise


def _make_ctx(tmp_path, ocn_topo, custom_segments=None):
    (tmp_path / "ocnice").mkdir(exist_ok=True)
    ctx = WorkflowContext(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path / "ocnice",
        config={"conditions": {"outputs": {"custom_segments": custom_segments or {}}}},
    )
    # cached_property allows a plain attribute set to short-circuit the
    # lazy file-based computation.
    ctx.ocn_topo = ocn_topo
    return ctx


@patch("regional_mom6.segment.Segment.regrid_tides", autospec=True)
def test_tides_process(
    mock_regrid_tides, tmp_path, gen_grid_topo_vgrid, dummy_tidal_data
):
    """process() drives Segment directly (Segment.cardinal + regrid_tides) --
    no regional_mom6.experiment involved. The expensive xESMF regrid step
    itself is mocked out; the real tidal-file open/rename/complex-transform
    logic upstream of it still runs for real."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    elev, vel = dummy_tidal_data
    grid.write_supergrid(tmp_path / "grid.nc")
    elev.to_netcdf(tmp_path / "h.nc")
    vel.to_netcdf(tmp_path / "u.nc")

    configurator = TidesConfigurator(
        tpxo_elevation_filepath=tmp_path / "h.nc",
        tpxo_velocity_filepath=tmp_path / "u.nc",
        tidal_constituents=["M2"],
        boundaries=["east"],
        start_date="2000, 1, 1",
    )
    ctx = _make_ctx(tmp_path, topo)

    configurator.process(ctx)

    assert mock_regrid_tides.called


@patch("regional_mom6.segment.Segment.regrid_tides", autospec=True)
def test_tides_process_custom_segment(
    mock_regrid_tides, tmp_path, gen_grid_topo_vgrid, dummy_tidal_data
):
    """A non-cardinal boundary's tides can be processed too: process()
    rebuilds it from a custom_segments spec dict (the same config.json
    round-trip obc.py uses), not just from one of the 4 cardinal strings."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    elev, vel = dummy_tidal_data
    grid.write_supergrid(tmp_path / "grid.nc")
    elev.to_netcdf(tmp_path / "h.nc")
    vel.to_netcdf(tmp_path / "u.nc")

    hgrid = xr.open_dataset(tmp_path / "grid.nc")
    interior = Segment.from_hgrid(
        hgrid,
        axis="nxp",
        index=11,
        segment_name="interior_west",
        topo=topo,
        ocean_side="west",
    )

    configurator = TidesConfigurator(
        tpxo_elevation_filepath=tmp_path / "h.nc",
        tpxo_velocity_filepath=tmp_path / "u.nc",
        tidal_constituents=["M2"],
        boundaries=["interior_west"],
        start_date="2000, 1, 1",
    )
    ctx = _make_ctx(
        tmp_path, topo, custom_segments={"interior_west": interior.to_spec()}
    )

    configurator.process(ctx)

    assert mock_regrid_tides.called
