import pytest
import crocodileregionalruckus as crr
from crocodileregionalruckus import grid_gen as grid_gen
from pathlib import Path


def test_setup_run_dir():
    crr_obj = crr.driver.crr_driver()
    grid_obj = grid_gen.GridGen()
    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]
    resolution = 0.05
    hgrid = grid_obj.create_rectangular_hgrid(
        longitude_extent, latitude_extent, resolution
    )
    vgrid = grid_obj.create_vgrid(75, 10, 4500, minimum_depth=5)
    date_range = ["2020-01-01 00:00:00", "2020-01-02 00:00:00"]
    mom_input_dir = Path("mom_input")
    mom_run_dir = Path("mom_run")
    tidal_constituents = ["M2"]
    crr_obj.setup_run_directory(
        mom_input_dir=mom_input_dir,
        mom_run_dir=mom_run_dir,
        hgrid=hgrid,
        vgrid=vgrid,
        date_range=date_range,
        tidal_constituents=tidal_constituents,
    )
