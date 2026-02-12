from CrocoDash.shareable.inspect import *
import pytest
import subprocess
from pathlib import Path


@pytest.fixture(scope="session")
def two_cesm_cases(CrocoDash_case_factory, tmp_path_factory):
    case1 = CrocoDash_case_factory(tmp_path_factory.mktemp("case1"))
    case2 = CrocoDash_case_factory(tmp_path_factory.mktemp("case2"))
    return case1, case2


def test_diff_CESM_cases_nodiff(two_cesm_cases):

    case1, case2 = two_cesm_cases
    output = diff_CESM_cases(
        case1.caseroot,
        case2.caseroot,
    )
    assert output["xml_files_missing_in_new"] == []
    assert output["user_nl_missing_params"] == {}
    assert output["source_mods_missing_files"] == []
    assert output["xmlchanges_missing"] == []


def test_diff_CESM_cases_alldiff(two_cesm_cases):
    case1, case2 = two_cesm_cases
    # add in a .xml file to case1.caseroot folder
    xml_file = Path(case1.caseroot) / "test.xml"
    xml_file.write_text("<test>data</test>")

    # run subprocess.run xmlchange in case1.caseroot folder for JOB_PRIORITY=premium with -N flag
    subprocess.run(
        ["./xmlchange", "JOB_PRIORITY=premium", "-N"],
        cwd=case1.caseroot,
    )

    # add a file to case1.caseroot/SourceMods/src.mom called bleh.dummy
    srcmods_dir = Path(case1.caseroot) / "SourceMods" / "src.mom"
    dummy_file = srcmods_dir / "bleh.dummy"
    dummy_file.write_text("dummy content")

    # add a line to case1.caseroot/user_nl_mom with DEBUG=TRUE
    user_nl_path = Path(case1.caseroot) / "user_nl_mom"
    with open(user_nl_path, "a") as f:
        f.write("\nDEBUG=TRUE\n")

    output = diff_CESM_cases(
        case1.caseroot,
        case2.caseroot,
    )
    assert output["xml_files_missing_in_new"] == ["test.xml"]
    assert output["user_nl_missing_params"] == {"user_nl_mom": ["DEBUG"]}
    assert output["source_mods_missing_files"] == ["src.mom/bleh.dummy"]
    assert output["xmlchanges_missing"] == ["JOB_PRIORITY"]


def test_identify_CrocoDashCase_init_args(get_CrocoDash_case):
    case = get_CrocoDash_case
    init_args = identify_CrocoDashCase_init_args(case.caseroot)
    print(init_args)

    assert str(case.inputdir / "ocnice") == str(init_args["inputdir_ocnice"])
    assert str(init_args["supergrid_path"]).startswith(str("ocean_hgrid_pana"))

    assert str(init_args["topo_path"]).startswith(str("ocean_topog_pana"))

    assert str(init_args["vgrid_path"]).startswith(str("ocean_vgrid_pana"))

    assert init_args["compset"] == "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"


def test_identify_CrocoDashCase_forcing_config_args(
    CrocoDash_case_factory, tmp_path_factory
):
    case1 = CrocoDash_case_factory(tmp_path_factory.mktemp("forcing_config_args"))
    case1.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
        tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
    )
    forcing_config = identify_CrocoDashCase_forcing_config_args(case1.caseroot)
    # Since this just reads the forcing_config json file in input directory, I'll only check one thing in it
    assert "tides" in forcing_config


def test_identify_CrocoDashCase_forcing_config_args(
    CrocoDash_case_factory, tmp_path_factory
):
    case1 = CrocoDash_case_factory(tmp_path_factory.mktemp("forcing_config_args"))
    case1.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
        tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
    )
    forcing_config = identify_CrocoDashCase_forcing_config_args(case1.caseroot)
    # Since this just reads the forcing_config json file in input directory, I'll only check one thing in it
    assert "tides" in forcing_config


def test_identify_non_standard_case_information(get_CrocoDash_case):
    case1 = get_CrocoDash_case
    # add in a .xml file to case1.caseroot folder
    xml_file = Path(case1.caseroot) / "test.xml"
    xml_file.write_text("<test>data</test>")

    # run subprocess.run xmlchange in case1.caseroot folder for JOB_PRIORITY=premium with -N flag
    subprocess.run(
        ["./xmlchange", "JOB_PRIORITY=premium", "-N"],
        cwd=case1.caseroot,
    )

    # add a file to case1.caseroot/SourceMods/src.mom called bleh.dummy
    srcmods_dir = Path(case1.caseroot) / "SourceMods" / "src.mom"
    dummy_file = srcmods_dir / "bleh.dummy"
    dummy_file.write_text("dummy content")

    # add a line to case1.caseroot/user_nl_mom with DEBUG=TRUE
    user_nl_path = Path(case1.caseroot) / "user_nl_mom"
    with open(user_nl_path, "a") as f:
        f.write("\nDEBUG=TRUE\n")

    case1.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
        tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
    )

    output = identify_non_standard_case_information(
        case1.caseroot, case1.cime.cimeroot.parent, case1.machine, case1.project
    )
    assert output["differences"]["xml_files_missing_in_new"] == ["test.xml"]
    assert output["differences"]["user_nl_missing_params"] == {"user_nl_mom": ["DEBUG"]}
    assert output["differences"]["source_mods_missing_files"] == ["src.mom/bleh.dummy"]
    assert output["differences"]["xmlchanges_missing"] == ["JOB_PRIORITY"]


def test_read_user_nl_mom_lines_as_obj(get_CrocoDash_case):
    case = get_CrocoDash_case
    user_nl_mom_obj = read_user_nl_mom_lines_as_obj(case.caseroot)
    breakpoint()
    assert user_nl_mom_obj.data["Global"]["INPUTDIR"]["value"] == str(case.inputdir)


def test_get_case_obj(get_CrocoDash_case):
    case = get_case_obj(get_CrocoDash_case.caseroot)
    assert case.get_value("COMPSET") == get_CrocoDash_case.compset_lname + "_SESP"
