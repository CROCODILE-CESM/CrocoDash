from CrocoDash.raw_data_access.datasets import gebco as gb
import os
import pytest


def test_get_gebco_data_script(tmp_path):

    path = gb.GEBCO.get_gebco_data_script(
        output_folder=tmp_path, output_filename="gebco_2024.nc"
    )

    assert os.path.exists(path)


@pytest.mark.slow
def test_get_gebco_data_with_python(tmp_path):

    path = gb.GEBCO.get_gebco_data_with_python(
        output_folder=tmp_path, output_filename="gebco_2024.nc"
    )

    assert os.path.exists(path)
