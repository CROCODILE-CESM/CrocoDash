from CrocoDash.raw_data_access.datasets import seawifs as sw
import os


def test_get_global_seawifs_script_for_cli(tmp_path):

    path = sw.get_global_seawifs_script_for_cli(output_dir=tmp_path, username="test")

    assert os.path.exists(path)
