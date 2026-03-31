from CrocoDash.shareable import inspect, fork
from unittest.mock import patch
import subprocess
from pathlib import Path


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

