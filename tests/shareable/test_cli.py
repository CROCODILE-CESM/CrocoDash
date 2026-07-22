import sys
import json
from unittest.mock import patch, MagicMock


def run_main(argv):
    with patch.object(sys, "argv", ["crocodash"] + argv):
        from CrocoDash.cli import main

        main()


def test_bundle_cli(tmp_path):
    mock_case = MagicMock()
    mock_case.bundle.return_value = tmp_path / "bundle"

    with patch("CrocoDash.shareable.CaseBundle", return_value=mock_case) as mock_cls:
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

    mock_cls.assert_called_once_with("/some/case")
    mock_case.identify_non_standard_case_info.assert_called_once_with(
        cesmroot="/some/cesm",
        machine="derecho",
        project_number="PROJ123",
    )
    mock_case.bundle.assert_called_once_with(str(tmp_path))


def test_fork_cli(tmp_path):
    mock_forker = MagicMock()
    plan = {
        "xml_files": True,
        "user_nl": False,
        "source_mods": True,
        "xmlchanges": True,
    }

    with patch("CrocoDash.shareable.ForkBundle", return_value=mock_forker):
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

    mock_forker.fork.assert_called_once_with(
        cesmroot="/some/cesm",
        machine="derecho",
        project_number="PROJ123",
        new_caseroot=str(tmp_path / "new_case"),
        new_inputdir=str(tmp_path / "inputdir"),
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
