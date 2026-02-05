from CrocoDash.shareable.apply import *
from unittest.mock import patch, MagicMock


def test_copy_xml_files_from_case(tmp_path):
    """Test copy_xml_files_from_case copies XML files correctly."""
    old_caseroot = tmp_path / "old_case"
    new_caseroot = tmp_path / "new_case"
    old_caseroot.mkdir()
    new_caseroot.mkdir()

    # Create XML files in old_caseroot
    xml_file1 = old_caseroot / "custom.xml"
    xml_file2 = old_caseroot / "config.xml"
    xml_file1.write_text("<xml>data1</xml>")
    xml_file2.write_text("<xml>data2</xml>")

    # Copy files
    copy_xml_files_from_case(old_caseroot, new_caseroot, ["custom.xml", "config.xml"])

    # Verify files were copied
    assert (new_caseroot / "custom.xml").exists()
    assert (new_caseroot / "config.xml").exists()
    assert (new_caseroot / "custom.xml").read_text() == "<xml>data1</xml>"
    assert (new_caseroot / "config.xml").read_text() == "<xml>data2</xml>"


def test_copy_user_nl_params_from_case(tmp_path):
    """Test copy_user_nl_params_from_case extracts and applies user_nl parameters from multiple files."""
    old_caseroot = tmp_path / "old_case"
    old_caseroot.mkdir()

    # Create user_nl_mom with parameters
    user_nl_mom = old_caseroot / "user_nl_mom"
    user_nl_mom.write_text(
        "! This is a comment\n" "PARAM1=value1\n" "PARAM2=value2\n" "PARAM3=value3\n"
    )

    # Create user_nl_cice with parameters
    user_nl_cice = old_caseroot / "user_nl_cice"
    user_nl_cice.write_text(
        "! CICE parameters\n" "CICE_PARAM1=cice_value1\n" "CICE_PARAM2=cice_value2\n"
    )

    # Mock append_user_nl to track calls
    with patch("CrocoDash.shareable.apply.append_user_nl") as mock_append:
        copy_user_nl_params_from_case(
            old_caseroot, {"mom": {"PARAM1", "PARAM3"}, "cice": {"CICE_PARAM1"}}
        )

    # Verify that only specified mom params were appended
    calls = [call[0] for call in mock_append.call_args_list]
    assert ("mom", [("PARAM1", "value1")]) in calls
    assert ("mom", [("PARAM3", "value3")]) in calls
    # PARAM2 should not have been called
    assert ("mom", [("PARAM2", "value2")]) not in calls

    # Verify that only specified cice params were appended
    assert ("cice", [("CICE_PARAM1", "cice_value1")]) in calls
    # CICE_PARAM2 should not have been called
    assert ("cice", [("CICE_PARAM2", "cice_value2")]) not in calls


def test_copy_source_mods_from_case(tmp_path):
    """Test copy_source_mods_from_case copies source modification files."""
    old_caseroot = tmp_path / "old_case"
    new_caseroot = tmp_path / "new_case"

    # Create source mods in old_caseroot
    old_srcmods = old_caseroot / "SourceMods" / "src.mom"
    old_srcmods.mkdir(parents=True)
    (old_srcmods / "file1.F90").write_text("! Source code 1")
    (old_srcmods / "file2.F90").write_text("! Source code 2")

    # Create destination
    new_srcmods = new_caseroot / "SourceMods" / "src.mom"
    new_srcmods.mkdir(parents=True)

    # Copy files
    copy_source_mods_from_case(
        old_caseroot,
        new_caseroot,
        ["src.mom/file1.F90", "src.mom/file2.F90"],
    )

    # Verify files were copied
    assert (new_srcmods / "file1.F90").exists()
    assert (new_srcmods / "file2.F90").exists()
    assert (new_srcmods / "file1.F90").read_text() == "! Source code 1"
    assert (new_srcmods / "file2.F90").read_text() == "! Source code 2"


def test_apply_xmlchanges_to_case(tmp_path):
    """Test apply_xmlchanges_to_case applies xmlchange parameters from replay.sh."""
    old_caseroot = tmp_path / "old_case"
    old_caseroot.mkdir()

    # Create replay.sh with xmlchange lines
    replay_sh = old_caseroot / "replay.sh"
    replay_sh.write_text(
        "#!/bin/bash\n"
        "./xmlchange JOB_PRIORITY=premium\n"
        "./xmlchange DOUT_S=TRUE\n"
        "./xmlchange CONTINUE_RUN=FALSE\n"
    )

    # Mock xmlchange to track calls
    with patch("CrocoDash.shareable.apply.xmlchange") as mock_xmlchange:
        apply_xmlchanges_to_case(old_caseroot, {"JOB_PRIORITY", "CONTINUE_RUN"})

    # Verify that only specified params were applied
    calls = [call[0] for call in mock_xmlchange.call_args_list]
    assert ("JOB_PRIORITY", "premium") in calls
    assert ("CONTINUE_RUN", "FALSE") in calls
    # DOUT_S should not have been called
    assert ("DOUT_S", "TRUE") not in calls


def test_copy_configurations_to_case(tmp_path):
    """Test copy_configurations_to_case copies forcing configuration files."""
    # Create mock case object
    mock_case = MagicMock()
    mock_case.inputdir = tmp_path / "inputdir" / "ocnice"
    mock_case.inputdir.mkdir(parents=True, exist_ok=True)
    mock_case.fcr.active_configurators.keys.return_value = ["tides", "bgc"]

    # Create source directory with files
    inputdir_ocnice = tmp_path / "old_ocnice"
    inputdir_ocnice.mkdir()
    (inputdir_ocnice / "forcing_obc_seg_0001.nc").write_text("data1")
    (inputdir_ocnice / "init_temp_salt.nc").write_text("data2")
    (inputdir_ocnice / "tides_data.nc").write_text("data3")

    # Create forcing config
    forcing_config = {
        "basic": {"data": "basic_data"},
        "tides": {"name": "tides", "outputs": ["tides_data.nc"]},
        "bgc": {"name": "bgc", "outputs": ["bgc_data.nc"]},
    }

    # Mock multiple functions to track calls
    with patch("CrocoDash.shareable.apply.shutil.copy") as mock_copy, patch(
        "CrocoDash.shareable.apply.ForcingConfigRegistry.get_configurator"
    ) as mock_get_cfg, patch("CrocoDash.shareable.apply.Path.glob") as mock_glob:

        # Setup mock configurator
        mock_cfg = MagicMock()
        mock_cfg.get_output_filepaths.return_value = ["tides_data.nc"]
        mock_get_cfg.return_value = mock_cfg

        # Setup mock glob to return test files
        mock_glob.return_value = [inputdir_ocnice / "forcing_obc_seg_0001.nc"]

        copy_configurations_to_case(forcing_config, mock_case, inputdir_ocnice)

    # Verify functions were called
    assert mock_copy.call_count > 0
    assert mock_get_cfg.called
