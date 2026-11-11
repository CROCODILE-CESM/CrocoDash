import pytest

from CrocoDash.forcing.pe_layout import pe_layout


@pytest.mark.parametrize(
    "ocean_points, marbl, ntasks_ocn, tasks_per_node, expected",
    [
        # (MOM6/CICE/WW3 tasks, DATM/DROF/mediator tasks)
        (100, False, None, 128, (1, 56)),  # one task; data at least 56
        (5_000, False, None, 128, (30, 56)),  # 5000/170 -> 30
        (15_000, False, None, 128, (89, 89)),  # data matches MOM6 above 56
        (200_000, False, None, 128, (1177, 128)),  # data up to one node
        (5_000, True, None, 128, (84, 84)),  # MARBL: 60 points per task
        (30_000, False, 8, 128, (8, 56)),  # ntasks_ocn replaces the count
        (100, False, None, 1, (1, 1)),  # a one-task machine (crocontainer)
    ],
)
def test_pe_layout_gives_mom6_one_task_per_170_ocean_points(
    ocean_points, marbl, ntasks_ocn, tasks_per_node, expected
):
    layout = pe_layout(ocean_points, tasks_per_node, marbl=marbl, ntasks_ocn=ntasks_ocn)
    ntasks, data = expected
    assert layout == {
        "NTASKS": ntasks,
        "ROOTPE": 0,
        "NTASKS_ATM": data,
        "NTASKS_ROF": data,
        "NTASKS_CPL": data,
    }


def test_a_layout_change_is_followed_by_a_case_setup_reset(monkeypatch, tmp_path):
    """case.setup has already locked the PE layout, so a changed layout needs a
    reset before CIME will build; an unchanged one needs none (a reset forces a
    rebuild)."""
    from types import SimpleNamespace

    import numpy as np
    import xarray as xr

    import CrocoDash.forcing.base as base_mod
    import CrocoDash.forcing.pe_layout as pe_mod

    (tmp_path / "xmlquery").touch()
    topo = tmp_path / "topo.nc"
    xr.Dataset({"mask": (("ny", "nx"), np.ones((10, 10)))}).to_netcdf(topo)
    changed = {}
    monkeypatch.setattr(
        base_mod, "xmlchange", lambda var, val, **kw: changed.update({var: val})
    )
    # CIME's default layout: one node for every component.
    case_values = {
        "MAX_MPITASKS_PER_NODE": "128",
        "NTASKS": "['CPL:128', 'ATM:128', 'OCN:128', 'ICE:128', 'ROF:128', 'ESP:1']",
        "ROOTPE": "['CPL:0', 'ATM:0', 'OCN:0', 'ICE:0', 'ROF:0', 'ESP:0']",
    }
    resets = []

    def run(cmd, **kw):
        if cmd[0] == "./xmlquery":
            return SimpleNamespace(stdout=case_values[cmd[1]])
        resets.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(pe_mod.subprocess, "run", run)

    def configurator():
        return pe_mod.PELayoutConfigurator(str(tmp_path), str(topo), "MOM6%REGIONAL")

    configurator().configure()
    assert changed == {
        "NTASKS": "1",
        "ROOTPE": "0",
        "NTASKS_ATM": "56",
        "NTASKS_ROF": "56",
        "NTASKS_CPL": "56",
    }
    assert resets == [["./case.setup", "--reset"]]

    # Configured again with that layout in place: nothing to reset.
    case_values["NTASKS"] = "['CPL:56', 'ATM:56', 'OCN:1', 'ICE:1', 'ROF:56', 'ESP:1']"
    configurator().configure()
    assert len(resets) == 1

    # A case made for another machine needs --non-local, as xmlchange does.
    case_values["NTASKS"] = (
        "['CPL:128', 'ATM:128', 'OCN:128', 'ICE:128', 'ROF:128', 'ESP:1']"
    )
    non_local = configurator()
    non_local.registry = SimpleNamespace(case=SimpleNamespace(is_non_local=True))
    non_local.configure()
    assert resets[-1] == ["./case.setup", "--reset", "--non-local"]

    # A failed reset says why, with CIME's own message.
    monkeypatch.setattr(
        pe_mod.subprocess,
        "run",
        lambda cmd, **kw: (
            SimpleNamespace(stdout=case_values[cmd[1]])
            if cmd[0] == "./xmlquery"
            else SimpleNamespace(returncode=1, stderr="ERROR: locked file")
        ),
    )
    with pytest.raises(RuntimeError, match="ERROR: locked file"):
        configurator().configure()
