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
    assert file_with_prefix_exists(case.inputdir / "ocnice", "ocean_hgrid")

    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_hgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_topog_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ocean_vgrid_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"scrip_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    files = [
        f
        for f in os.listdir(case.inputdir / "ocnice")
        if f.startswith(f"ESMF_mesh_{case.ocn_grid.name}")
    ]
    assert len(files) > 0
    if "CICE" in case.compset_lname:
        files = [
            f
            for f in os.listdir(case.inputdir / "ocnice")
            if f.startswith(f"cice_grid_{case.ocn_grid.name}")
        ]
        assert len(files) > 0


def test_ported_case_has_cime_artifacts(ported_case):
    """The one case built on a ported machine must be a real, CIME-created case.

    Everything else in the suite is configured without invoking CIME, so this is what
    covers the create_newcase/case.setup path: the files below only exist because CIME
    actually ran.
    """
    caseroot = ported_case.caseroot
    assert file_with_prefix_exists(caseroot, "README")
    assert (caseroot / "xmlquery").exists()
    assert (caseroot / "env_case.xml").exists()
    assert (caseroot / "user_nl_mom").exists()
    assert (caseroot / "SourceMods").is_dir()


def test_not_ported_machine_configures_without_cime(get_CrocoDash_case):
    """The complement of test_ported_case_has_cime_artifacts: CESM_NOT_PORTED must
    configure everything CIME is not needed for, and invoke CIME for nothing.

    This is the un-ported path itself, not a stand-in for it. CESM_NOT_PORTED is
    visualCaseGen's placeholder rather than a CIME machine, so requesting it works on any
    host -- which is what makes the path assertable here rather than only on a laptop with
    an unported CESM checkout.
    """
    case = get_CrocoDash_case
    assert case.machine == "CESM_NOT_PORTED"
    assert case.do_exec is False

    # Everything that does not need CIME still happened.
    assert case.caseroot.exists()
    assert file_with_prefix_exists(case.inputdir / "ocnice", "ocean_hgrid")
    assert (case.caseroot / "_crocodash_state.json").exists()

    # Nothing create_newcase or case.setup would have written exists.
    assert not (case.caseroot / "xmlquery").exists()
    assert not (case.caseroot / "env_case.xml").exists()
    assert not (case.caseroot / "SourceMods").exists()
    assert not file_with_prefix_exists(case.caseroot, "README")


def test_not_ported_machine_recorded_in_state(get_CrocoDash_case):
    """The state file records the placeholder machine, so a later replay on a ported
    machine has to override it rather than silently inheriting a case CIME never ran."""
    import json

    state = json.loads(
        (get_CrocoDash_case.caseroot / "_crocodash_state.json").read_text()
    )
    assert state["machine"] == "CESM_NOT_PORTED"


def test_emulate_not_ported_matches_visualcasegen(monkeypatch, tmp_path):
    """_emulate_not_ported replicates the identity fields of visualCaseGen's own
    _handle_machine_not_ported instead of calling it, so that a test run does not create
    ~/scratch and ~/inputdata as a side effect. Replication can drift from the original,
    so pin the two together here.

    Only the identity fields are compared: the data roots are intentionally different,
    since on a ported host the machine's real CIME_OUTPUT_ROOT/DIN_LOC_ROOT already exist
    and are the correct place to write.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from visualCaseGen.cime_interface import CIME_interface
    from CrocoDash import case as case_module

    # Redirect $HOME so the handler's mkdirs land in tmp_path.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    reference = SimpleNamespace()
    CIME_interface._handle_machine_not_ported(reference)

    # _emulate_not_ported refreshes the MACHINE option list, which needs cvars.
    machine_var = SimpleNamespace(options=["derecho", "casper"])
    monkeypatch.setattr(case_module, "cvars", {"MACHINE": machine_var})
    emulated = SimpleNamespace(machine="derecho")
    case_module._emulate_not_ported(emulated)

    assert emulated.machine == reference.machine
    assert emulated.machines == reference.machines
    assert emulated.project_required == reference.project_required
    assert machine_var.options == reference.machines


def test_configure_forcings(ported_case):
    # Reads user_nl_mom, which only a CIME-created case has, hence ported_case.
    case = ported_case
    assert case.expt is not None
    assert case.date_range[0].year == 2020
    assert case.boundaries == ["north", "east"]
    search_string = "OBC_NUMBER_OF_SEGMENTS"
    found_user_nl_mom_adjusted_var = False
    with open(case.caseroot / "user_nl_mom", "r", encoding="utf-8") as file:
        for line in file:
            if search_string in line:
                found_user_nl_mom_adjusted_var = True
                break
    assert found_user_nl_mom_adjusted_var


def test_configure_forcings_invalid_function_overrides(get_mutable_CrocoDash_case):
    """
    GLORYS access functions have no non-required args, so any override key is invalid.
    """
    case = get_mutable_CrocoDash_case
    with pytest.raises(ValueError):
        case.configure_forcings(
            date_range=["2020-01-01 00:00:00", "2020-02-01 00:00:00"],
            boundaries=["north"],
            function_overrides={"bogus_key": 1},
        )
