import pytest
import crocodileregionalruckus as crr
from pathlib import Path
from crocodileregionalruckus.rm6 import regional_mom6 as rmom6


def test_write_config_file():

    expt_name = "crr-sub-glob-fresh-hawaii"

    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]

    date_range = ["2020-01-01 00:00:00", "2020-02-01 00:00:00"]

    ## Place where all your input files go
    input_dir = Path(
        f"/glade/u/home/manishrv/documents/nwa12_0.1/mom_input/{expt_name}/"
    )

    ## Directory where you'll run the experiment from
    run_dir = Path(f"/glade/u/home/manishrv/documents/nwa12_0.1/mom_run/{expt_name}/")
    expt = rmom6.experiment(
        longitude_extent=longitude_extent,
        latitude_extent=latitude_extent,
        date_range=date_range,
        resolution=0.05,
        number_vertical_layers=75,
        layer_thickness_ratio=10,
        depth=4500,
        minimum_depth=25,
        mom_run_dir=run_dir,
        mom_input_dir=input_dir,
        toolpath_dir=Path(""),
        hgrid_type="from_file",  # This is how we incorporate the grid_gen files
        vgrid_type="from_file",
        name=expt_name,
    )

    crr.driver.write_config_file(path="tests/test_config.json")
