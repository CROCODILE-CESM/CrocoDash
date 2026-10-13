import json

from CrocoDash import case_state
from CrocoDash.forcing.base import ReadCrocoDashCase


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
