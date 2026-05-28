from CrocoDash.raw_data_access.datasets import srtm as sr
import os
import pytest


def test_get_srtm_data_script(tmp_path):

    path = sr.SRTM.get_srtm_data_script(
        output_folder=tmp_path, output_filename="SRTM15_V2.6.nc"
    )

    assert os.path.exists(path)


@pytest.mark.slow
def test_get_srtm_data_with_python(tmp_path):

    path = sr.SRTM.get_srtm_data_with_python(
        output_folder=tmp_path, output_filename="SRTM15_V2.6.nc"
    )

    assert os.path.exists(path)
