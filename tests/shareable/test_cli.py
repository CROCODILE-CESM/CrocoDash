import sys
import json
from unittest.mock import patch, MagicMock


def run_main(argv):
    with patch.object(sys, "argv", ["crocodash"] + argv):
        from CrocoDash.cli import main

        main()


def test_read_cli(tmp_path):
    mock_case = MagicMock()
    mock_case.bundle.return_value = tmp_path / "bundle"

    with patch(
        "CrocoDash.shareable.inspect.ReadCrocoDashCase", return_value=mock_case
    ) as mock_cls:
        run_main(
            [
                "read",
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
    mock_case.identify_non_standard_CrocoDash_case_information.assert_called_once_with(
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
    args_file = tmp_path / "args.json"

    with patch(
        "CrocoDash.shareable.fork.ForkCrocoDashBundle", return_value=mock_forker
    ):
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
                "--compset",
                "GOMOM6",
                "--extra-configs",
                "tides,bgc",
                "--remove-configs",
                "runoff",
                "--extra-forcing-args",
                str(args_file),
            ]
        )

    mock_forker.fork.assert_called_once_with(
        plan=plan,
        compset="GOMOM6",
        extra_configs=["tides", "bgc"],
        remove_configs=["runoff"],
        extra_forcing_args_path=str(args_file),
    )


def test_clone_cli(tmp_path):
    mock_case = MagicMock()

    with patch(
        "CrocoDash.shareable.inspect.clone", return_value=mock_case
    ) as mock_clone:
        run_main(
            [
                "clone",
                "--clone",
                "/some/existing/case",
                "--case",
                str(tmp_path / "new_case"),
                "--inputdir",
                str(tmp_path / "inputdir"),
            ]
        )

    mock_clone.assert_called_once_with(
        caseroot="/some/existing/case",
        new_caseroot=str(tmp_path / "new_case"),
        new_inputdir=str(tmp_path / "inputdir"),
        bundle_dir=None,
    )
