import sys
import json
from unittest.mock import patch, MagicMock


def run_main(argv):
    with patch.object(sys, "argv", ["crocodash"] + argv):
        from CrocoDash.cli import main

        main()


def test_bundle_cli(tmp_path):
    mock_case = MagicMock()
    mock_case.name = "case"

    with patch(
        "CrocoDash.case.Case.from_caseroot", return_value=mock_case
    ) as from_caseroot:
        run_main(
            [
                "bundle",
                "--caseroot",
                "/some/case",
                "--output-dir",
                str(tmp_path),
                "--cesmroot",
                "/some/cesm",
                "--machine",
                "derecho",
                "--project",
                "PROJ123",
            ]
        )

    from_caseroot.assert_called_once_with("/some/case")
    mock_case.bundle.assert_called_once_with(tmp_path / "case_case_bundle")


def test_fork_cli(tmp_path):
    source = MagicMock()
    plan = {
        "xml_files": True,
        "user_nl": False,
        "source_mods": True,
        "xmlchanges": True,
    }

    with patch("CrocoDash.case.Case.from_caseroot", return_value=source), patch(
        "CrocoDash.case.Case.fork"
    ) as fork:
        run_main(
            [
                "fork",
                "--bundle",
                str(tmp_path / "bundle"),
                "--caseroot",
                str(tmp_path / "new_case"),
                "--inputdir",
                str(tmp_path / "inputdir"),
                "--cesmroot",
                "/some/cesm",
                "--machine",
                "derecho",
                "--project",
                "PROJ123",
                "--plan",
                json.dumps(plan),
            ]
        )

    fork.assert_called_once_with(
        source,
        str(tmp_path / "new_case"),
        str(tmp_path / "inputdir"),
        cesmroot="/some/cesm",
        machine="derecho",
        project="PROJ123",
        plan=plan,
    )


def test_duplicate_case_cli(tmp_path):
    mock_case = MagicMock()

    with patch(
        "CrocoDash.shareable.duplicate_case", return_value=mock_case
    ) as mock_duplicate:
        run_main(
            [
                "duplicate",
                "--source",
                "/some/existing/case",
                "--case",
                str(tmp_path / "new_case"),
                "--inputdir",
                str(tmp_path / "inputdir"),
            ]
        )

    mock_duplicate.assert_called_once_with(
        caseroot="/some/existing/case",
        new_caseroot=str(tmp_path / "new_case"),
        new_inputdir=str(tmp_path / "inputdir"),
        bundle_dir=None,
    )
