import json
import sys
from pathlib import Path
from unittest.mock import patch
import nbformat
import pytest

from crocogallery import list_notebooks, load_paths


def run_main(argv):
    with patch.object(sys, "argv", ["crocodash"] + argv):
        from CrocoDash.cli import main

        main()


# --- notebook output ---

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
    # Assert *a* known path was injected (load from source rather than hardcoding)
    derecho_paths = load_paths("derecho")
    assert any(v in code for v in derecho_paths.values()), (
        "Expected at least one derecho path value to appear in output"
    )


# --- .py output ---

def test_template_python_no_machine(tmp_path):
    output = tmp_path / "out.py"
    run_main(["template", "--output", str(output)])
    assert output.exists()
    text = output.read_text()
    assert "<GEBCO>" in text, "Placeholders should remain when --machine is not set"
    assert text.startswith("# %%"), "First cell must start with # %% marker"


def test_template_python_with_machine(tmp_path):
    output = tmp_path / "out.py"
    run_main(["template", "--output", str(output), "--machine", "derecho"])
    assert output.exists()
    text = output.read_text()
    assert "<GEBCO>" not in text
    derecho_paths = load_paths("derecho")
    assert any(v in text for v in derecho_paths.values())
    assert text.startswith("# %%"), "First cell must start with # %% marker"
    assert text.count("# %%") > 1, "Multiple cells should each have a # %% marker"


# --- YAML output ---

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


# --- error handling ---

def test_template_unknown_machine(tmp_path):
    output = tmp_path / "out.ipynb"
    with pytest.raises(KeyError, match="Unknown machine 'bogus'"):
        run_main(["template", "--output", str(output), "--machine", "bogus"])


def test_template_yaml_unknown_machine(tmp_path):
    output = tmp_path / "out.yaml"
    with pytest.raises(KeyError, match="Unknown machine 'bogus'"):
        run_main(["template", "--output", str(output), "--machine", "bogus"])


# --- --notebook flag ---

def test_template_custom_notebook(tmp_path):
    """Any gallery notebook can be used as the template source."""
    notebooks = list_notebooks()
    # pick a notebook other than the default
    alt_id = next(
        nid for nid in sorted(notebooks)
        if nid != "crocodash.tutorials.crocodash_tutorial"
        and notebooks[nid].suffix == ".ipynb"
    )
    output = tmp_path / "out.ipynb"
    run_main(["template", "--output", str(output), "--notebook", alt_id])
    assert output.exists()
    nb = nbformat.read(output, as_version=4)
    assert len(nb.cells) > 0


def test_template_unknown_notebook(tmp_path):
    output = tmp_path / "out.ipynb"
    with pytest.raises(KeyError, match="Unknown notebook"):
        run_main(["template", "--output", str(output), "--notebook", "no.such.notebook"])
