"""Unit tests for CrocoDash/raw_data_access/datasets/utils.py helpers."""

import os
import stat
from pathlib import Path

import pytest

from CrocoDash.raw_data_access.datasets.gebco import GEBCO
from CrocoDash.raw_data_access.datasets.seawifs import SeaWIFS
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
    """write_bash_curl_script writes a shell script with curl and sets the +x bit,
    creating its folder first."""
    script_path = write_bash_curl_script(
        url="https://example.com/file.nc",
        script_name="download.sh",
        output_folder=str(tmp_path / "not_yet_made"),
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


@pytest.mark.parametrize(
    "method, script_name",
    [
        (SeaWIFS.get_global_seawifs_script_for_cli, "get_seawifs_data.sh"),
        (GEBCO.get_gebco_data_script, "get_gebco_data.sh"),
    ],
)
def test_script_methods_work_on_their_defaults(
    tmp_path, monkeypatch, method, script_name
):
    """With no output_folder, a script method writes its script to the working
    directory and downloads there."""
    monkeypatch.chdir(tmp_path)
    script = Path(method())
    assert script == tmp_path / script_name
    assert "None" not in script.read_text()


def _serve_gebco_zip(monkeypatch, members):
    """Make GEBCO's download return a zip holding these (empty) files."""
    import io
    import zipfile
    from types import SimpleNamespace
    import CrocoDash.raw_data_access.datasets.gebco as gebco

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        for name in members:
            z.writestr(name, b"")

    class Response(SimpleNamespace):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield payload.getvalue()

    monkeypatch.setattr(gebco.requests, "get", lambda url, stream: Response())


def test_gebco_python_download_returns_the_grid_not_the_zip(tmp_path, monkeypatch):
    """The method unzips the download; callers need the grid file it holds."""
    _serve_gebco_zip(monkeypatch, ["GEBCO_2024.nc", "README.pdf"])
    assert GEBCO.get_gebco_data_with_python(tmp_path) == tmp_path / "GEBCO_2024.nc"


def test_gebco_python_download_without_a_grid_raises(tmp_path, monkeypatch):
    """A zip with no grid says so, instead of handing back the folder."""
    _serve_gebco_zip(monkeypatch, ["README.pdf"])
    with pytest.raises(ValueError, match="exactly one .nc grid"):
        GEBCO.get_gebco_data_with_python(tmp_path)
