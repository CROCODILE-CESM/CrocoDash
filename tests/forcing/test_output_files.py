"""Every process step writes the files it declares in output_files().

The per-step check is slow and on demand (--runslow): each step really runs,
on synthetic data where CrocoDash ships some. A step whose data only exists on
GLADE, or that is too heavy for a test, skips with the reason, so the skip
list is the coverage gap.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from ProConPy.config_var import cvars

from CrocoDash.forcing.base import ForcingConfigRegistry, WorkflowContext
from CrocoDash.forcing.bgc import (
    BGCICConfigurator,
    BGCIronForcingConfigurator,
    BGCRiverNutrientsConfigurator,
)
from CrocoDash.forcing.cice import CICEConfigurator
from CrocoDash.forcing.mom6 import ConditionsConfigurator
from CrocoDash.forcing.tides import TidesConfigurator
from CrocoDash.forcing.ww3 import WW3Configurator
from CrocoDash.raw_data_access.base import NOLEAP

_RIVER_NUTRIENTS = Path(
    "/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/rof/river_nutrients/"
    "river_nutrients.GNEWS_GNM.glofas.20250916.64bit.nc"
)
_RUNOFF_MAP = Path(
    "/glade/campaign/cesm/cesmdata/cseg/inputdata/ocn/mom/croc/testing_data/panama/"
    "GLOFAS_to_panama1_map_r20_f40_nnsm.nc"
)


@pytest.fixture
def ctx(tmp_path, gen_grid_topo_vgrid):
    """A case inputdir holding the grid, topo and vgrid, plus a caseroot for
    configure() to write user_nl blocks into."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    inputdir = tmp_path / "input"
    ocn = inputdir / "ocn"
    ocn.mkdir(parents=True)
    grid.write_supergrid(ocn / "hgrid.nc")
    topo.write_topo(ocn / "topog.nc")
    vgrid.write(ocn / "vgrid.nc")

    caseroot = tmp_path / "case"
    caseroot.mkdir()
    for component in ("mom", "cice"):
        (caseroot / f"user_nl_{component}").touch()
    cvars["CASEROOT"] = SimpleNamespace(value=caseroot)
    cvars["NINST"] = SimpleNamespace(value=None)

    # configure_forcings() makes this; the process steps make what's under it.
    extract = inputdir / "extract_forcings"
    extract.mkdir()
    context = WorkflowContext(
        inputdir=inputdir,
        supergrid_path=ocn / "hgrid.nc",
        vgrid_path=ocn / "vgrid.nc",
        topo_path=ocn / "topog.nc",
        raw_data_dir=extract / "raw_data",
        regridded_data_dir=extract / "regridded_data",
        output_path=ocn,
        config={
            "conditions": {"inputs": {"start_date": "20200101", "end_date": "20200103"}}
        },
    )
    context.grid = grid
    context.ocn_topo = topo
    return context


def _conditions(ctx):
    configurator = ConditionsConfigurator(
        boundaries=["south", "north", "east", "west"],
        product_name="reference_ocean",
        function_name="get_reference_ocean_data",
        compset="MOM6",
        date_range=pd.to_datetime(["2020-01-01", "2020-01-03"]),
    )
    configurator.configure()
    ctx.config["conditions"] = configurator.serialize()
    return configurator


def _tides(ctx, dummy_tidal_data):
    elevation, velocity = (ctx.inputdir.parent / name for name in ("h.nc", "u.nc"))
    dummy_tidal_data[0].to_netcdf(elevation)
    dummy_tidal_data[1].to_netcdf(velocity)
    configurator = TidesConfigurator(
        tpxo_elevation_filepath=str(elevation),
        tpxo_velocity_filepath=str(velocity),
        tidal_constituents=["M2"],
        boundaries=["east"],
        start_date="2020, 01, 01",
    )
    configurator.configure()
    return configurator


def _cice(ctx):
    configurator = CICEConfigurator(
        cice_product_name="reference_ice",
        cice_function_name="get_reference_ice_data",
        restore_ice=True,
        case_inputdir=ctx.inputdir,
    )
    configurator.configure()
    return configurator


def _ww3(ctx):
    configurator = WW3Configurator(
        case_inputdir=ctx.inputdir,
        boundaries=["west", "east"],
        ww3_obc_product_name="reference_waves",
        ww3_obc_function_name="get_reference_wave_spectra",
    )
    with patch("CrocoDash.forcing.base.xmlchange"):
        configurator.configure()
    return configurator


def _bgcic(ctx):
    source = ctx.inputdir.parent / "marbl_ic.nc"
    source.write_bytes(b"CDF\x01")
    configurator = BGCICConfigurator(marbl_ic_filepath=str(source))
    configurator.configure()
    return configurator


def _bgcironforcing(ctx):
    configurator = BGCIronForcingConfigurator(
        case_session_id="test", case_grid_name="rect"
    )
    configurator.configure()
    return configurator


def _bgcrivernutrients(ctx, is_glade_file_system):
    if not (is_glade_file_system and _RIVER_NUTRIENTS.exists()):
        pytest.skip("needs the GLADE river nutrients file and a runoff map")
    configurator = BGCRiverNutrientsConfigurator(
        global_river_nutrients_filepath=str(_RIVER_NUTRIENTS),
        case_session_id="test",
        case_grid_name="panama1",
        calendar=NOLEAP,
    )
    configurator.configure()
    ctx.config["runoff"] = {"outputs": {"ROF2OCN_LIQ_RMAPNAME": str(_RUNOFF_MAP)}}
    return configurator


_BUILDERS = {
    "ic": lambda ctx, **_: _conditions(ctx),
    "bc": lambda ctx, **_: _conditions(ctx),
    "tides": lambda ctx, dummy_tidal_data, **_: _tides(ctx, dummy_tidal_data),
    "cice": lambda ctx, **_: _cice(ctx),
    "ww3": lambda ctx, **_: _ww3(ctx),
    "bgcic": lambda ctx, **_: _bgcic(ctx),
    "bgcironforcing": lambda ctx, **_: _bgcironforcing(ctx),
    "bgcrivernutrients": lambda ctx, is_glade_file_system, **_: _bgcrivernutrients(
        ctx, is_glade_file_system
    ),
    "chl": lambda ctx, **_: pytest.skip(
        "no processed SeaWiFS chlorophyll file ships with CrocoDash"
    ),
    "runoff": lambda ctx, **_: pytest.skip(
        "runoff map generation needs an ESMF runoff mesh and a large-memory node"
    ),
}


def test_every_process_flag_has_a_builder():
    """A new process step must be added to this check, even if only to skip.
    (Not slow, so a missing entry fails the default test run.)"""
    flags = {
        flag
        for configurator_cls in ForcingConfigRegistry.registered_types
        # Leave out the dummy configurators other test modules register.
        if configurator_cls.__module__.startswith("CrocoDash.")
        for flag in configurator_cls.process_components
    }
    assert set(_BUILDERS) == flags


@pytest.mark.slow
@pytest.mark.parametrize("flag", sorted(_BUILDERS))
def test_process_step_writes_its_declared_files(
    flag, ctx, dummy_tidal_data, is_glade_file_system
):
    configurator = _BUILDERS[flag](
        ctx,
        dummy_tidal_data=dummy_tidal_data,
        is_glade_file_system=is_glade_file_system,
    )
    declared = configurator.output_files(ctx)[flag]
    assert declared, f"{flag} declares no files here, so this checks nothing"

    getattr(configurator, configurator.process_components[flag])(ctx)

    assert configurator.missing_output_files(ctx, flag) == []
