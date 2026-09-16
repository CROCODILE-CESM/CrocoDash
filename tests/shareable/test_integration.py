from CrocoDash import shareable
from CrocoDash.shareable import duplicate_case, CaseBundle, ForkBundle
from unittest.mock import patch
import subprocess
from pathlib import Path
import pytest


# ForkBundle.fork() is interactive. These stand in for a recipient who presses
# Enter at every prompt: ask_string/ask_yes_no both return the value they were
# given as `default`. Patching them with a fixed return_value instead is a trap
# -- return_value="" makes _guide_yaml_review overwrite every field (caseroot,
# machine, compset) with the empty string, and a fixed True/False also answers
# the final "Proceed with this configuration?" and the "$EDITOR?" prompt.
def press_enter_string(prompt, default=""):
    return default


def press_enter_yes_no(prompt, default=True):
    return default


@pytest.mark.slow
def test_duplicate_case(get_case_with_cf, tmp_path):
    case = get_case_with_cf
    new_caseroot = tmp_path / "duplicated_case"
    new_inputdir = tmp_path / "duplicated_inputdir"

    # configure_forcings doesn't produce NetCDF files — seed the ocnice dir
    # with fake forcing files so the copy logic has something to transfer.
    old_ocnice = Path(case.inputdir) / "ocnice"
    old_ocnice.mkdir(parents=True, exist_ok=True)
    fake_files = ["forcing_obc_seg_001.nc", "init_temp_salt.nc"]
    for fname in fake_files:
        (old_ocnice / fname).write_text("fake")

    new_case = duplicate_case(case.caseroot, new_caseroot, new_inputdir)

    assert new_case is not None
    assert new_caseroot.exists()
    new_ocnice = new_inputdir / "ocnice"
    for fname in fake_files:
        assert (new_ocnice / fname).exists()


@pytest.mark.slow
def test_pass_from_inspect_to_fork_no_change(get_case_with_cf, tmp_path):
    case = get_case_with_cf
    rcc = CaseBundle(case.caseroot)
    rcc.identify_non_standard_case_info(rcc.cesmroot, case.machine, case.project)
    loc = rcc.bundle(tmp_path)
    with patch("CrocoDash.shareable.ask_yes_no", side_effect=press_enter_yes_no), patch(
        "CrocoDash.shareable.ask_string", side_effect=press_enter_string
    ):
        fcb = ForkBundle(loc)
        new_case = fcb.fork(
            rcc.cesmroot,
            case.machine,
            case.project,
            tmp_path / "caseroot",
            tmp_path / "inputdir",
        )
        # Every copy-plan prompt defaults to False, so nothing is transferred.
        assert not any(fcb.plan.values())
        assert new_case is not None
        assert Path(new_case.caseroot).exists()


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
    with patch("CrocoDash.shareable.ask_yes_no", side_effect=press_enter_yes_no), patch(
        "CrocoDash.shareable.ask_string", side_effect=press_enter_string
    ):
        fcb = ForkBundle(loc)
        fcb.fork(
            rcc.cesmroot,
            case.machine,
            case.project,
            tmp_path / "caseroot",
            tmp_path / "inputdir",
            plan={
                "xml_files": True,
                "user_nl": True,
                "source_mods": True,
                "xmlchanges": True,
            },
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
