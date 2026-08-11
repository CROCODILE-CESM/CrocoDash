from functools import partial

import numpy as np
import xarray as xr
from CrocoDash.forcing import mom6, obc
from CrocoDash.raw_data_access.registry import ProductRegistry


def test_build_forcing_request_merges_function_args():
    product_info = {
        "u_var_name": "uo",
        "v_var_name": "vo",
        "eta_var_name": "zos",
        "tracer_var_names": {"temp": "thetao", "salt": "so"},
        "dataset_path": "/some/path",
    }

    variables, extra_args = mom6.build_forcing_request(
        product_info, function_args={"member": 5}
    )

    assert extra_args["dataset_path"] == "/some/path"
    assert extra_args["member"] == 5


def test_regrid_obc_chunk_with_reference_ocean(tmp_path, gen_grid_topo_vgrid):
    """process_obc_conditions runs the real GET + regional_mom6.segment.Segment
    regrid end-to-end against the fast synthetic 'reference_ocean' product --
    no network/campaign-storage access, no GLADE dependency. Confirms
    _regrid_obc_chunk's port to the new Segment class (replacing the old
    rm6.segment(...) factory) still produces valid per-boundary output."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)

    raw_dir = tmp_path / "raw"
    regridded_dir = tmp_path / "regridded"
    output_dir = tmp_path / "output"
    for d in (raw_dir, regridded_dir, output_dir):
        d.mkdir()

    ProductRegistry.load()
    product_info = ProductRegistry.get_product("reference_ocean").write_metadata()

    obc.process_obc_conditions(
        start_date="2020-01-01",
        end_date="2020-01-03",
        boundary_number_conversion={"east": 1, "south": 2},
        product_name="reference_ocean",
        function_name="get_reference_ocean_data",
        variables=None,
        extra_args={},
        dataset_varnames=product_info,
        hgrid_path=str(hgrid_path),
        raw_dataset_path=str(raw_dir),
        regridded_dataset_path=str(regridded_dir),
        output_path=str(output_dir),
        regrid_chunk_fn=mom6._regrid_obc_chunk,
        regrid_step_days=3,
    )

    for seg in ("001", "002"):
        out = output_dir / f"forcing_obc_segment_{seg}.nc"
        assert out.exists()
        ds = xr.open_dataset(out)
        try:
            assert np.isfinite(ds[f"temp_segment_{seg}"].values).all()
        finally:
            ds.close()


def test_regrid_obc_chunk_with_custom_interior_segment(tmp_path, gen_grid_topo_vgrid):
    """A non-cardinal (interior) boundary regrids the same way as a cardinal
    one -- _regrid_obc_chunk's custom_segments kwarg (bound in by
    ConditionsConfigurator.process_bc via functools.partial) rebuilds the
    live Segment from its spec instead of Segment.cardinal."""
    from regional_mom6.segment import Segment

    grid, topo, vgrid = gen_grid_topo_vgrid
    hgrid_path = tmp_path / "hgrid.nc"
    grid.write_supergrid(hgrid_path)
    hgrid = xr.open_dataset(hgrid_path)

    interior = Segment.from_hgrid(
        hgrid,
        axis="nxp",
        index=11,
        segment_name="interior_west",
        topo=topo,
        ocean_side="west",
    )
    custom_segments = {"interior_west": interior.to_spec()}

    raw_dir = tmp_path / "raw"
    regridded_dir = tmp_path / "regridded"
    output_dir = tmp_path / "output"
    for d in (raw_dir, regridded_dir, output_dir):
        d.mkdir()

    ProductRegistry.load()
    product_info = ProductRegistry.get_product("reference_ocean").write_metadata()

    obc.process_obc_conditions(
        start_date="2020-01-01",
        end_date="2020-01-02",
        boundary_number_conversion={"interior_west": 1},
        product_name="reference_ocean",
        function_name="get_reference_ocean_data",
        variables=None,
        extra_args={},
        dataset_varnames=product_info,
        hgrid_path=str(hgrid_path),
        raw_dataset_path=str(raw_dir),
        regridded_dataset_path=str(regridded_dir),
        output_path=str(output_dir),
        regrid_chunk_fn=partial(
            mom6._regrid_obc_chunk, custom_segments=custom_segments
        ),
        custom_segments=custom_segments,
        regrid_step_days=2,
    )

    out = output_dir / "forcing_obc_segment_001.nc"
    assert out.exists()
    ds = xr.open_dataset(out)
    try:
        assert np.isfinite(ds["temp_segment_001"].values).all()
    finally:
        ds.close()
