import CrocoDash as crr
from CrocoDash import driver
from CrocoDash.rm6 import regional_mom6 as rm6
import pytest
from pathlib import Path
import json
import shutil
import os


def test_driver_init_basic():
    """
    This test confirms we can import crr driver, and generate a CrocoDashDriver object which includes grid_gen, regional_mom6, and regional_casegen objects.
    """

    crr_driver_obj = driver.CrocoDashDriver()
    assert crr_driver_obj is not None
    assert crr_driver_obj.empty_expt_obj is not None
    assert crr_driver_obj.grid_gen_obj is not None
    assert crr_driver_obj.rcg_obj is not None


def test_driver_init_rm6_args():
    """
    This test confirms we can pass Regional-MOM6 arguments into the Regional MOM6 empty_expt_obj
    """

    crr_driver_obj = driver.CrocoDashDriver(
        expt_name="test_args", hgrid_type="test_hgrid_type"
    )
    assert crr_driver_obj.empty_expt_obj.expt_name == "test_args"
    assert crr_driver_obj.empty_expt_obj.hgrid_type == "test_hgrid_type"


def test_driver_init_rm6_args_fails():
    """
    This test confirms that we can't pass bogus arguments into the Regional MOM6 empty_expt_obj
    """
    with pytest.raises(TypeError):
        driver.CrocoDashDriver(expt_name_bogus_args="test_args")


def test_driver_write_config_file_basic(tmp_path, setup_sample_rm6_expt):
    """
    This test confirms we can write a Regional MOM6 experiment configuration file. There is a lot of overhead to creating ane experiment object, so we'll use our given dummy data.
    """
    # Create a dummy expt object

    expt = setup_sample_rm6_expt

    # Write the configuration file
    config_file = driver.CrocoDashDriver.write_config_file(
        expt, tmp_path / "test_light_config_file.json"
    )

    with open(tmp_path / "test_light_config_file.json", "r") as written_config:
        written_config_dict = json.load(written_config)

    assert written_config_dict["expt_name"] == expt.expt_name
    assert written_config_dict["longitude_extent"] == list(expt.longitude_extent)
    assert written_config_dict["latitude_extent"] == list(expt.latitude_extent)
    assert written_config_dict["date_range"] == [
        str(expt.date_range[0]),
        str(expt.date_range[1]),
    ]
    assert written_config_dict["resolution"] == expt.resolution
    assert written_config_dict["number_vertical_layers"] == expt.number_vertical_layers
    assert written_config_dict["layer_thickness_ratio"] == expt.layer_thickness_ratio
    assert written_config_dict["depth"] == expt.depth
    assert written_config_dict["minimum_depth"] == expt.minimum_depth
    assert written_config_dict["tidal_constituents"] == expt.tidal_constituents
    assert written_config_dict["boundaries"] == expt.boundaries
    assert written_config_dict["hgrid_type"] == expt.hgrid_type


def test_driver_read_config_file_basic(tmp_path, setup_sample_rm6_expt):
    """
    This test confirms we can write a Regional MOM6 experiment configuration file. There is a lot of overhead to creating ane experiment object, so we'll use our given dummy data.
    """

    # Create a dummy expt object

    expt = setup_sample_rm6_expt
    # Write the configuration file
    config_file = driver.CrocoDashDriver.write_config_file(
        expt, tmp_path / "test_light_config_file.json"
    )
    # Read the configuration file
    config_expt = driver.CrocoDashDriver.create_experiment_from_config(
        tmp_path / "test_light_config_file.json"
    )
    assert str(config_expt) == str(expt)


def test_driver_read_config_file_copy(setup_sample_rm6_expt, tmp_path_factory):
    """
    This test confirms we can write a Regional MOM6 experiment configuration file. There is a lot of overhead to creating ane experiment object, so we'll use our given dummy data.
    """
    expt = setup_sample_rm6_expt
    fake_input_folder = tmp_path_factory.mktemp("fake_input_folder")
    fake_run_folder = tmp_path_factory.mktemp("fake_run_folder")
    fake_json_folder = tmp_path_factory.mktemp("fake_json_folder")
    fake_json_path = fake_json_folder / "test_light_config_file.json"
    tmp_path = tmp_path_factory.mktemp("tmp_path")
    # Write the configuration file
    config_file = driver.CrocoDashDriver.write_config_file(
        expt, tmp_path / "test_light_config_file.json"
    )
    shutil.copy(tmp_path / "test_light_config_file.json", fake_json_path)

    # Step 2: Read the copied JSON file as a dictionary
    with open(fake_json_path, "r") as file:
        config = json.load(file)  # This reads the JSON into a Python dictionary

    old_mom_input_dir = config["mom_input_dir"]
    old_mom_run_dir = config["mom_run_dir"]
    config["mom_input_dir"] = str(fake_input_folder)
    config["mom_run_dir"] = str(fake_run_folder)
    # Step 3: Write the modified dictionary back to the JSON file
    with open(fake_json_path, "w") as file:
        json.dump(config, file)

    # Write the configuration file
    config_expt = driver.CrocoDashDriver.create_experiment_from_config(fake_json_path)
    assert_directories_equal(old_mom_input_dir, fake_input_folder)
    assert_directories_equal(old_mom_run_dir, fake_run_folder)


def assert_directories_equal(dir1, dir2):
    # Walk both directories and collect file paths relative to the root
    dir1_files = {
        os.path.relpath(os.path.join(root, file), dir1)
        for root, _, files in os.walk(dir1)
        for file in files
    }
    dir2_files = {
        os.path.relpath(os.path.join(root, file), dir2)
        for root, _, files in os.walk(dir2)
        for file in files
    }

    # Assert that the sets of files in both directories are identical
    assert dir1_files == dir2_files
