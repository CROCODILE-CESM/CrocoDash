import pytest
import CrocoDash as cd
from pathlib import Path
from CrocoDash.rm6 import regional_mom6 as rmom6
import os


def test_write_config_file(tmp_path):

    expt_name = "cd-sub-glob-fresh-hawaii"

    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]

    date_range = ["2020-01-01 00:00:00", "2020-02-01 00:00:00"]

    ## Place where all your input files go
    input_dir = Path(os.path.join(tmp_path, f"{expt_name}_input/"))

    ## Directory where you'll run the experiment from
    run_dir = Path(os.path.join(tmp_path, f"{expt_name}_run"))
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
        expt_name=expt_name,
    )

    cd.driver.CrocoDashDriver.write_config_file(
        expt,
        path=os.path.join(tmp_path, "cd_config.json"),
    )


def test_read_config_file(tmp_path):
    expt_name = "cd-sub-glob-fresh-hawaii"

    latitude_extent = [16.0, 27]
    longitude_extent = [192, 209]

    date_range = ["2020-01-01 00:00:00", "2020-02-01 00:00:00"]

    ## Place where all your input files go
    input_dir = Path(os.path.join(tmp_path, f"{expt_name}_input/"))

    ## Directory where you'll run the experiment from
    run_dir = Path(os.path.join(tmp_path, f"{expt_name}_run"))
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
        expt_name=expt_name,
    )

    cd.driver.CrocoDashDriver.write_config_file(
        expt,
        path=os.path.join(tmp_path, "cd_config.json"),
    )

    expt = cd.driver.CrocoDashDriver.create_experiment_from_config(
        os.path.join(tmp_path, "cd_config.json")
    )

    assert expt.expt_name == expt_name
