from pathlib import Path
from CrocoDash.extract_obc.subset_dataset import subset_dataset
from CrocoDash.extract_obc.parse_dataset import parse_dataset
from CrocoDash.extract_obc.regrid_dataset import regrid_dataset_to_boundaries
from CrocoDash.raw_data_access.driver import get_rectangular_segment_info
import xarray as xr


def test_regrid_dataset_to_boundaries(skip_if_not_glade, get_rect_grid, tmp_path):
    sample_ds_path = Path(
        "/glade/campaign/collections/cmip/CMIP6/CESM-HR/FOSI_BGC/HR/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001/ocn/proc/tseries/month_1"
    )
    vars = ["DIC", "DOC"]
    variable_info = parse_dataset(vars, sample_ds_path)
    variable_info["DIC"] = variable_info["DIC"][:2]
    variable_info["DOC"] = variable_info["DOC"][:2]
    grid = get_rect_grid
    boundary_info = get_rectangular_segment_info(grid)
    paths = subset_dataset(
        variable_info=variable_info,
        output_path=tmp_path,
        lat_min=boundary_info["ic"]["lat_min"] - 1,
        lat_max=boundary_info["ic"]["lat_max"] + 1,
        lon_min=boundary_info["ic"]["lon_min"] - 1,
        lon_max=boundary_info["ic"]["lon_max"] + 1,
        lat_name="TLAT",
        lon_name="TLONG",
        preview=False,
    )
    grid.write_supergrid(tmp_path / "supergrid.nc")
    supergrid = xr.open_dataset(tmp_path / "supergrid.nc")
    paths = regrid_dataset_to_boundaries(
        input_path=tmp_path,
        output_path=tmp_path,
        supergrid=supergrid,
        variable_info=variable_info,
        lat_name="TLAT",
        lon_name="TLONG",
        preview=True,
    )
    assert len(paths) == 10
