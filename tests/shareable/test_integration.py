from CrocoDash import shareable
from CrocoDash.shareable import duplicate_case, CaseBundle, ForkBundle
from unittest.mock import patch
import subprocess
from pathlib import Path
import pytest
import pytest


@pytest.mark.slow
def test_duplicate_case(get_case_with_cf, tmp_path):
    case = get_case_with_cf
    new_caseroot = tmp_path / "duplicated_case"
    new_inputdir = tmp_path / "duplicated_inputdir"

    new_case = duplicate_case(case.caseroot, new_caseroot, new_inputdir)

    assert new_case is not None
    assert new_caseroot.exists()
    assert any(new_caseroot.glob("*_case_bundle"))


@pytest.mark.slow
def test_pass_from_inspect_to_fork_no_change(get_case_with_cf, tmp_path):
    case = get_case_with_cf
    rcc = CaseBundle(case.caseroot)
    rcc.identify_non_standard_case_info(rcc.cesmroot, case.machine, case.project)
    loc = rcc.bundle(tmp_path)
    with patch("CrocoDash.shareable.ask_yes_no", return_value=False), patch(
        "CrocoDash.shareable.ask_string", return_value=""
    ), patch("CrocoDash.shareable.copy_xml_files_from_case"), patch(
        "CrocoDash.shareable.copy_user_nl_params_from_case"
    ), patch(
        "CrocoDash.shareable.copy_source_mods_from_case"
    ), patch(
        "CrocoDash.shareable.apply_xmlchanges_to_case"
    ):
        fcb = ForkBundle(loc)
        fcb.fork(
            rcc.cesmroot,
            case.machine,
            case.project,
            tmp_path / "caseroot",
            tmp_path / "inputdir",
        )
        assert fcb


@pytest.mark.slow
def test_pass_from_inspect_to_fork_with_changes(get_case_with_cf, tmp_path):
    case = get_case_with_cf

    xml_file = Path(case.caseroot) / "test.xml"
    xml_file.write_text("<test>data</test>")

    # run subprocess.run xmlchange in case.caseroot folder for JOB_PRIORITY=premium with -N flag
    subprocess.run(
        ["./xmlchange", "JOB_PRIORITY=premium", "-N"],
        cwd=case.caseroot,
    )

    # add a file to case.caseroot/SourceMods/src.mom called bleh.dummy
    srcmods_dir = Path(case.caseroot) / "SourceMods" / "src.mom"
    dummy_file = srcmods_dir / "bleh.dummy"
    dummy_file.write_text("dummy content")

    # add a line to case.caseroot/user_nl_mom with DEBUG=TRUE
    user_nl_path = Path(case.caseroot) / "user_nl_mom"
    with open(user_nl_path, "a") as f:
        f.write("\nDEBUG=TRUE\n")
    rcc = CaseBundle(case.caseroot)
    rcc.identify_non_standard_case_info(rcc.cesmroot, case.machine, case.project)
    loc = rcc.bundle(tmp_path)
    with patch("CrocoDash.shareable.ask_yes_no", return_value=True), patch(
        "CrocoDash.shareable.ask_string", return_value=""
    ):
        fcb = ForkBundle(loc)
        fcb.fork(
            rcc.cesmroot,
            case.machine,
            case.project,
            tmp_path / "caseroot",
            tmp_path / "inputdir",
            compset=case.compset_lname,
        )
        path_to_case = fcb.case.caseroot
        assert (path_to_case / "test.xml").exists()
        assert (path_to_case / "SourceMods" / "src.mom" / "bleh.dummy").exists()
        with open(path_to_case / "user_nl_mom") as f:
            user_nl_content = f.read()
            assert "DEBUG = TRUE" in user_nl_content
        with open(path_to_case / "replay.sh") as f:
            replay_content = f.read()
            assert "./xmlchange JOB_PRIORITY=premium" in replay_content
