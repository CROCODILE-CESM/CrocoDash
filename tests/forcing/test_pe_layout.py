import pytest

from CrocoDash.forcing.pe_layout import pe_layout


@pytest.mark.parametrize(
    "ocean_points, marbl, ntasks_ocn, expected",
    [
        # (NTASKS, ROOTPE, NTASKS_OCN, ROOTPE_OCN) on a 128-task node
        (100, False, None, (1, 0, 1, 0)),  # 1 task: MOM_interface's XS
        (5_000, False, None, (1, 0, 32, 0)),  # 30 tasks: the 32 tier, one node
        (15_000, False, None, (128, 0, 128, 128)),  # 89: S
        (30_000, False, None, (128, 0, 384, 128)),  # 177, two nodes: M
        (200_000, False, None, (128, 0, 896, 128)),  # 1177, ten nodes: L
        (5_000, True, None, (128, 0, 384, 128)),  # 84 with MARBL: MARBL's S
        (30_000, False, 8, (1, 0, 8, 0)),  # ntasks_ocn replaces the count
    ],
)
def test_pe_layout_picks_the_smallest_tier_that_fits(
    ocean_points, marbl, ntasks_ocn, expected
):
    layout = pe_layout(ocean_points, 128, marbl=marbl, ntasks_ocn=ntasks_ocn)
    assert layout == dict(
        zip(("NTASKS", "ROOTPE", "NTASKS_OCN", "ROOTPE_OCN"), expected)
    )


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
        "MAX_TASKS_PER_NODE": "128",
        "NTASKS": "['CPL:128', 'ATM:128', 'OCN:128', 'ESP:1']",
        "ROOTPE": "['CPL:0', 'ATM:0', 'OCN:0', 'ESP:0']",
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
        "NTASKS_OCN": "1",
        "ROOTPE_OCN": "0",
    }
    assert resets == [["./case.setup", "--reset"]]

    # Configured again with that layout in place: nothing to reset.
    case_values["NTASKS"] = "['CPL:1', 'ATM:1', 'OCN:1', 'ESP:1']"
    configurator().configure()
    assert len(resets) == 1

    # A case made for another machine needs --non-local, as xmlchange does.
    case_values["NTASKS"] = "['CPL:128', 'ATM:128', 'OCN:128', 'ESP:1']"
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
