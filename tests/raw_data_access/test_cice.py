from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from CrocoDash.raw_data_access.datasets import cice_output
from CrocoDash.raw_data_access.region import Region
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


def test_cice_window_on_degree_grid(tmp_path):
    """A MOM6 grid file (ny/nx, degrees, U points at the qlon/qlat corners)
    finds a Gulf of Mexico box on its own values, with each T cell's NE
    corner as its U point, and an Arctic box whose cells fall either side of
    the tripole fold keeps every column of its rows. A CICE grid file in
    radians labelled degrees finds the same Gulf cells."""
    ny, nx = 18, 36
    lon_q, lat_q = np.meshgrid(
        -280.0 + 10 * np.arange(nx + 1), -90.0 + 10 * np.arange(ny + 1)
    )
    tlon, tlat = lon_q[:-1, :-1] + 5, lat_q[:-1, :-1] + 5
    tlat[-1, [8, 9, 26, 27]] = 88.0  # the top row's cells either side of the fold
    east, north = {"units": "degrees_east"}, {"units": "degrees_north"}
    xr.Dataset(
        {
            "tlon": (("ny", "nx"), tlon, east),
            "tlat": (("ny", "nx"), tlat, north),
            "ulon": (("ny", "nxp"), lon_q[:-1], east),
            "ulat": (("ny", "nxp"), tlat[:, [0] * (nx + 1)], north),
            "qlon": (("nyp", "nxp"), lon_q, east),
            "qlat": (("nyp", "nxp"), lat_q, north),
        }
    ).to_netcdf(tmp_path / "grid.nc")
    j, i = np.mgrid[:ny, :nx]
    restart = xr.Dataset({"aicen": (("ncat", "nj", "ni"), [100.0 * j + i])})
    restart.to_netcdf(tmp_path / "restart.nc")

    def subset(region):
        return cice_output.CICE_RESTART.get_cice_restart_subset(
            dates=["2000-01-01", "2000-01-01"],
            region=region,
            buf=0,
            restart_path=tmp_path / "restart.nc",
            grid_path=tmp_path / "grid.nc",
            preview=True,
        )

    gulf = subset(Region(18, 31, -98, -80))
    np.testing.assert_array_equal(gulf.tlat, [[25.0, 25.0]])
    np.testing.assert_array_equal(gulf.tlon, [[-95.0, -85.0]])
    np.testing.assert_array_equal(gulf.aicen, [[[1118.0, 1119.0]]])
    np.testing.assert_array_equal(gulf.ulon, gulf.tlon + 5)
    np.testing.assert_array_equal(gulf.ulat, gulf.tlat + 5)

    arctic = subset(Region(87, 90, -200, 0))
    np.testing.assert_array_equal(arctic.aicen, [[100.0 * (ny - 1) + np.arange(nx)]])

    # A CICE grid file in radians whose tlon/tlat say degrees, as tx2_3v3's do.
    xr.Dataset(
        {
            "tlon": (("nj", "ni"), np.deg2rad(tlon), east),
            "tlat": (("nj", "ni"), np.deg2rad(tlat), north),
            "ulon": (("nj", "ni"), np.deg2rad(lon_q[1:, 1:]), {"units": "radians"}),
            "ulat": (("nj", "ni"), np.deg2rad(lat_q[1:, 1:]), {"units": "radians"}),
        }
    ).to_netcdf(tmp_path / "grid.nc")
    np.testing.assert_array_equal(subset(Region(18, 31, -98, -80)).aicen, gulf.aicen)


def test_get_cice_restart_subset(skip_if_not_glade, tmp_path):
    _skip_if_reference_files_missing()
    paths = cice_output.CICE_RESTART.get_cice_restart_subset(
        dates=["2000-01-01", "2000-01-04"],
        region=Region(18, 31, -98, -80),
        output_folder=tmp_path,
        output_filename="cice_restart_subset.nc",
        restart_path=RESTART_PATH,
        grid_path=GRID_PATH,
    )

    ds = xr.open_dataset(paths[0])
    # A restart is a single static snapshot -- no `time` dimension at all,
    # regardless of the requested date range.
    assert set(ds.sizes) == {"nj", "ni", "ncat"}
    assert ds.sizes["nj"] > 0 and ds.sizes["ni"] > 0
    # No ice expected in the Gulf of Mexico.
    assert float(ds["aicen"].sum()) == 0.0

    # tlon/tlat/ulon/ulat are attached from the grid file, in degrees, over
    # the same window -- used by extract_forcings/cice.py's regrid step.
    for coord_name in ("tlon", "tlat", "ulon", "ulat"):
        assert coord_name in ds.data_vars
        assert ds[coord_name].dims == ("nj", "ni")
    # Window is row-selected (whole nj rows, not per-point), so it covers
    # the requested box but can extend further at high-latitude grid
    # curvature -- just check it covers the request, not a tight bound.
    assert ds["tlat"].values.min() <= 18
    assert ds["tlat"].values.max() >= 31


def test_get_cice_restart_subset_variable_filter(skip_if_not_glade, tmp_path):
    _skip_if_reference_files_missing()
    paths = cice_output.CICE_RESTART.get_cice_restart_subset(
        dates=["2000-01-01", "2000-01-02"],
        region=Region(18, 31, -98, -80),
        output_folder=tmp_path,
        output_filename="cice_restart_subset.nc",
        variables=["aicen", "vicen"],
        restart_path=RESTART_PATH,
        grid_path=GRID_PATH,
    )

    ds = xr.open_dataset(paths[0])
    # tlon/tlat/ulon/ulat are always attached, regardless of the requested
    # variable filter -- downstream regridding always needs them.
    assert set(ds.data_vars) == {"aicen", "vicen", "tlon", "tlat", "ulon", "ulat"}


def test_get_cice_restart_subset_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cice_output.CICE_RESTART.get_cice_restart_subset(
            dates=["2000-01-01", "2000-01-02"],
            region=Region(18, 31, -98, -80),
            output_folder=tmp_path,
            restart_path=str(tmp_path / "does_not_exist.nc"),
            grid_path=GRID_PATH,
        )


def test_cice_restart_registered():
    ProductRegistry.load()
    assert "cice_restart" in ProductRegistry.list_products()
    product = ProductRegistry.get_product("cice_restart")
    assert "get_cice_restart_subset" in product._access_methods
