import tempfile
from pathlib import Path
from datetime import datetime
import pytest
from CrocoDash.extract_forcings import utils


def test_date_continuity(tmp_path: Path):
    # Fake filenames with a gap (20000104 missing) and overlap (20000106 appears twice)
    filenames = [
        "north_unprocessed.20000101_20000102.nc",
        "north_unprocessed.20000103_20000103.nc",
        # gap here: missing 20000104
        "north_unprocessed.20000105_20000106.nc",
        "north_unprocessed.20000106_20000107.nc",  # overlap with previous (20000106)
    ]

    # Create these fake files in tmp_path
    for name in filenames:
        (tmp_path / name).touch()

    # Run parser
    files = utils.parse_dataset_folder(
        tmp_path,
        r"(north|east|south|west)_unprocessed\.(\d{8})_(\d{8})\.nc",
        "%Y%m%d",
    )

    # Run continuity check
    issues = utils.check_date_continuity(files)

    # Assertions
    assert "north" in issues
    assert any("Gap" in msg for msg in issues["north"])
    assert any("Overlap" in msg for msg in issues["north"])
