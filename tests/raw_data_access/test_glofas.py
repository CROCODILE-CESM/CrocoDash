from CrocoDash.raw_data_access.datasets import glofas as gl
import os
import pytest


def test_get_processed_global_glofas_script_for_cli(tmp_path):

    path = gl.get_processed_global_glofas_script_for_cli(output_dir="", output_file="glofas_processed_data.nc")

    assert os.path.exists(path)

