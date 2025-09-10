from pathlib import Path
from CrocoDash.extract_obc.subset_dataset import subset_dataset
from CrocoDash.extract_obc.parse_dataset import parse_dataset
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info
import xarray as xr


def test_subset_dataset(dummy_forcing_factory, get_rect_grid, tmp_path):

    ds = dummy_forcing_factory(
            0,
            15,
            270,
            300,
        )
    ds.to_netcdf(tmp_path  / "east.thetao.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path  / "west.thetao.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path  / "north.so.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path  / "south.so.20200101.20200102.nc")

    # Generate datasets

    vars = ["so", "thetao"]
    variable_info = parse_dataset(vars, tmp_path, "20200101", "20200131", regex = r"(\d{6,8}).(\d{6,8})")

    grid = get_rect_grid
    boundary_info = get_rectangular_segment_info(grid)
    subset_dataset(
        variable_info=variable_info,
        output_path=tmp_path,
        lat_min=boundary_info["ic"]["lat_min"] - 1,
        lat_max=boundary_info["ic"]["lat_max"] + 1,
        lon_min=boundary_info["ic"]["lon_min"] - 1,
        lon_max=boundary_info["ic"]["lon_max"] + 1,
        lat_name="latitude",
        lon_name="longitude",
        preview=False,
    )
    assert (tmp_path / "so_subset.nc").exists()
    assert (tmp_path / "thetao_subset.nc").exists()
    ds = xr.open_dataset(tmp_path / "so_subset.nc")
    assert ds["latitude"].max() < boundary_info["ic"]["lat_max"] + 2
    assert ds["latitude"].min() > boundary_info["ic"]["lat_min"] - 2
    assert len(ds.time) == 64
