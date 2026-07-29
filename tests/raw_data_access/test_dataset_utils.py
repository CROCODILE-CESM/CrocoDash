"""Unit tests for CrocoDash/raw_data_access/datasets/utils.py helpers."""

import os
import stat

from CrocoDash.raw_data_access.datasets.utils import (
    convert_lons_to_180_range,
    write_bash_curl_script,
)


def test_convert_lons_to_180_range_basic():
    """Longitudes > 180 should wrap into [-180, 180)."""
    out = convert_lons_to_180_range(190, 0, -10, 360)
    assert out == [-170, 0, -10, 0]


def test_convert_lons_to_180_range_returns_list():
    """The function always returns a list, even for a single argument."""
    out = convert_lons_to_180_range(45)
    assert isinstance(out, list)
    assert out == [45]


def test_write_bash_curl_script_creates_executable_script(tmp_path):
    """write_bash_curl_script writes a shell script with curl and sets the +x bit."""
    script_path = write_bash_curl_script(
        url="https://example.com/file.nc",
        script_name="download.sh",
        output_folder=str(tmp_path),
        output_filename="file.nc",
    )
    assert os.path.exists(script_path)

    with open(script_path) as f:
        body = f.read()
    assert body.startswith("#!/bin/bash")
    assert "curl -L 'https://example.com/file.nc'" in body
    assert "file.nc" in body

    # Ensure executable bit is set (owner, group, or other).
    mode = os.stat(script_path).st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
