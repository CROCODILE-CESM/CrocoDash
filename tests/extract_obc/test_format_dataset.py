from pathlib import Path
from CrocoDash.extract_obc.subset_dataset import subset_dataset
from CrocoDash.extract_obc.parse_dataset import parse_dataset
from CrocoDash.extract_obc.regrid_dataset import regrid_dataset_to_boundaries
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info
from CrocoDash.extract_obc.format_dataset import format_dataset
import xarray as xr


def test_format_dataset(dummy_forcing_factory, get_rect_grid, tmp_path, get_vgrid):
    vgrid = get_vgrid
    vgrid.write(tmp_path / "vgrid.nc")
    vgrid = xr.open_dataset(tmp_path / "vgrid.nc")
    ds = dummy_forcing_factory(
        0,
        15,
        270,
        300,
    )
    ds.to_netcdf(tmp_path / "east.thetao.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path / "west.thetao.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path / "north.so.20200101.20200102.nc")
    ds["time"] = ds.time + 32
    ds.to_netcdf(tmp_path / "south.so.20200101.20200102.nc")

    vars = ["so", "thetao"]
    variable_info = parse_dataset(
        vars, tmp_path, "20200101", "20200131", regex=r"(\d{6,8}).(\d{6,8})"
    )

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
    grid.write_supergrid(tmp_path / "supergrid.nc")
    supergrid = xr.open_dataset(tmp_path / "supergrid.nc")
    paths = regrid_dataset_to_boundaries(
        input_path=tmp_path,
        output_path=tmp_path,
        supergrid=supergrid,
        variable_info=variable_info,
        lat_name="latitude",
        lon_name="longitude",
        preview=False,
    )

    paths = format_dataset(
        input_path=tmp_path,
        output_path=tmp_path,
        supergrid=supergrid,
        vgrid=vgrid,
        bathymetry=None,
        variable_info=variable_info,
        lat_name="lat",
        lon_name="lon",
        z_dim="depth",
    )
