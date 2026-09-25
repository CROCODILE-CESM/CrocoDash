"""CrocoDash-managed user_nl blocks (forcing/user_nl_blocks.py): a rerun of
configure_forcings() replaces its own entries and nothing else."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from ProConPy.config_var import cvars

from CrocoDash.forcing import user_nl_blocks
from tests.user_nl_helpers import keys as _keys, mom_parser

# What case creation writes outside any block (visualCaseGen, then
# Case._set_ww3_timesteps / _set_cice_ndtd).
CREATION = {
    "mom": "INPUTDIR = /inputdir/ocn\nNIGLOBAL = 10\n",
    "ww3": "\n! WW3 time steps scaled to the grid\ndtmax = 1800\ndtcfl = 450\n",
    "cice": "\n! CICE dynamics substeps\nndtd = 3\n",
}

IC = ("Initial conditions", [("INIT_LAYERS_FROM_Z_FILE", "True")])
OBC4 = (
    "Open boundary conditions",
    [("OBC_NUMBER_OF_SEGMENTS", 4)]
    + [(f"OBC_SEGMENT_00{i}_DATA", f'"seg {i}"') for i in range(1, 5)],
)
OBC3 = (
    "Open boundary conditions",
    [("OBC_NUMBER_OF_SEGMENTS", 3)]
    + [(f"OBC_SEGMENT_00{i}_DATA", f'"seg {i}"') for i in range(1, 4)],
)


@pytest.fixture
def caseroot(tmp_path, monkeypatch):
    monkeypatch.setitem(cvars, "CASEROOT", SimpleNamespace(value=tmp_path))
    monkeypatch.setitem(cvars, "NINST", SimpleNamespace(value=1))
    for model, text in CREATION.items():
        (tmp_path / f"user_nl_{model}").write_text(text)
    return tmp_path


def _configure(caseroot, obc=OBC4, tides=True):
    """One configure_forcings() call's worth of writes."""
    edited = user_nl_blocks.strip(caseroot)
    user_nl_blocks.write("conditions", "mom", [IC, obc])
    if tides:
        user_nl_blocks.write("tides", "mom", [("Tides", [("TIDES", "True")])])
    user_nl_blocks.write("CICE", "cice", [(None, [("ice_ic", "'default'")])])
    user_nl_blocks.report_edits(caseroot, edited)


def _files(caseroot):
    return {p.name: p.read_text() for p in sorted(caseroot.glob("user_nl_*"))}


def test_rerun_with_the_same_entries_changes_nothing(caseroot):
    _configure(caseroot)
    once = _files(caseroot)
    _configure(caseroot)
    assert _files(caseroot) == once
    for text in once.values():
        assert len(_keys(text)) == len(set(_keys(text)))


def test_strip_restores_the_creation_entries_exactly(caseroot):
    _configure(caseroot)
    user_nl_blocks.strip(caseroot)
    assert _files(caseroot) == {f"user_nl_{m}": t for m, t in sorted(CREATION.items())}


def test_rerun_drops_what_it_no_longer_writes(caseroot):
    _configure(caseroot, obc=OBC4, tides=True)
    _configure(caseroot, obc=OBC3, tides=False)
    mom = (caseroot / "user_nl_mom").read_text()
    assert "OBC_SEGMENT_004" not in mom
    assert "TIDES" not in mom
    assert _keys(mom).count("OBC_NUMBER_OF_SEGMENTS") == 1
    assert "OBC_NUMBER_OF_SEGMENTS = 3" in mom


def test_user_lines_outside_the_blocks_survive_and_win(caseroot, capsys):
    _configure(caseroot)
    with open(caseroot / "user_nl_mom", "a") as f:
        f.write('LAYOUT = 31, 2\nobc_segment_001_data = "mine"\n')
    _configure(caseroot)

    mom = (caseroot / "user_nl_mom").read_text()
    assert mom.startswith(CREATION["mom"])
    assert "LAYOUT = 31, 2" in mom
    # The user's value is the only one, so MOM6 sees no duplicate.
    assert [k.upper() for k in _keys(mom)].count("OBC_SEGMENT_001_DATA") == 1
    assert 'obc_segment_001_data = "mine"' in mom
    assert (
        "OBC_SEGMENT_001_DATA: set outside CrocoDash's block" in capsys.readouterr().out
    )
    for model in ("ww3", "cice"):
        assert (caseroot / f"user_nl_{model}").read_text().startswith(CREATION[model])


def test_hand_edits_inside_a_block_are_replaced_with_a_warning(caseroot, capsys):
    _configure(caseroot)
    path = caseroot / "user_nl_mom"
    path.write_text(path.read_text().replace('"seg 2"', '"edited"'))
    capsys.readouterr()

    _configure(caseroot)
    out = capsys.readouterr().out
    assert "user_nl_mom was edited inside CrocoDash's 'conditions' block" in out
    assert 'OBC_SEGMENT_002_DATA = "edited"' in out
    assert '"seg 2"' in path.read_text() and '"edited"' not in path.read_text()


def test_a_deleted_line_inside_a_block_is_reported_when_written_back(caseroot, capsys):
    _configure(caseroot)
    path = caseroot / "user_nl_mom"
    path.write_text(path.read_text().replace('OBC_SEGMENT_002_DATA = "seg 2"\n', ""))
    capsys.readouterr()

    _configure(caseroot)
    out = capsys.readouterr().out
    assert "Written back:" in out and 'OBC_SEGMENT_002_DATA = "seg 2"' in out


def test_unedited_blocks_give_no_warning(caseroot, capsys):
    _configure(caseroot)
    _configure(caseroot, obc=OBC3)
    assert "WARNING" not in capsys.readouterr().out


def test_every_instance_file_is_managed(tmp_path, monkeypatch):
    monkeypatch.setitem(cvars, "CASEROOT", SimpleNamespace(value=tmp_path))
    monkeypatch.setitem(cvars, "NINST", SimpleNamespace(value=2))
    for _ in range(2):
        user_nl_blocks.strip(tmp_path)
        user_nl_blocks.write("conditions", "mom", [IC])
    for name in ("user_nl_mom_0001", "user_nl_mom_0002"):
        assert _keys((tmp_path / name).read_text()) == ["INIT_LAYERS_FROM_Z_FILE"]


def test_a_block_without_its_end_line_is_an_error(caseroot):
    _configure(caseroot)
    path = caseroot / "user_nl_mom"
    path.write_text(
        path.read_text().replace("! <<< CrocoDash configure_forcings: conditions\n", "")
    )
    with pytest.raises(RuntimeError, match="'conditions' block has no"):
        user_nl_blocks.strip(caseroot)


def test_stream_mods_set_outside_win_whatever_the_spacing(caseroot):
    """CDEPS reads "stream : key" like "stream:key" and applies the last line,
    so an override spelled with spaces must still keep CrocoDash's line out."""
    path = caseroot / "user_nl_datm_streams"
    path.write_text("CORE_IAF_JRA.PREC : year_first = 2000\n")
    pairs = [
        ("CORE_IAF_JRA.PREC:year_first", 2014),
        ("CORE_IAF_JRA.PREC:year_last", 2015),
    ]
    user_nl_blocks.write("StreamYears", "datm_streams", [("Align", pairs)])
    text = path.read_text()
    assert "year_first = 2014" not in text
    assert "CORE_IAF_JRA.PREC:year_last = 2015" in text


def test_each_instance_file_keeps_its_own_overrides(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(cvars, "CASEROOT", SimpleNamespace(value=tmp_path))
    monkeypatch.setitem(cvars, "NINST", SimpleNamespace(value=2))
    (tmp_path / "user_nl_mom_0002").write_text("INIT_LAYERS_FROM_Z_FILE = False\n")
    user_nl_blocks.write("conditions", "mom", [IC])
    assert _keys((tmp_path / "user_nl_mom_0001").read_text()) == [
        "INIT_LAYERS_FROM_Z_FILE"
    ]
    assert (tmp_path / "user_nl_mom_0002").read_text() == (
        "INIT_LAYERS_FROM_Z_FILE = False\n"
    )
    assert (
        "set outside CrocoDash's block in user_nl_mom_0002" in capsys.readouterr().out
    )


def test_restore_undoes_a_failed_call(caseroot):
    _configure(caseroot)
    before = _files(caseroot)
    contents = user_nl_blocks.snapshot(caseroot)
    user_nl_blocks.strip(caseroot)
    user_nl_blocks.write("conditions", "mom", [IC, OBC3])
    user_nl_blocks.write("StreamYears", "datm_streams", [(None, [("s:year_first", 1)])])
    user_nl_blocks.restore(caseroot, contents)
    assert _files(caseroot) == before


def test_marker_lines_are_comments_to_cime_and_mom(
    caseroot, get_cesm_root_path, monkeypatch
):
    """CIME's namelist parser (user_nl_cice, user_nl_ww3) and MOM_interface's
    (user_nl_mom, which also rejects any variable listed twice) both read a
    managed file. CDEPS's stream-mod parser skips every line starting with "!"."""
    cesmroot = Path(get_cesm_root_path)
    if not (cesmroot / "cime/CIME/namelist.py").exists():
        pytest.skip("no CESM checkout with CIME")
    monkeypatch.syspath_prepend(str(cesmroot / "cime"))
    from CIME.namelist import parse

    FType_MOM_params = mom_parser(cesmroot)
    if FType_MOM_params is None:
        pytest.skip("no MOM_interface in this CESM checkout")

    _configure(caseroot)
    _configure(caseroot)

    cice = parse(text=(caseroot / "user_nl_cice").read_text(), groupless=True)
    assert set(cice) == {"ndtd", "ice_ic"}

    params = FType_MOM_params.from_MOM_input(str(caseroot / "user_nl_mom"))
    assert set(params._data["Global"]) == {
        "INPUTDIR",
        "NIGLOBAL",
        "INIT_LAYERS_FROM_Z_FILE",
        "OBC_NUMBER_OF_SEGMENTS",
        *(f"OBC_SEGMENT_00{i}_DATA" for i in range(1, 5)),
        "TIDES",
    }
