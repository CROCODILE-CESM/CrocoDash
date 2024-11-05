import crocodileregionalruckus as crr
from crocodileregionalruckus import driver
from crocodileregionalruckus.rm6 import regional_mom6 as rm6
import pytest
from pathlib import Path
import json
import shutil
import os


def test_driver_init_basic():
    """
    This test confirms we can import crr driver, and generate a CRRDriver object which includes grid_gen, regional_mom6, and regional_casegen objects.
    """

    crr_driver_obj = driver.CRRDriver()
    assert crr_driver_obj is not None
    assert crr_driver_obj.empty_expt_obj is not None
    assert crr_driver_obj.grid_gen_obj is not None
    assert crr_driver_obj.rcg_obj is not None


def test_driver_init_rm6_args():
    """
    This test confirms we can pass Regional-MOM6 arguments into the Regional MOM6 empty_expt_obj
    """

    crr_driver_obj = driver.CRRDriver(
        expt_name="test_args", hgrid_type="test_hgrid_type"
    )
    assert crr_driver_obj.empty_expt_obj.expt_name == "test_args"
    assert crr_driver_obj.empty_expt_obj.hgrid_type == "test_hgrid_type"


def test_driver_init_rm6_args_fails():
    """
    This test confirms that we can't pass bogus arguments into the Regional MOM6 empty_expt_obj
    """
    with pytest.raises(TypeError):
        driver.CRRDriver(expt_name_bogus_args="test_args")


def test_driver_write_config_file_basic(get_dummy_data_folder, tmp_path):
    """
    This test confirms we can write a Regional MOM6 experiment configuration file. There is a lot of overhead to creating ane experiment object, so we'll use our given dummy data.
    """
    dummy_data_folder = get_dummy_data_folder

    # Create a dummy expt object

    expt = rm6.experiment(
        longitude_extent=[10, 12],
        latitude_extent=[10, 12],
        date_range=["2000-01-01 00:00:00", "2000-01-01 00:00:00"],
        resolution=0.05,
        number_vertical_layers=75,
        layer_thickness_ratio=10,
        depth=4500,
        minimum_depth=25,
        mom_run_dir=dummy_data_folder + "/light_rm6_run",
        mom_input_dir=dummy_data_folder + "/light_rm6_input",
        toolpath_dir=Path(""),
        hgrid_type="from_file",  # This is how we incorporate the grid_gen files
        vgrid_type="from_file",
        expt_name="test",
    )

    # Write the configuration file
    config_file = driver.CRRDriver.write_config_file(
        expt, tmp_path / "test_light_config_file.json"
    )
    with open(tmp_path / "test_light_config_file.json", "r") as written_config:
        written_config_dict = json.load(written_config)
    with open(
        dummy_data_folder + "/test_light_config_file.json", "r"
    ) as correct_config:
        correct_config_dict = json.load(correct_config)
    assert written_config_dict == correct_config_dict


def test_driver_read_config_file_basic(get_dummy_data_folder):
    """
    This test confirms we can write a Regional MOM6 experiment configuration file. There is a lot of overhead to creating ane experiment object, so we'll use our given dummy data.
    """
    dummy_data_folder = get_dummy_data_folder

    # Create a dummy expt object

    expt = rm6.experiment(
        longitude_extent=[10, 12],
        latitude_extent=[10, 12],
        date_range=["2000-01-01 00:00:00", "2000-01-01 00:00:00"],
        resolution=0.05,
        number_vertical_layers=75,
        layer_thickness_ratio=10,
        depth=4500,
        minimum_depth=25,
        mom_run_dir=dummy_data_folder + "/light_rm6_run",
        mom_input_dir=dummy_data_folder + "/light_rm6_input",
        toolpath_dir=Path(""),
        hgrid_type="from_file",  # This is how we incorporate the grid_gen files
        vgrid_type="from_file",
        expt_name="test",
    )

    # Write the configuration file
    config_expt = driver.CRRDriver.create_experiment_from_config(
        dummy_data_folder + "/test_light_config_file.json"
    )
    assert str(config_expt) == str(expt)


def test_driver_read_config_file_copy(get_dummy_data_folder, tmp_path_factory):
    """
    This test confirms we can write a Regional MOM6 experiment configuration file. There is a lot of overhead to creating ane experiment object, so we'll use our given dummy data.
    """
    dummy_data_folder = get_dummy_data_folder
    fake_input_folder = tmp_path_factory.mktemp("fake_input_folder")
    fake_run_folder = tmp_path_factory.mktemp("fake_run_folder")
    fake_json_folder = tmp_path_factory.mktemp("fake_json_folder")
    fake_json_path = fake_json_folder / "test_light_config_file.json"
    shutil.copy(dummy_data_folder + "/test_light_config_file.json", fake_json_path)

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
    config_expt = driver.CRRDriver.create_experiment_from_config(fake_json_path)
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
