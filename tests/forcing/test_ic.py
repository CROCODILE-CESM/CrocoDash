import numpy as np
import pytest
import xarray as xr
from pathlib import Path

import CrocoDash.forcing.ic as ic_module
from CrocoDash.grid import Grid
from CrocoDash.raw_data_access.region import Region
from CrocoDash.raw_data_access.time_request import TimeRequest


@pytest.fixture
def ic_kwargs(tmp_path, get_rect_grid):
    get_rect_grid.write_supergrid(tmp_path / "hgrid.nc")
    # raw/ and out/ are deliberately absent -- the engine creates them itself.
    return dict(
        product_name="glorys",
        function_name="get_glorys_data_from_rda",
        variables=["thetao", "so"],
        extra_args={"dataset_path": "/some/path"},
        dataset_varnames={"tracer_var_names": {"temp": "thetao"}},
        when=TimeRequest("2020-01-01", "2020-01-01"),
        hgrid_path=str(tmp_path / "hgrid.nc"),
        raw_data_dir=str(tmp_path / "raw"),
        output_data_dir=str(tmp_path / "out"),
    )


def test_process_initial_condition_downloads_then_regrids(
    ic_kwargs, get_rect_grid, monkeypatch
):
    """IC is a single t=0 snapshot: GET asks for the start day over the
    whole-domain box, then hands the file to the caller's regrid_fn."""
    calls, regridded = [], {}

    def access_fn(**kw):
        calls.append(kw)
        out = Path(kw["output_folder"]) / kw["output_filename"]
        xr.Dataset({"thetao": ("x", np.zeros(3))}).to_netcdf(out)

    access_fn._how_to_use = "needs a Copernicus account"
    monkeypatch.setattr(
        ic_module.utils, "get_data_access_function", lambda *a: access_fn
    )

    ic_module.process_initial_condition(
        **ic_kwargs, regrid_fn=lambda **kw: regridded.update(kw)
    )

    (call,) = calls
    assert call["when"] == ic_kwargs["when"]
    assert call["dataset_path"] == "/some/path"  # extra_args splatted, not nested
    bbox = Grid.get_bounding_boxes(get_rect_grid)["ic"]
    # The whole-domain box as a Region. get_bounding_boxes's
    # crosses_antimeridian isn't passed on: a box across 180E already ends
    # past 180.
    assert call["region"] == Region(
        bbox["lat_min"], bbox["lat_max"], bbox["lon_min"], bbox["lon_max"]
    )
    # netCDF4 reports a missing parent dir as a bare EACCES, so the engine has
    # to have made both dirs before writing into them.
    assert (
        regridded["raw_file"] == Path(ic_kwargs["raw_data_dir"]) / "ic_unprocessed.nc"
    )
    assert regridded["raw_file"].exists()
    assert regridded["output_dir"] == Path(ic_kwargs["output_data_dir"])
    assert regridded["when"] == ic_kwargs["when"]
