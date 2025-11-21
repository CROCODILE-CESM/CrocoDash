from CrocoDash.raw_data_access.datasets import seawifs as sw
import os


def test_get_global_seawifs_script_for_cli(tmp_path):

    path = sw.SeaWIFS.get_global_seawifs_script_for_cli(
        output_folder=tmp_path, username="test"
    )

    assert os.path.exists(path)


def test_get_processed_global_seawifs_script_for_cli(tmp_path):

    path = sw.SeaWIFS.get_processed_global_seawifs_script_for_cli(
        output_folder=tmp_path, output_filename="test.nc"
    )

    assert os.path.exists(path)
