import json
from unittest.mock import MagicMock, patch

from CrocoDash import case_state
from CrocoDash.forcing.base import ReadCrocoDashCase
from CrocoDash.shareable import (
    BundleDifferences,
    ForkBundle,
    _copy_output_files,
    duplicate_case,
)


def _make_case(tmp_path, forcing_config=None):
    """A caseroot with a state file, and an inputdir with config.json when
    forcing_config is given."""
    caseroot = tmp_path / "case"
    caseroot.mkdir()
    inputdir = tmp_path / "input"
    case_state.write(
        caseroot,
        {
            "inputdir": str(inputdir),
            "supergrid_path": str(inputdir / "ocn" / "hgrid.nc"),
            "topo_path": str(inputdir / "ocn" / "topog.nc"),
            "vgrid_path": str(inputdir / "ocn" / "vgrid.nc"),
        },
    )
    if forcing_config is not None:
        (inputdir / "extract_forcings").mkdir(parents=True)
        (inputdir / "extract_forcings" / "config.json").write_text(
            json.dumps(forcing_config)
        )
    return caseroot, inputdir


def test_read_case_builds_the_workflow_context(tmp_path):
    caseroot, inputdir = _make_case(tmp_path, {"caseroot": "x"})

    case = ReadCrocoDashCase(caseroot)
    ctx = case.workflow_context()

    assert case.forcing_config == {"caseroot": "x"}
    assert ctx.inputdir == inputdir
    assert ctx.output_path == case.ocn_dir == inputdir / "ocn"
    assert ctx.supergrid_path == inputdir / "ocn" / "hgrid.nc"
    assert ctx.raw_data_dir == inputdir / "extract_forcings" / "raw_data"
    assert ctx.regridded_data_dir == inputdir / "extract_forcings" / "regridded_data"
    assert ctx.config == {"caseroot": "x"}
    # Another config.json (crocodash process --config) replaces the case's own.
    assert case.workflow_context({"other": 1}).config == {"other": 1}


def test_read_case_before_configure_forcings(tmp_path):
    caseroot, _ = _make_case(tmp_path)
    assert ReadCrocoDashCase(caseroot).forcing_config == {}


class _Declares:
    """A configurator stand-in that declares an ocn/ file, a glob in ice/ and a
    mapping/ file."""

    def output_files(self, ctx):
        return {
            "x": [
                ctx.output_path / "a.nc",
                ctx.inputdir / "ice" / "*.nc",
                ctx.inputdir / "mapping" / "map.nc",
            ]
        }


def _declaring():
    """Make every case read back from disk report _Declares as its configurator."""
    return patch.object(
        ReadCrocoDashCase, "configurators", lambda self: {"x": _Declares()}
    )


def _write_files(root, rels):
    for rel in rels:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)


def _nc_files(inputdir):
    return sorted(p.relative_to(inputdir).as_posix() for p in inputdir.rglob("*.nc"))


def test_copy_output_files_restores_every_declared_file(tmp_path):
    """Fork and duplicate restore declared files outside ocn/ too (ice/ and
    mapping/ used to be dropped), at the same path under the new inputdir."""
    source = tmp_path / "bundle"
    _write_files(
        source,
        ("ocn/a.nc", "ice/f1.nc", "ice/f2.nc", "ice/notes.txt", "mapping/map.nc"),
    )
    caseroot, inputdir = _make_case(tmp_path, {"caseroot": "x"})
    case = ReadCrocoDashCase(caseroot)
    case.configurators = lambda: {"x": _Declares()}

    _copy_output_files(source, case)

    assert _nc_files(inputdir) == [
        "ice/f1.nc",
        "ice/f2.nc",
        "mapping/map.nc",
        "ocn/a.nc",
    ]
    assert not (inputdir / "ice" / "notes.txt").exists()


def test_fork_restores_grid_and_declared_files(tmp_path):
    bundle = tmp_path / "bundle"
    _write_files(bundle, ("ocn/hgrid.nc", "ocn/a.nc", "ice/f1.nc", "mapping/map.nc"))
    caseroot, inputdir = _make_case(tmp_path, {"caseroot": "x"})
    (inputdir / "ocn").mkdir()
    new_case = MagicMock(caseroot=caseroot)
    # Skip the interactive review; only the file restore is under test.
    fork = ForkBundle.__new__(ForkBundle)
    fork.bundle_location = bundle
    fork._configure_yaml_for_forked_case_args = lambda *args: {}
    fork._guide_yaml_review = lambda config: config
    fork._resolve_copy_plan = lambda plan: None
    fork.apply_copy_plan = lambda: None

    with patch(
        "CrocoDash.shareable.create_case_from_yaml", return_value=new_case
    ), _declaring():
        assert fork.fork("cesm", "machine", "project", caseroot, inputdir) is new_case

    assert _nc_files(inputdir) == [
        "ice/f1.nc",
        "mapping/map.nc",
        "ocn/a.nc",
        "ocn/hgrid.nc",
    ]
    new_case.validate_case.assert_called_once()


def test_duplicate_case_restores_grid_and_declared_files(tmp_path):
    old_inputdir = tmp_path / "old"
    _write_files(old_inputdir, ("ocn/hgrid.nc", "ice/grid.nc", "mapping/map.nc"))
    source = MagicMock(
        inputdir=old_inputdir,
        ocn_dir=old_inputdir / "ocn",
        case_yaml={"case": {}},
        non_standard_case_info=BundleDifferences(),
    )
    caseroot, inputdir = _make_case(tmp_path, {"caseroot": "x"})
    new_case = MagicMock(caseroot=caseroot)

    with patch("CrocoDash.shareable.CaseBundle", return_value=source), patch(
        "CrocoDash.shareable.create_case_from_yaml", return_value=new_case
    ), _declaring():
        assert duplicate_case("old_case", caseroot, inputdir) is new_case

    # ocn/ and ice/ come over whole; mapping/ only because it is declared.
    assert _nc_files(inputdir) == ["ice/grid.nc", "mapping/map.nc", "ocn/hgrid.nc"]
