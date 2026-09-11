import os
import datetime as dt
import os
import pytest
from uuid import uuid4


def file_with_prefix_exists(directory, prefix):
    for filename in os.listdir(directory):
        if filename.startswith(prefix):
            return True
    return False


def test_case_init_and_create_grid_input(get_CrocoDash_case):
    case = get_CrocoDash_case
    assert case is not None
    assert os.path.exists(case.caseroot)
    assert os.path.exists(case.inputdir)
    assert file_with_prefix_exists(case.inputdir / "ocnice", "ocean_hgrid")
    assert file_with_prefix_exists(case.caseroot, "README")

    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_hgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_topog_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_vgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"scrip_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ESMF_mesh_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    if "CICE" in case.compset_lname:
        files = [
            f
            for f in os.listdir(case.inputdir / "ocnice")
            if f.startswith(f"cice_grid_{case.ocn_grid.name}")
        ]
        assert len(files) > 0


def test_configure_forcings(get_case_with_cf):
    case = get_case_with_cf
    assert case.date_range[0].year == 2020
    assert case.boundaries == ["north", "east"]
    search_string = "OBC_NUMBER_OF_SEGMENTS"
    with open(case.caseroot / "user_nl_mom", "r", encoding="utf-8") as file:
        for line in file:
            if search_string in line:
                found_user_nl_mom_adjusted_var = True
                break
    assert found_user_nl_mom_adjusted_var


def test_configure_forcings_invalid_function_overrides(get_CrocoDash_case):
    """
    GLORYS access functions have no non-required args, so any override key is invalid.
    """
    case = get_CrocoDash_case
    with pytest.raises(ValueError):
        case.configure_forcings(
            date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
            boundaries=["north"],
            function_overrides={"bogus_key": 1},
        )
