from CrocoDash.shareable.inspect import *
import pytest
import subprocess
from pathlib import Path


@pytest.fixture(scope="session")
def two_cesm_cases(CrocoDash_case_factory, tmp_path_factory):
    case1 = CrocoDash_case_factory(tmp_path_factory.mktemp("case1"))
    case2 = CrocoDash_case_factory(tmp_path_factory.mktemp("case2"))
    return case1, case2


@pytest.fixture
def fake_RCC_filled_case():
    case = ReadCrocoDashCase.__new__(ReadCrocoDashCase)

    case.xmlfiles = {"a.xml", "b.xml"}
    case.sourcemods = {"src.mom/foo.F90"}
    case.xmlchanges = {"JOB_QUEUE": "regular"}
    case.user_nl_objs = {
        "mom": {"DEBUG": {"value": "FALSE"}, "INPUTDIR": {"value": "/path"}}
    }

    return case


@pytest.fixture
def fake_RCC_empty_case():
    case = ReadCrocoDashCase.__new__(ReadCrocoDashCase)
    return case


def test_diff_CESM_cases_nodiff(two_cesm_cases):

    case1, case2 = two_cesm_cases
    output = ReadCrocoDashCase(case1).diff(ReadCrocoDashCase(case2))
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

    output = ReadCrocoDashCase(case1).diff(ReadCrocoDashCase(case2))
    assert output["xml_files_missing_in_new"] == ["test.xml"]
    assert output["user_nl_missing_params"] == {"user_nl_mom": ["DEBUG"]}
    assert output["source_mods_missing_files"] == ["src.mom/bleh.dummy"]
    assert output["xmlchanges_missing"] == ["JOB_PRIORITY"]


def test_identify_CrocoDashCase_init_args(get_CrocoDash_case, fake_RCC_empty_case):
    case = get_CrocoDash_case
    rcc = fake_RCC_empty_case
    rcc.caseroot = case.caseroot
    init_args = rcc._identify_CrocoDashCase_init_args()
    print(init_args)

    assert str(case.inputdir / "ocnice") == str(init_args["inputdir_ocnice"])
    assert str(init_args["supergrid_path"]).startswith(str("ocean_hgrid_pana"))

    assert str(init_args["topo_path"]).startswith(str("ocean_topog_pana"))

    assert str(init_args["vgrid_path"]).startswith(str("ocean_vgrid_pana"))

    assert init_args["compset"] == "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV"


def test_identify_CrocoDashCase_forcing_config_args(
    CrocoDash_case_factory, tmp_path_factory, fake_RCC_empty_case
):
    case1 = CrocoDash_case_factory(tmp_path_factory.mktemp("forcing_config_args"))
    case1.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
        tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
    )
    rcc = fake_RCC_empty_case
    rcc.caseroot = case1.caseroot
    forcing_config = rcc.identify_CrocoDashCase_forcing_config_args()
    # Since this just reads the forcing_config json file in input directory, I'll only check one thing in it
    assert "tides" in forcing_config


def test_identify_non_standard_case_information(
    get_CrocoDash_case, fake_RCC_filled_case
):

    case1 = get_CrocoDash_case
    case1.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
        tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
    )
    rcc = fake_RCC_filled_case
    rcc.caseroot = case1.caseroot
    rcc._get_cesmroot()
    rcc._identify_CrocoDashCase_init_args()
    rcc._identify_CrocoDashCase_forcing_config_args()
    output = rcc.identify_non_standard_case_information(
        case1.cime.cimeroot.parent, case1.machine, case1.project
    )
    assert output["differences"]["xml_files_missing_in_new"] == ["test.xml"]
    assert output["differences"]["user_nl_missing_params"] == {"user_nl_mom": ["DEBUG"]}
    assert output["differences"]["source_mods_missing_files"] == ["src.mom/bleh.dummy"]
    assert output["differences"]["xmlchanges_missing"] == ["JOB_PRIORITY"]


def test_read_user_nl_mom_lines_as_obj(get_CrocoDash_case, fake_RCC_empty_case):
    case = get_CrocoDash_case
    rcc = fake_RCC_empty_case
    rcc.caseroot = case.caseroot
    rcc._get_cesmroot()
    user_nl_mom_obj = rcc._read_user_nl_lines_as_obj("mom")
    assert user_nl_mom_obj["Global"]["INPUTDIR"]["value"] == str(case.inputdir)


def test_get_case_obj(get_CrocoDash_case):
    case = get_case_obj(get_CrocoDash_case.caseroot)
    assert case.get_value("COMPSET") == get_CrocoDash_case.compset_lname + "_SESP"


# Need to test xml, sourcemods, user_nls, init

# Add bundle test


def test_bundle_with_modifications(CrocoDash_case_factory, tmp_path_factory, tmp_path):
    """Test bundle with XML files and sourceMods modifications."""
    case = CrocoDash_case_factory(tmp_path_factory.mktemp(f"case-{uuid4().hex}"))
    # Add modifications to the case
    # 1. Add an XML file
    xml_file = Path(case.caseroot) / "custom_settings.xml"
    xml_file.write_text("<config><setting>value</setting></config>")

    # 2. Add a sourceMods file
    srcmods_dir = Path(case.caseroot) / "SourceMods" / "src.mom"
    srcmods_dir.mkdir(parents=True, exist_ok=True)
    srcmods_file = srcmods_dir / "custom_module.F90"
    srcmods_file.write_text(
        "! Custom source modification\nprogram test\nend program test"
    )

    # 3. Modify user_nl_mom
    user_nl_path = Path(case.caseroot) / "user_nl_mom"
    with open(user_nl_path, "a") as f:
        f.write("\nCUSTOM_PARAM=42\n")

    # Configure forcings
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-09 00:00:00"],
        tidal_constituents=["M2"],
        tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
        tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
    )

    # Create fake files in ocnice directory
    ocnice_dir = Path(case.inputdir) / "ocnice"
    (ocnice_dir / "forcing_obc_Seg_fake.nc").touch()
    (ocnice_dir / "tz_fake.nc").touch()

    # Create identify_output with modifications
    identify_output = {
        "differences": {
            "xml_files_missing_in_new": ["custom_settings.xml"],
            "user_nl_missing_params": {"user_nl_mom": ["CUSTOM_PARAM"]},
            "source_mods_missing_files": ["src.mom/custom_module.F90"],
            "xmlchanges_missing": [],
        },
        "init_args": {
            "inputdir": case.inputdir,
            "supergrid_path": case.supergrid_path,
            "topo_path": case.topo_path,
            "vgrid_path": case.vgrid_path,
            "compset": case.compset_lname,
        },
        "forcing_config": {},
        "case_info": {
            "caseroot": case.caseroot,
            "inputdir_ocnice": case.inputdir / "ocnice",
        },
    }
    with open(case.inputdir / "extract_forcings" / "config.json") as f:
        identify_output["forcing_config"] = json.load(f)

    output_dir = tmp_path / "bundle_output_modified"
    output_dir.mkdir()

    rcc = ReadCrocoDashCase(case.caseroot)
    # Run the function
    rcc.bundle(output_dir)

    # Check that case_bundle folder was created
    case_bundle = output_dir / f"{case.caseroot.name}_case_bundle"
    assert case_bundle.exists()

    # Check that XML files were copied
    xml_files_dir = case_bundle / "xml_files"
    assert xml_files_dir.exists()
    assert (xml_files_dir / "custom_settings.xml").exists()

    # Check that sourceMods were copied
    sourcemods_dir = case_bundle / "SourceMods"
    assert sourcemods_dir.exists()
    assert (sourcemods_dir / "src.mom" / "custom_module.F90").exists()

    # Check that user_nl_mom was copied
    assert (case_bundle / "user_nl_mom").exists()

    # Check that replay.sh was copied
    replay_sh_path = case_bundle / "replay.sh"
    assert replay_sh_path.exists()

    # Check that identify_output.json was written
    json_file = case_bundle / "identify_output.json"
    assert json_file.exists()
    with open(json_file) as f:
        saved_output = json.load(f)
    assert "differences" in saved_output
    assert "init_args" in saved_output
    assert "forcing_config" in saved_output
    assert "case_info" in saved_output
    assert saved_output["differences"]["xml_files_missing_in_new"] == [
        "custom_settings.xml"
    ]
    assert saved_output["differences"]["source_mods_missing_files"] == [
        "src.mom/custom_module.F90"
    ]

    # Check that ocnice directory was copied
    ocnice_dir = case_bundle / "ocnice"
    assert ocnice_dir.exists(), "ocnice directory should be copied from inputdir"
    # Verify ocnice has expected structure
    assert (ocnice_dir / "forcing_obc_Seg_fake.nc").exists()
    assert (ocnice_dir / "tz_fake.nc").exists()

    # Verify content of XML file
    with open(xml_files_dir / "custom_settings.xml") as f:
        xml_content = f.read()
    assert "<config>" in xml_content
    assert "<setting>value</setting>" in xml_content

    # Verify content of sourceMod file
    with open(sourcemods_dir / "src.mom" / "custom_module.F90") as f:
        sourcemod_content = f.read()
    assert "! Custom source modification" in sourcemod_content
    assert "program test" in sourcemod_content

    # Verify user_nl_mom contains the custom parameter
    with open(case_bundle / "user_nl_mom") as f:
        user_nl_content = f.read()
    assert "CUSTOM_PARAM=42" in user_nl_content

    # Verify zip contains all expected files
