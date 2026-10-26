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


def _fail_create_case(monkeypatch, exc):
    from visualCaseGen.custom_widget_types.case_creator import CaseCreator

    def fail(self, do_exec):
        raise exc

    monkeypatch.setattr(CaseCreator, "create_case", fail)


@pytest.mark.parametrize(
    "exc",
    [RuntimeError("create_newcase failed"), KeyboardInterrupt()],
    ids=["error", "ctrl-c"],
)
def test_a_failed_create_leaves_nothing_behind(
    CrocoDash_case_factory, tmp_path, monkeypatch, exc
):
    """Carrying on after a failed create_newcase only moves the error to
    get_case on a caseroot that was never made. The failed attempt must not
    leave half-made dirs that make a retry fail with "already exists"; with
    override=True (as the factory uses) the previous case is gone either way."""
    previous = tmp_path / "inputdir"
    previous.mkdir()
    (previous / "marker").write_text("previous case")

    _fail_create_case(monkeypatch, exc)
    with pytest.raises(type(exc)):
        CrocoDash_case_factory(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_override_says_what_it_removes(tmp_path, capsys):
    from CrocoDash.case import _remove_previous

    old = tmp_path / "old_case"
    old.mkdir()
    _remove_previous(old)
    _remove_previous(tmp_path / "never_existed")
    assert not old.exists()
    assert capsys.readouterr().out == f"Removing previous case files: {old}\n"


def test_a_failed_attempt_leaves_a_preexisting_dir_alone(tmp_path):
    """The build/run dir may be an earlier case's, left behind (M2) with
    override=False; create_newcase refuses it, and it is not ours to delete."""
    from CrocoDash.case import _remove_failed_attempt

    bld_run, caseroot, inputdir = (tmp_path / n for n in ("bld_run", "case", "input"))
    bld_run.mkdir()
    (bld_run / "marker").write_text("earlier run")
    caseroot.mkdir()
    inputdir.mkdir()
    _remove_failed_attempt(
        [inputdir, caseroot, bld_run, caseroot], preexisting={bld_run}
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bld_run"]
    assert (bld_run / "marker").read_text() == "earlier run"


def _fake_caseroot(tmp_path, created_files=None, name="case", **state):
    """A caseroot ``name`` with a 1.2 state file whose cesmroot and grid paths
    don't exist, created with ``created_files`` ({name: text}) in it.
    ``state`` overrides values of the state."""
    from CrocoDash import case_state

    caseroot, inputdir = tmp_path / name, tmp_path / f"{name}_input"
    caseroot.mkdir()
    (inputdir / "extract_forcings").mkdir(parents=True)
    for file_name, text in (created_files or {}).items():
        (caseroot / file_name).write_text(text)
    case_state.write(
        caseroot,
        {
            "inputdir": str(inputdir),
            "cesmroot": "/nonexistent/cesm",
            "supergrid_path": str(inputdir / "ocn" / "ocean_hgrid.nc"),
            "topo_path": str(inputdir / "ocn" / "ocean_topog.nc"),
            "vgrid_path": str(inputdir / "ocn" / "ocean_vgrid.nc"),
            "esmf_mesh_path": str(inputdir / "ocn" / "ESMF_mesh.nc"),
            "grid_name": "g",
            "session_id": "abc123",
            "compset_lname": "1850_DATM%JRA_SLND_SICE_MOM6_SROF_SGLC_SWAV",
            "machine": "derecho",
            "project": None,
            "ninst": 1,
            "atm_grid_name": "TL319",
            "rof_grid_name": None,
            "created": case_state.created_snapshot(caseroot),
            **state,
        },
    )
    return caseroot, inputdir


def test_from_caseroot_reads_a_case_back_without_cime(tmp_path):
    """A case reads back from its state file and config.json alone. Nothing
    exists at its cesmroot or grid paths, so touching CESM, visualCaseGen or
    the grid files on the way would fail."""
    from CrocoDash.case import Case
    from CrocoDash.forcing.base import CONFIG_FILENAME, write_config

    caseroot, inputdir = _fake_caseroot(tmp_path)
    tides = {
        "name": "tides",
        "inputs": {
            "tpxo_elevation_filepath": "h.nc",
            "tpxo_velocity_filepath": "u.nc",
            "tidal_constituents": ["M2"],
            "start_date": "2020, 01, 01",
            "boundaries": ["north"],
        },
    }
    write_config(
        inputdir / "extract_forcings" / CONFIG_FILENAME,
        {"caseroot": str(caseroot), "tides": tides},
    )

    case = Case.from_caseroot(caseroot)

    assert case.configurators()["tides"].get_input_param("tidal_constituents") == ["M2"]
    assert case.workflow_context().inputdir == inputdir


def test_forcing_inputs_has_every_case_input_a_configurator_takes(tmp_path):
    """Configurators get case_* values only from forcing_inputs(), so a case
    read back must provide them all: a missing one fails configure_forcings()
    where it is required (Runoff's) and silently takes its default elsewhere."""
    from CrocoDash.case import Case
    from CrocoDash.forcing.base import ForcingConfigRegistry

    caseroot, _ = _fake_caseroot(tmp_path)
    provided = Case.from_caseroot(caseroot).forcing_inputs()
    for configurator_cls in ForcingConfigRegistry.registered_types:
        args, _ = ForcingConfigRegistry.get_ctor_signature(configurator_cls)
        missing = {arg for arg in args if arg.startswith("case_")} - provided.keys()
        assert not missing, f"{configurator_cls.name} takes {missing}"


def test_from_caseroot_refuses_a_state_older_than_1_2(tmp_path):
    """Cases from before the state recorded esmf_mesh_path and the created
    snapshot have to be recreated."""
    from CrocoDash.case import Case

    (tmp_path / "_crocodash_state.json").write_text('{"schema_version": "1.1.0"}')
    with pytest.raises(ValueError):
        Case.from_caseroot(tmp_path)


def test_user_changes_are_the_changes_made_after_creation(tmp_path):
    """Fork carries a user's own changes over to the new case: an xmlchange
    or user_nl line made after creation, with its value, but not what
    creating the case or configure_forcings() wrote."""
    from CrocoDash.case import Case
    from CrocoDash.forcing import user_nl_blocks
    from CrocoDash.forcing.base import CONFIG_FILENAME, write_config

    caseroot, inputdir = _fake_caseroot(
        tmp_path,
        {
            "replay.sh": "./xmlchange NTASKS_OCN=20 --non-local\n",
            "user_nl_mom": "INPUTDIR = /input/ocn\n",
        },
    )
    write_config(
        inputdir / "extract_forcings" / CONFIG_FILENAME,
        {"caseroot": str(caseroot), "runoff": {"name": "Runoff"}},
    )
    with open(caseroot / "replay.sh", "a") as f:
        f.write(
            "./xmlchange STOP_N=31 --non-local\n"
            "./xmlchange ROF2OCN_LIQ_RMAPNAME=/input/map.nc --non-local\n"
            "./xmlchange NTASKS_OCN=40\n"
            "/cesm/cime/CIME/Tools/xmlchange --id DOUT_S --val FALSE\n"
            './xmlchange --id=RUN_REFCASE --val="my ref" --file env_run.xml\n'
            "./xmlchange HIST_OPTION=nhours,HIST_N=6 --force  # 6-hourly\n"
        )
    with open(caseroot / "user_nl_mom", "a") as f:
        f.write("DT = 900.0\n")
    user_nl_blocks.write(
        "conditions",
        "mom",
        [(None, [("OBC_NUMBER_OF_SEGMENTS", "1")])],
        caseroot=caseroot,
        ninst=1,
    )
    (caseroot / "user_nl_datm_streams").write_text("JRA.PREC:year_first = 1999\n")

    changes = Case.from_caseroot(caseroot).user_changes()

    assert changes["xmlchanges"] == {
        "NTASKS_OCN": "40",
        "DOUT_S": "FALSE",
        "RUN_REFCASE": "my ref",
        "HIST_OPTION": "nhours",
        "HIST_N": "6",
    }
    assert changes["user_nl"] == {
        "user_nl_datm_streams": ["JRA.PREC:year_first = 1999"],
        "user_nl_mom": ["DT = 900.0"],
    }


def test_user_changes_for_another_machine_leave_out_pe_and_job_settings(tmp_path):
    """The source machine's PE layout and batch job settings are wrong on
    another machine (a JOB_QUEUE fails where there is no batch system)."""
    from CrocoDash.case import Case

    caseroot, _ = _fake_caseroot(tmp_path)
    (caseroot / "replay.sh").write_text(
        "./xmlchange NTASKS_OCN=64,ROOTPE_OCN=0,JOB_QUEUE=main,DOUT_S=FALSE\n"
    )
    case = Case.from_caseroot(caseroot)

    assert case.user_changes("ubuntu-latest")["xmlchanges"] == {"DOUT_S": "FALSE"}
    assert len(case.user_changes("derecho")["xmlchanges"]) == 4


def _configured_case(
    tmp_path, monkeypatch, name="case", boundaries=("south", "north"), process=False
):
    """A case read back from a fake caseroot, with a user change and its OBCs
    and chlorophyll configured, and with process, processed by steps that only
    write the files they declare. No DATM, whose stream years need CESM."""
    import CrocoDash.case as case_mod
    from CrocoDash.forcing.chl import ChlConfigurator
    from CrocoDash.forcing.driver import run_workflow
    from CrocoDash.forcing.mom6 import ConditionsConfigurator

    def write_declared(self, ctx):
        for path in self._output_paths(ctx):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(path.name)

    monkeypatch.setattr(case_mod, "xmlchange", lambda *args, **kwargs: None)
    monkeypatch.setattr(ConditionsConfigurator, "process_ic", write_declared)
    monkeypatch.setattr(ConditionsConfigurator, "process_bc", write_declared)
    monkeypatch.setattr(ChlConfigurator, "process", write_declared)

    caseroot, _ = _fake_caseroot(
        tmp_path, name=name, compset_lname="1850_SATM_SLND_SICE_MOM6_SROF_SGLC_SWAV"
    )
    (caseroot / "replay.sh").write_text("./xmlchange DOUT_S=FALSE\n")
    case = case_mod.Case.from_caseroot(caseroot)
    os.makedirs(os.path.dirname(case.supergrid_path))
    for path in (
        case.supergrid_path,
        case.topo_path,
        case.vgrid_path,
        case.esmf_mesh_path,
    ):
        open(path, "w").close()
    case.configure_forcings(
        date_range=["2020-01-01 00:00:00", "2020-01-05 00:00:00"],
        boundaries=list(boundaries),
        chl_processed_filepath=str(tmp_path / "chl.nc"),
    )
    if process:
        run_workflow(case, ic=True, bc=True, chl=True)
    return case


def test_a_bundle_reads_back_like_its_caseroot(tmp_path, monkeypatch):
    """create --from reads a bundle on another machine: its forcing arguments,
    user changes and the files its configured forcings declare all come from
    it."""
    from CrocoDash.case import Case

    case = _configured_case(tmp_path, monkeypatch, process=True)
    bundled = Case.from_caseroot(case.bundle(tmp_path / "bundle"))

    assert bundled.forcing_args() == case.forcing_args()
    assert (bundled.session_id, bundled.compset_lname, bundled.machine) == (
        case.session_id,
        case.compset_lname,
        case.machine,
    )
    assert bundled.user_changes()["xmlchanges"] == {"DOUT_S": "FALSE"}
    ctx = bundled.workflow_context()
    assert ctx.inputdir == tmp_path / "bundle" / "inputdir"
    assert ctx.supergrid_path.is_relative_to(ctx.inputdir)
    assert ctx.supergrid_path.is_file()
    for configurator in bundled.configurators().values():
        assert not configurator.missing_output_files(ctx)


def test_only_the_forcing_steps_whose_settings_match_are_copied(tmp_path, monkeypatch):
    """Swapping two boundaries swaps their segment numbers, so the source's
    OBC files would be wrong for the new case; its chlorophyll is still right,
    and is copied and recorded so processing skips it."""
    from CrocoDash.forcing.driver import read_finished_steps

    source = _configured_case(tmp_path, monkeypatch, process=True)
    case = _configured_case(
        tmp_path, monkeypatch, name="copy", boundaries=("north", "south")
    )

    assert case.copy_forcing_files(source) == ["chl"]
    ctx = case.workflow_context()
    assert case.configurators()["chl"].get_output_filepaths(ctx)
    assert not case.configurators()["conditions"].get_output_filepaths(ctx)
    assert list(read_finished_steps(case.inputdir)) == ["chl"]
