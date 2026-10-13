import json

from CrocoDash import case_state
from CrocoDash.forcing.base import ReadCrocoDashCase
from CrocoDash.shareable import _copy_output_files


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
    """A configurator stand-in that declares an ocn/ file and a glob in ice/."""

    def output_files(self, ctx):
        return {"x": [ctx.output_path / "a.nc", ctx.inputdir / "ice" / "*.nc"]}


def test_copy_output_files_restores_every_declared_file(tmp_path):
    """Fork and duplicate restore declared files outside ocn/ too (ice/ and
    mapping/ used to be dropped), at the same path under the new inputdir."""
    source = tmp_path / "bundle"
    for rel in ("ocn/a.nc", "ice/f1.nc", "ice/f2.nc", "ice/notes.txt"):
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_text(rel)
    caseroot, inputdir = _make_case(tmp_path, {"caseroot": "x"})
    case = ReadCrocoDashCase(caseroot)
    case.configurators = lambda: {"x": _Declares()}

    _copy_output_files(source, case)

    copied = sorted(p.relative_to(inputdir).as_posix() for p in inputdir.rglob("*.nc"))
    assert copied == ["ice/f1.nc", "ice/f2.nc", "ocn/a.nc"]
    assert not (inputdir / "ice" / "notes.txt").exists()
