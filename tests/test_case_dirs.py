"""Tests for CaseDirs: replacing a case's directories without losing the previous case."""

from CrocoDash.case_dirs import CaseDirs


def _make(path, text):
    path.mkdir()
    (path / "marker").write_text(text)


def test_override_restores_the_previous_case_when_the_new_one_fails(tmp_path, capsys):
    inputdir, caseroot = tmp_path / "inputdir", tmp_path / "case"
    _make(inputdir, "old input")
    _make(caseroot, "old case")

    dirs = CaseDirs([inputdir, caseroot, tmp_path / "bld_run"], override=True)
    assert not inputdir.exists() and not caseroot.exists()
    _make(inputdir, "half-made")  # what the failed attempt wrote
    dirs.undo()

    assert (inputdir / "marker").read_text() == "old input"
    assert (caseroot / "marker").read_text() == "old case"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["case", "inputdir"]
    assert f"Restored previous case files: {inputdir}" in capsys.readouterr().out


def test_override_removes_the_previous_case_once_the_new_one_is_complete(
    tmp_path, capsys
):
    caseroot = tmp_path / "case"
    _make(caseroot, "old case")
    dirs = CaseDirs([caseroot], override=True)
    _make(caseroot, "new case")
    dirs.discard_previous()

    assert (caseroot / "marker").read_text() == "new case"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["case"]
    out = capsys.readouterr().out
    assert f"Moving previous case files aside: {caseroot}" in out
    assert f"Removing previous case files: {caseroot}" in out


def test_without_override_a_failed_attempt_leaves_preexisting_dirs_alone(tmp_path):
    """The build/run dir may be an earlier case's, left behind (M2);
    create_newcase refuses it, and it is not this attempt's to delete."""
    bld_run, caseroot = tmp_path / "bld_run", tmp_path / "case"
    _make(bld_run, "earlier run")
    dirs = CaseDirs([caseroot, bld_run], override=False)
    _make(caseroot, "half-made")
    dirs.undo()

    assert not caseroot.exists()
    assert (bld_run / "marker").read_text() == "earlier run"


def test_a_caseroot_that_is_also_the_build_run_dir_is_handled_once(tmp_path):
    """On derecho, a caseroot placed straight in scratch is the build/run
    dir too; moving it aside twice raised before anything was created."""
    caseroot = tmp_path / "case"
    _make(caseroot, "old case")
    dirs = CaseDirs([tmp_path / "inputdir", caseroot, caseroot], override=True)
    _make(caseroot, "half-made")
    dirs.undo()
    assert (caseroot / "marker").read_text() == "old case"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["case"]


def test_a_caseroot_nested_in_the_inputdir_goes_aside_with_it(tmp_path):
    inputdir = tmp_path / "inputdir"
    _make(inputdir, "old input")
    _make(inputdir / "case", "old case")
    dirs = CaseDirs([inputdir, inputdir / "case"], override=True)
    _make(inputdir, "half-made input")
    _make(inputdir / "case", "half-made case")
    dirs.undo()
    assert (inputdir / "marker").read_text() == "old input"
    assert (inputdir / "case" / "marker").read_text() == "old case"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["inputdir"]


def test_undo_restores_the_rest_when_one_path_cannot_be_removed(
    tmp_path, monkeypatch, capsys
):
    import shutil

    inputdir, caseroot = tmp_path / "inputdir", tmp_path / "case"
    _make(inputdir, "old input")
    _make(caseroot, "old case")
    dirs = CaseDirs([inputdir, caseroot], override=True)
    _make(inputdir, "half-made")
    _make(caseroot, "half-made")

    real_rmtree = shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if path == inputdir:
            raise PermissionError("busy")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("CrocoDash.case_dirs.shutil.rmtree", rmtree)
    dirs.undo()
    assert (caseroot / "marker").read_text() == "old case"
    out = capsys.readouterr().out
    assert f"Could not remove {inputdir}: busy" in out
    assert f"Could not restore {inputdir}; the previous copy is at" in out


def test_a_symlinked_alias_of_the_same_dir_is_moved_once(tmp_path):
    """~/sch -> scratch: caseroot and build/run dir are one dir reached
    through different paths, which comparing them cannot tell."""
    real = tmp_path / "scratch"
    real.mkdir()
    (tmp_path / "sch").symlink_to(real)
    _make(real / "case", "old case")

    dirs = CaseDirs([tmp_path / "sch" / "case", real / "case"], override=True)
    assert not (real / "case").exists()
    _make(real / "case", "half-made")
    dirs.undo()
    assert (real / "case" / "marker").read_text() == "old case"
    assert sorted(p.name for p in real.iterdir()) == ["case"]

    dirs = CaseDirs([tmp_path / "sch" / "case", real / "case"], override=True)
    _make(real / "case", "new case")
    dirs.discard_previous()
    assert (real / "case" / "marker").read_text() == "new case"
    assert sorted(p.name for p in real.iterdir()) == ["case"]
