"""Rerunning Case.configure_forcings() on the same case -- as a notebook cell
rerun does -- leaves the case as if only the latest call had happened."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import xarray as xr
from ProConPy.config_var import cvars

from CrocoDash.forcing import mom6, obc, tides
from tests.user_nl_helpers import keys as _keys, mom_parser

COMPSET = "2000_DATM%JRA_SLND_CICE%PRES_MOM6_SROF_SGLC_SWAV"
DATES = ["2015-01-01 00:00:00", "2015-01-11 00:00:00"]
TIDES = dict(
    tidal_constituents=["M2"],
    tpxo_elevation_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/h_tpxo9.v1.zarr/",
    tpxo_velocity_filepath="s3://crocodile-cesm/CrocoDash/data/tpxo/u_tpxo9.v1.zarr/",
)
RESTORE = dict(
    restore_ice=True,
    cice_product_name="reference_ice",
    cice_function_name="get_reference_ice_data",
)


@pytest.fixture(scope="module")
def case(CrocoDash_case_factory, tmp_path_factory):
    return CrocoDash_case_factory(tmp_path_factory.mktemp("rerun"), compset=COMPSET)


def _user_nl(case):
    return {p.name: p.read_text() for p in sorted(case.caseroot.glob("user_nl_*"))}


def _read_with_mom_parser(case):
    """user_nl_mom as MOM_interface reads it at build time; it exits on any
    variable listed twice. (Creating the case put CIME on sys.path.)"""
    FType_MOM_params = mom_parser(case.cesmroot)
    if FType_MOM_params is not None:
        FType_MOM_params.from_MOM_input(str(case.caseroot / "user_nl_mom"))


def _write_forcing_outputs(case):
    """Stand-ins for the IC and merged OBC files process_forcings() writes."""
    ocn = case.inputdir / "ocn"
    ic = [ocn / f"init_{name}.nc" for name in ("eta", "vel", "tracers")]
    ic_filled = [ocn / f"init_{name}_filled.nc" for name in ("eta", "vel", "tracers")]
    merged = ocn / "forcing_obc_segment_001.nc"
    for path in ic + ic_filled + [merged]:
        xr.Dataset({"a": ("x", [1.0])}).to_netcdf(path)
    return ic, ic_filled, merged


def test_the_same_call_twice_is_one_call(case):
    case.configure_forcings(date_range=DATES, **TIDES, **RESTORE)
    once = _user_nl(case)
    case.configure_forcings(date_range=DATES, **TIDES, **RESTORE)

    assert _user_nl(case) == once
    assert {"user_nl_mom", "user_nl_cice", "user_nl_datm_streams"} <= set(once)
    for name, text in once.items():
        keys = [key.lower() for key in _keys(text)]
        assert len(keys) == len(set(keys)), name
    _read_with_mom_parser(case)


def test_dropping_a_boundary_drops_its_segment(case):
    case.configure_forcings(date_range=DATES)
    case.configure_forcings(date_range=DATES, boundaries=["south", "north", "west"])

    mom = (case.caseroot / "user_nl_mom").read_text()
    assert "OBC_SEGMENT_004" not in mom
    assert _keys(mom).count("OBC_NUMBER_OF_SEGMENTS") == 1
    assert "OBC_NUMBER_OF_SEGMENTS = 3" in mom


def test_dropping_tides_and_ice_restoring_drops_their_entries(case):
    case.configure_forcings(date_range=DATES, **TIDES, **RESTORE)
    mom = (case.caseroot / "user_nl_mom").read_text()
    cice = (case.caseroot / "user_nl_cice").read_text()
    assert "TIDES" in _keys(mom) and "Uamp=file:tu_segment_001.nc" in mom
    assert "restore_ice" in _keys(cice)

    case.configure_forcings(date_range=DATES)
    mom = (case.caseroot / "user_nl_mom").read_text()
    cice = (case.caseroot / "user_nl_cice").read_text()
    assert not [key for key in _keys(mom) if "TIDE" in key]
    assert "tu_segment" not in mom
    assert not [key for key in _keys(cice) if key.startswith("restore_")]
    assert "ice_ic = 'default'" in cice


def test_user_and_case_creation_entries_survive(case):
    case.configure_forcings(date_range=DATES)
    mom_path = case.caseroot / "user_nl_mom"
    before = mom_path.read_text()
    user_lines = (
        "LAYOUT = 31, 2\nOBC_SEGMENT_001_VELOCITY_NUDGING_TIMESCALES = 0.5, 100.0\n"
    )
    mom_path.write_text(before + user_lines)
    try:
        case.configure_forcings(date_range=DATES)
        mom = mom_path.read_text()
        keys = _keys(mom)
        for key in (
            "INPUTDIR",
            "LAYOUT",
            "OBC_SEGMENT_001_VELOCITY_NUDGING_TIMESCALES",
        ):
            assert keys.count(key) == 1, key
        assert "OBC_SEGMENT_001_VELOCITY_NUDGING_TIMESCALES = 0.5, 100.0" in mom
        assert _keys((case.caseroot / "user_nl_cice").read_text()).count("ndtd") == 1
        _read_with_mom_parser(case)
    finally:
        mom_path.write_text(mom_path.read_text().replace(user_lines, ""))


def test_a_new_date_range_regenerates_the_ic_and_obcs(case):
    """process_ic/process_bc skip any final file that exists; configure_forcings()
    has to remove the ones made for another configuration."""
    case.configure_forcings(date_range=DATES)
    ic, ic_filled, merged = _write_forcing_outputs(case)
    ocn = merged.parent

    # Same arguments, or only tides toggled: process_forcings() still skips them.
    case.configure_forcings(date_range=DATES)
    case.configure_forcings(date_range=DATES, **TIDES)
    assert mom6._all_written(ic) and mom6._all_written(ic_filled)
    assert obc._merge_boundary("001", [], ocn) == merged

    # New dates: they're gone, so process_forcings() makes them again.
    case.configure_forcings(date_range=["2015-01-02 00:00:00", "2015-01-11 00:00:00"])
    assert not mom6._all_written(ic) and not mom6._all_written(ic_filled)
    assert not merged.exists()


def test_a_failed_call_leaves_the_case_as_it_was(case, monkeypatch):
    """A configurator that raises after others have written their blocks: the
    user_nl files and config.json stay as the previous call left them, so the
    next call still knows what the existing forcing files were made from."""
    case.configure_forcings(date_range=DATES, **TIDES)
    _write_forcing_outputs(case)
    config_path = case.inputdir / "extract_forcings" / "config.json"
    user_nl, config = _user_nl(case), config_path.read_text()

    def fail(self):
        raise RuntimeError("configure() failed")

    monkeypatch.setattr(tides.TidesConfigurator, "configure", fail)
    with pytest.raises(RuntimeError, match=r"configure\(\) failed"):
        case.configure_forcings(
            date_range=["2015-01-02 00:00:00", "2015-01-11 00:00:00"],
            boundaries=["south", "north"],
            **TIDES,
        )
    assert _user_nl(case) == user_nl
    assert config_path.read_text() == config
    assert (case.inputdir / "ocn" / "init_eta_filled.nc").exists()


def test_refuses_to_write_into_a_case_created_later(case, monkeypatch, tmp_path):
    """Every case created in a session repoints visualCaseGen's CASEROOT, which
    append_user_nl and xmlchange write into -- so configuring an earlier case
    used to change the later one."""
    user_nl = _user_nl(case)
    config = json.loads((case.inputdir / "extract_forcings/config.json").read_text())
    monkeypatch.setitem(cvars, "CASEROOT", SimpleNamespace(value=str(tmp_path)))
    with pytest.raises(RuntimeError, match="created after it in this session"):
        case.configure_forcings(date_range=DATES)
    assert _user_nl(case) == user_nl
    assert (
        json.loads((case.inputdir / "extract_forcings/config.json").read_text())
        == config
    )
