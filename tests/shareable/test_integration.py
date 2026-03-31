from CrocoDash.shareable import inspect, fork
from unittest.mock import patch
import subprocess
from pathlib import Path
import pytest
import pytest


@pytest.mark.slow
def test_pass_from_inspect_to_fork_no_change(get_case_with_cf, tmp_path):
    case = get_case_with_cf
    rcc = inspect.ReadCrocoDashCase(case.caseroot)
    rcc.identify_non_standard_CrocoDash_case_information(
        rcc.cesmroot, case.machine, case.project
    )
    loc = rcc.bundle(tmp_path)
    with patch("CrocoDash.shareable.fork.ask_yes_no", return_value=False), patch(
        "CrocoDash.shareable.fork.ask_string", return_value=""
    ), patch("CrocoDash.shareable.fork.copy_xml_files_from_case"), patch(
        "CrocoDash.shareable.fork.copy_user_nl_params_from_case"
    ), patch(
        "CrocoDash.shareable.fork.copy_source_mods_from_case"
    ), patch(
        "CrocoDash.shareable.fork.apply_xmlchanges_to_case"
    ), patch(
        "CrocoDash.shareable.fork.copy_configurations_to_case"
    ):
        fcb = fork.ForkCrocoDashBundle(
            loc,
            rcc.cesmroot,
            case.machine,
            case.project,
            tmp_path / "caseroot",
            tmp_path / "inputdir",
        )
        fcb.fork()
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
    rcc = inspect.ReadCrocoDashCase(case.caseroot)
    rcc.identify_non_standard_CrocoDash_case_information(
        rcc.cesmroot, case.machine, case.project
    )
    loc = rcc.bundle(tmp_path)
    with patch("CrocoDash.shareable.fork.ask_yes_no", return_value=True), patch(
        "CrocoDash.shareable.fork.ask_string", return_value=""
    ), patch(
        "CrocoDash.shareable.fork.ForkCrocoDashBundle.resolve_compset",
        return_value=case.compset_lname,
    ):
        fcb = fork.ForkCrocoDashBundle(
            loc,
            rcc.cesmroot,
            case.machine,
            case.project,
            tmp_path / "caseroot",
            tmp_path / "inputdir",
        )
        fcb.fork()
        path_to_case = fcb.case.caseroot
        assert (path_to_case / "test.xml").exists()
        assert (path_to_case / "SourceMods" / "src.mom" / "bleh.dummy").exists()
        with open(path_to_case / "user_nl_mom") as f:
            user_nl_content = f.read()
            assert "DEBUG = TRUE" in user_nl_content
        with open(path_to_case / "replay.sh") as f:
            replay_content = f.read()
            assert "./xmlchange JOB_PRIORITY=premium" in replay_content
