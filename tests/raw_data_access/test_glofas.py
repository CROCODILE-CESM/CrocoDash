from CrocoDash.raw_data_access.datasets import glofas as gl
import os
import pytest


def test_get_processed_global_glofas_script_for_cli(tmp_path):

    path = gl.GLORYS.get_processed_global_glofas_script_for_cli(output_dir=tmp_path, output_file="glofas_processed_data.nc")

    assert os.path.exists(path)

@pytest.mark.slow
def test_get_global_data_with_python(tmp_path):

    path = gl.GLORYS.get_global_data_with_python(dates = ["2020-01-01","2020-01-03"],output_dir=tmp_path, output_file="glofas_processed_data.nc")

    assert os.path.exists(path)
