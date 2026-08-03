from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from CrocoDash.raw_data_access.datasets import cice
from CrocoDash.raw_data_access.registry import ProductRegistry

GRID_PATH = "/glade/campaign/cesm/community/omwg/grids/tx2_3v3_grid.nc"
RESTART_PATH = (
    "/glade/u/home/dbailey/"
    "b.e30_alpha09b.B1850C_MTso.ne30_t233_wgx3.360.cice.r.0201-01-01-00000.nc"
)


def _skip_if_reference_files_missing():
    if not Path(GRID_PATH).exists() or not Path(RESTART_PATH).exists():
        pytest.skip(
            "Reference tx2_3v3 grid or CICE restart file not available on this "
            "filesystem."
        )


def test_find_cice_index_window_gulf_of_mexico(skip_if_not_glade):
    _skip_if_reference_files_missing()
    ni_idx, nj_min, nj_max = cice.find_cice_index_window(
        GRID_PATH, lat_min=18, lat_max=31, lon_min=-98, lon_max=-80
    )

    assert np.all(np.diff(np.sort(ni_idx)) == 1), "ni window should be contiguous"

    grid = xr.open_dataset(GRID_PATH)
    tlat = np.rad2deg(grid["tlat"].values)
    tlon = np.rad2deg(grid["tlon"].values)
    sub_tlat = tlat[nj_min : nj_max + 1][:, ni_idx]
    sub_tlon = tlon[nj_min : nj_max + 1][:, ni_idx]

    # Window should cover the requested box (with buffer) and not run away.
    assert sub_tlat.min() <= 18 <= sub_tlat.max()
    assert sub_tlat.min() <= 31 <= sub_tlat.max()
    assert sub_tlon.min() <= -98 <= sub_tlon.max()
    assert sub_tlon.min() <= -80 <= sub_tlon.max()
    assert sub_tlat.max() - sub_tlat.min() < 20
    assert sub_tlon.max() - sub_tlon.min() < 30


def test_find_cice_index_window_out_of_bounds_raises(skip_if_not_glade):
    _skip_if_reference_files_missing()
    with pytest.raises(ValueError):
        cice.find_cice_index_window(
            GRID_PATH, lat_min=1000, lat_max=1001, lon_min=0, lon_max=1
        )


def test_get_cice_restart_subset(skip_if_not_glade, tmp_path):
    _skip_if_reference_files_missing()
    paths = cice.CICE_RESTART.get_cice_restart_subset(
        dates=["2000-01-01", "2000-01-02"],
        lat_min=18,
        lat_max=31,
        lon_min=-98,
        lon_max=-80,
        output_folder=tmp_path,
        output_filename="cice_restart_subset.nc",
        restart_path=RESTART_PATH,
        grid_path=GRID_PATH,
    )

    ds = xr.open_dataset(paths[0])
    assert set(ds.sizes) == {"nj", "ni", "ncat"}
    assert ds.sizes["nj"] > 0 and ds.sizes["ni"] > 0
    # No ice expected in the Gulf of Mexico.
    assert float(ds["aicen"].sum()) == 0.0


def test_get_cice_restart_subset_variable_filter(skip_if_not_glade, tmp_path):
    _skip_if_reference_files_missing()
    paths = cice.CICE_RESTART.get_cice_restart_subset(
        dates=["2000-01-01", "2000-01-02"],
        lat_min=18,
        lat_max=31,
        lon_min=-98,
        lon_max=-80,
        output_folder=tmp_path,
        output_filename="cice_restart_subset.nc",
        variables=["aicen", "vicen"],
        restart_path=RESTART_PATH,
        grid_path=GRID_PATH,
    )

    ds = xr.open_dataset(paths[0])
    assert set(ds.data_vars) == {"aicen", "vicen"}


def test_get_cice_restart_subset_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cice.CICE_RESTART.get_cice_restart_subset(
            dates=["2000-01-01", "2000-01-02"],
            lat_min=18,
            lat_max=31,
            lon_min=-98,
            lon_max=-80,
            output_folder=tmp_path,
            restart_path=str(tmp_path / "does_not_exist.nc"),
            grid_path=GRID_PATH,
        )


def test_cice_restart_registered():
    ProductRegistry.load()
    assert "cice_restart" in ProductRegistry.list_products()
    product = ProductRegistry.get_product("cice_restart")
    assert "get_cice_restart_subset" in product._access_methods
