import json
import sys
from pathlib import Path
from unittest.mock import patch
import nbformat
import pytest

from crocogallery import list_notebooks, load_paths
from crocogallery.template import DEFAULT_TEMPLATE_NOTEBOOK_ID


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
    assert any(
        v in code for v in derecho_paths.values()
    ), "Expected at least one derecho path value to appear in output"


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


def test_template_python_is_valid_python(tmp_path):
    # The tutorial notebook has IPython magic cells (e.g. `%matplotlib ipympl`)
    # which must be commented out, or the .py output fails to even parse.
    import py_compile

    for extra_args in ([], ["--machine", "derecho"]):
        output = tmp_path / f"out_{len(extra_args)}.py"
        run_main(["template", "--output", str(output)] + extra_args)
        py_compile.compile(str(output), doraise=True)


def test_template_machine_leaves_non_path_keys_as_placeholders(tmp_path):
    # CESM/inputdir/casedir in known_paths.json hold placeholder tokens
    # ("Checkout", "fill_in_id", "fill_in_cd"), not real paths -- injecting
    # them is worse than leaving <KEY> since nothing then signals they still
    # need manual editing.
    output = tmp_path / "out.yaml"
    run_main(["template", "--output", str(output), "--machine", "derecho"])
    text = output.read_text()
    assert "<CESM>" in text
    assert "<inputdir>" in text
    assert "<casedir>" in text
    for bogus in ("Checkout", "fill_in_id", "fill_in_cd"):
        assert bogus not in text


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
    assert "<GEBCO>" not in text, "Dataset path placeholders should be replaced"
    # CESM/inputdir/casedir are not real paths in known_paths.json (see
    # test_template_machine_leaves_non_path_keys_as_placeholders) and are
    # deliberately left as placeholders even with --machine set.
    assert "<CESM>" in text
    config = yaml.safe_load(text)
    assert isinstance(config, dict)


# --- .pbs output ---


def test_template_pbs_no_machine(tmp_path):
    output = tmp_path / "out.pbs"
    run_main(["template", "--output", str(output), "--kind", "pbs"])
    assert output.exists()
    text = output.read_text()
    assert (
        "<PROJECT_CODE>" in text
    ), "Placeholders should remain when --machine is not set"
    assert text.startswith("#!/bin/bash"), "Output should be a shell script"
    assert output.stat().st_mode & 0o111, "Output should be executable"


def test_template_pbs_with_machine(tmp_path):
    output = tmp_path / "out.pbs"
    run_main(
        ["template", "--output", str(output), "--kind", "pbs", "--machine", "derecho"]
    )
    assert output.exists()
    text = output.read_text()
    # submit_forcings.pbs has no known_paths.json keys, so --machine is a no-op
    # on its content, but must not error and must still write the file.
    assert "<PROJECT_CODE>" in text
    assert text.startswith("#!/bin/bash")


def test_template_pbs_suffix_dispatches_without_kind_flag(tmp_path):
    # A .pbs output suffix selects the PBS template on its own, the same way
    # .yaml/.ipynb already dispatch by suffix -- --kind pbs is only needed to
    # use a different filename.
    output = tmp_path / "out.pbs"
    run_main(["template", "--output", str(output)])
    assert output.exists()
    text = output.read_text()
    assert text.startswith("#!/bin/bash")
    assert output.stat().st_mode & 0o111, "Output should be executable"


# --- error handling ---


def test_template_unknown_machine(tmp_path, capsys):
    output = tmp_path / "out.ipynb"
    with pytest.raises(SystemExit) as exc_info:
        run_main(["template", "--output", str(output), "--machine", "bogus"])
    assert exc_info.value.code == 1
    assert "Unknown machine 'bogus'" in capsys.readouterr().err


def test_template_yaml_unknown_machine(tmp_path, capsys):
    output = tmp_path / "out.yaml"
    with pytest.raises(SystemExit) as exc_info:
        run_main(["template", "--output", str(output), "--machine", "bogus"])
    assert exc_info.value.code == 1
    assert "Unknown machine 'bogus'" in capsys.readouterr().err


# --- --notebook flag ---


def test_template_custom_notebook(tmp_path):
    """Any gallery notebook can be used as the template source."""
    notebooks = list_notebooks()
    # pick a notebook other than the default -- list_notebooks() only ever
    # returns .ipynb paths, so no suffix filter is needed here
    alt_id = next(
        (
            nid
            for nid in sorted(notebooks)
            if nid != "crocodash.tutorials.crocodash_tutorial"
        ),
        None,
    )
    if alt_id is None:
        pytest.skip("Gallery has no notebook other than the default tutorial.")
    output = tmp_path / "out.ipynb"
    run_main(["template", "--output", str(output), "--notebook", alt_id])
    assert output.exists()
    nb = nbformat.read(output, as_version=4)
    assert len(nb.cells) > 0


def test_template_unknown_notebook(tmp_path, capsys):
    output = tmp_path / "out.ipynb"
    with pytest.raises(SystemExit) as exc_info:
        run_main(
            ["template", "--output", str(output), "--notebook", "no.such.notebook"]
        )
    assert exc_info.value.code == 1
    assert "Unknown notebook" in capsys.readouterr().err


def test_template_list_notebooks(capsys):
    run_main(["template", "--list-notebooks"])
    out = capsys.readouterr().out
    # Assert against the constant, not a hardcoded string: a default that is
    # not actually a listed notebook breaks every no---notebook invocation.
    assert DEFAULT_TEMPLATE_NOTEBOOK_ID in out


def test_template_missing_output_without_list_notebooks(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        run_main(["template"])
    assert exc_info.value.code == 2


def test_template_creates_missing_output_parent_dir(tmp_path):
    output = tmp_path / "nested" / "dir" / "out.ipynb"
    run_main(["template", "--output", str(output)])
    assert output.exists()


def test_template_python_preserves_markdown_cells(tmp_path):
    output = tmp_path / "out.py"
    run_main(["template", "--output", str(output)])
    text = output.read_text()
    assert (
        "# %% [markdown]" in text
    ), "Markdown cells should be preserved as jupytext blocks"


def test_template_yaml_ignores_custom_notebook(tmp_path, capsys):
    """starter_case.yaml only lives next to the default tutorial notebook --
    a non-default --notebook must not error, just be ignored with a notice."""
    output = tmp_path / "out.yaml"
    run_main(
        [
            "template",
            "--output",
            str(output),
            "--notebook",
            "crocodash.features.add_chl",
        ]
    )
    assert output.exists()
    assert "ignored" in capsys.readouterr().out
