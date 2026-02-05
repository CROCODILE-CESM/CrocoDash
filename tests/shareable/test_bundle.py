from CrocoDash.shareable.bundle import bundle_case_information, compress_bundle
import json
import zipfile
from pathlib import Path
from uuid import uuid4


def test_compress_case_information_with_modifications(
    CrocoDash_case_factory, tmp_path_factory, tmp_path
):
    """Test compress_case_information with XML files and sourceMods modifications."""
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

    # Run the function
    bundle_case_information(identify_output, output_dir)

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

    # Verify zip information
    zip_file = compress_bundle(case_bundle)
    zip_file = case_bundle / f"{case.caseroot.name}_case_bundle.zip"
    assert zip_file.exists()
    assert zip_file.stat().st_size > 0, "Zip file should not be empty"

    # Verify zip contains all expected files
    with zipfile.ZipFile(zip_file, "r") as zipf:
        zip_names = zipf.namelist()
        assert "identify_output.json" in zip_names
        assert "xml_files/custom_settings.xml" in zip_names
        assert "SourceMods/src.mom/custom_module.F90" in zip_names
        assert "user_nl_mom" in zip_names
        assert "replay.sh" in zip_names
        assert any(
            "forcing_" in name for name in zip_names
        ), "Zip should contain ocnice files (such as forcing_)"

        # Verify JSON content in zip
        with zipf.open("identify_output.json") as zf:
            zip_json = json.load(zf)
        assert "differences" in zip_json
        assert "case_info" in zip_json
