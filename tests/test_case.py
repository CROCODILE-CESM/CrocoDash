import os
import datetime as dt
import os
import pytest
from uuid import uuid4


def file_with_prefix_exists(directory, prefix):
    for filename in os.listdir(directory):
        if filename.startswith(prefix):
            return True
    return False


def test_case_init_and_create_grid_input(get_CrocoDash_case):
    case = get_CrocoDash_case
    assert case is not None
    assert os.path.exists(case.caseroot)
    assert os.path.exists(case.inputdir)
    assert file_with_prefix_exists(case.inputdir / "ocn", "ocean_hgrid")
    assert file_with_prefix_exists(case.caseroot, "README")

    files = [
        f
        for f in os.listdir(case.inputdir / "ocn")
        if f.startswith(f"ocean_hgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocn")
        if f.startswith(f"ocean_topog_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocn")
        if f.startswith(f"ocean_vgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocn")
        if f.startswith(f"scrip_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocn")
        if f.startswith(f"ESMF_mesh_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    if "CICE" in case.compset_lname:
        files = [
            f
            for f in os.listdir(case.inputdir / "ice")
            if f.startswith(f"cice_grid_{case.ocn_grid.name}")
        ]
        assert len(files) > 0


def test_configure_forcings(get_case_with_cf):
    case = get_case_with_cf
    assert case.expt is not None
    assert case.date_range[0].year == 2020
    assert case.boundaries == ["north", "east"]
    search_string = "OBC_NUMBER_OF_SEGMENTS"
    with open(case.caseroot / "user_nl_mom", "r", encoding="utf-8") as file:
        for line in file:
            if search_string in line:
                found_user_nl_mom_adjusted_var = True
                break
    assert found_user_nl_mom_adjusted_var


def test_configure_forcings_invalid_function_overrides(get_CrocoDash_case):
    """
    GLORYS access functions have no non-required args, so any override key is invalid.
    """
    case = get_CrocoDash_case
    with pytest.raises(ValueError):
        case.configure_forcings(
            date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
            boundaries=["north"],
            function_overrides={"bogus_key": 1},
        )


def _stub_case_for_ncpl(ncpl, dx_m, base_period="day"):
    """A Case with only what _set_cice_ndtd/_coupling_interval read."""
    from types import SimpleNamespace
    import numpy as np
    import CrocoDash.case as case_mod

    case = case_mod.Case.__new__(case_mod.Case)
    values = {
        "NCPL_BASE_PERIOD": base_period,
        "CALENDAR": "GREGORIAN",
        "ICE_NCPL": ncpl,
        "WAV_NCPL": ncpl,
    }
    case._cime_case = SimpleNamespace(get_value=lambda name: values[name])
    cells = np.full((4, 4), dx_m)
    case.ocn_grid = SimpleNamespace(dxt=cells, dyt=cells * 1.2)
    return case


@pytest.mark.parametrize(
    "ncpl, dx_m, expected",
    [
        (24, 5450.0, 3),  # big_alaska.019: 1/8 deg near 67N, hourly ice step
        (48, 5450.0, 2),  # half-hour ice step
        (24, 100_000.0, 1),  # ~1 deg: one step is already enough
    ],
)
def test_set_cice_ndtd_scales_with_grid_and_ice_step(monkeypatch, ncpl, dx_m, expected):
    """One hourly dynamics step on a ~5 km grid made big_alaska.019 abort in
    ridging (aice0 < 0); three substeps ran."""
    import CrocoDash.case as case_mod

    written = {}
    monkeypatch.setattr(
        case_mod,
        "append_user_nl",
        lambda model, pairs, **kw: written.update({model: dict(pairs)}),
    )
    _stub_case_for_ncpl(ncpl, dx_m)._set_cice_ndtd()
    assert written["cice"]["ndtd"] == str(expected)


def test_coupling_interval_rejects_uneven_ncpl():
    with pytest.raises(ValueError, match="ICE_NCPL doesn't divide"):
        _stub_case_for_ncpl(7, 5450.0)._coupling_interval("ICE")


def test_a_configuration_error_raises_instead_of_returning_a_half_built_case(
    CrocoDash_case_factory, tmp_path, monkeypatch
):
    import CrocoDash.case as case_mod
    from ProConPy.dev_utils import ConstraintViolation

    def fail(self, *args, **kwargs):
        raise ConstraintViolation("no such grid")

    monkeypatch.setattr(case_mod.Case, "_configure_case", fail)
    with pytest.raises(RuntimeError, match="Case configuration failed: no such grid"):
        CrocoDash_case_factory(tmp_path)


def test_a_failed_create_newcase_raises_and_leaves_the_previous_case(
    CrocoDash_case_factory, tmp_path, monkeypatch
):
    """Carrying on after a failed create_newcase only moves the error to
    get_case on a caseroot that was never made. The failed attempt must not
    leave its own half-made dirs behind, nor lose the case it was replacing
    (the factory creates with override=True)."""
    from visualCaseGen.custom_widget_types.case_creator import CaseCreator

    previous = tmp_path / "inputdir"
    previous.mkdir()
    (previous / "marker").write_text("previous case")

    def fail(self, do_exec):
        raise RuntimeError("create_newcase failed")

    monkeypatch.setattr(CaseCreator, "create_case", fail)
    with pytest.raises(RuntimeError, match="create_newcase failed"):
        CrocoDash_case_factory(tmp_path)
    assert (previous / "marker").read_text() == "previous case"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["inputdir"]


def test_an_interrupted_create_restores_the_previous_case(
    CrocoDash_case_factory, tmp_path, monkeypatch
):
    """Ctrl-C in a notebook raises KeyboardInterrupt, not an Exception."""
    from visualCaseGen.custom_widget_types.case_creator import CaseCreator

    previous = tmp_path / "inputdir"
    previous.mkdir()
    (previous / "marker").write_text("previous case")

    def interrupt(self, do_exec):
        raise KeyboardInterrupt

    monkeypatch.setattr(CaseCreator, "create_case", interrupt)
    with pytest.raises(KeyboardInterrupt):
        CrocoDash_case_factory(tmp_path)
    assert (previous / "marker").read_text() == "previous case"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["inputdir"]
