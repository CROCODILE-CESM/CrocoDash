import sys
from unittest.mock import patch, MagicMock
import nbformat
import pytest


def run_main(argv):
    with patch.object(sys, "argv", ["crocodash"] + argv):
        from CrocoDash.cli import main

        main()


def test_template_notebook_no_machine(tmp_path):
    output = tmp_path / "out.ipynb"
    run_main(["template", "--output", str(output)])
    assert output.exists()
    nb = nbformat.read(output, as_version=4)
    code = "\n".join(c.source for c in nb.cells if c.cell_type == "code")
    assert "<GEBCO>" in code, "Placeholders should remain when --machine is not set"


def test_template_notebook_with_machine(tmp_path):
    output = tmp_path / "out.ipynb"
    run_main(["template", "--output", str(output), "--machine", "derecho"])
    assert output.exists()
    nb = nbformat.read(output, as_version=4)
    code = "\n".join(c.source for c in nb.cells if c.cell_type == "code")
    assert "<GEBCO>" not in code, "Placeholders should be replaced with --machine"
    assert "/glade/campaign" in code


def test_template_python_with_machine(tmp_path):
    output = tmp_path / "out.py"
    run_main(["template", "--output", str(output), "--machine", "derecho"])
    assert output.exists()
    text = output.read_text()
    assert "<GEBCO>" not in text
    assert "/glade/campaign" in text
    # Cells should be separated by # %% markers
    assert "# %%" in text


def test_template_unknown_machine(tmp_path):
    output = tmp_path / "out.ipynb"
    with pytest.raises(KeyError, match="Unknown machine 'bogus'"):
        run_main(["template", "--output", str(output), "--machine", "bogus"])


def test_template_yaml_no_machine(tmp_path):
    import yaml

    output = tmp_path / "out.yaml"
    run_main(["template", "--output", str(output)])
    assert output.exists()
    text = output.read_text()
    assert "<CESM>" in text, "Placeholders should remain when --machine is not set"
    config = yaml.safe_load(text)
    assert isinstance(config, dict)


def test_template_yaml_with_machine(tmp_path):
    import yaml

    output = tmp_path / "out.yaml"
    run_main(["template", "--output", str(output), "--machine", "derecho"])
    assert output.exists()
    text = output.read_text()
    assert "<CESM>" not in text, "Placeholders should be replaced with --machine"
    config = yaml.safe_load(text)
    assert isinstance(config, dict)


def test_template_yaml_unknown_machine(tmp_path):
    output = tmp_path / "out.yaml"
    with pytest.raises(KeyError, match="Unknown machine 'bogus'"):
        run_main(["template", "--output", str(output), "--machine", "bogus"])
