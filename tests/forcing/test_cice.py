"""Tests for CICEConfigurator: validate_args and process()."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing.cice import CICEConfigurator

# Reference files for the cice_restart product -- same as
# tests/raw_data_access/test_cice.py. Duplicated here (rather than imported)
# since each test file in this suite is self-contained.
_CICE_GRID_PATH = "/glade/campaign/cesm/community/omwg/grids/tx2_3v3_grid.nc"
_CICE_RESTART_PATH = (
    "/glade/u/home/dbailey/"
    "b.e30_alpha09b.B1850C_MTso.ne30_t233_wgx3.360.cice.r.0201-01-01-00000.nc"
)


def _skip_if_cice_reference_files_missing():
    if not Path(_CICE_GRID_PATH).exists() or not Path(_CICE_RESTART_PATH).exists():
        pytest.skip(
            "Reference tx2_3v3 grid or CICE restart file not available on this "
            "filesystem."
        )


def _make_ctx(tmp_path, **overrides):
    defaults = dict(
        inputdir=tmp_path,
        supergrid_path=tmp_path / "grid.nc",
        vgrid_path=tmp_path / "vgrid.nc",
        topo_path=tmp_path / "topo.nc",
        raw_data_dir=tmp_path,
        regridded_data_dir=tmp_path,
        output_path=tmp_path,
        config={
            "conditions": {
                "inputs": {"start_date": "2020-01-01", "end_date": "2020-01-02"}
            }
        },
    )
    defaults.update(overrides)
    return WorkflowContext(**defaults)


# =============================================================================
# validate_args
# =============================================================================


def test_cice_configurator_rejects_non_cice_product():
    with pytest.raises(ValueError, match="not a registered CICEForcingProduct"):
        CICEConfigurator(cice_product_name="reference_ocean")


def test_cice_configurator_accepts_matching_product():
    # Doesn't raise -- both the real restart product and the fast synthetic
    # stand-in are valid CICEForcingProducts.
    CICEConfigurator(cice_product_name="reference_ice")
    CICEConfigurator(cice_product_name="cice_restart")


def test_cice_configurator_defaults_to_none_product():
    # None (unset) defers resolution to CICEConfigurator.process's own
    # default ("cice_restart") -- not something validate_args should reject.
    CICEConfigurator()


# =============================================================================
# process()
# =============================================================================


def test_process_cice_forcing_produces_output(
    skip_if_not_glade, tmp_path, gen_grid_topo_vgrid
):
    """process() runs the real restart GET + full-grid ESMF regrid
    end-to-end against the reference restart + grid files -- confirms the
    output covers the domain plus its halo, with real (regridded, not
    placeholder) values, no ``time`` dimension (a restart/initial-condition
    file is a single static snapshot), a plain ``lat lon`` coordinates
    attribute, and no ``_FillValue`` (land is zero, not NaN)."""
    _skip_if_cice_reference_files_missing()
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")

    n_halo_cells = 2
    ny, nx = grid.tlat.shape

    configurator = CICEConfigurator(
        cice_product_name="cice_restart",
        cice_function_name="get_cice_restart_subset",
        cice_function_args={
            "restart_path": _CICE_RESTART_PATH,
            "grid_path": _CICE_GRID_PATH,
        },
        n_halo_cells=n_halo_cells,
    )
    configurator.process(_make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc"))

    ds = xr.open_dataset(tmp_path / "sea_ice" / "cice_forcing.nc")

    assert ds.sizes["ny"] == ny + 2 * n_halo_cells
    assert ds.sizes["nx"] == nx + 2 * n_halo_cells
    assert "time" not in ds.dims
    assert "aicen" in ds and ds["aicen"].dims == ("ncat", "ny", "nx")
    assert "uvel" in ds and ds["uvel"].dims == ("ny", "nx")
    assert ds["iceumask"].encoding.get("coordinates") == "lat lon"
    assert ds["aicen"].encoding.get("coordinates") == "lat lon"
    assert "_FillValue" not in ds["iceumask"].encoding
    assert not np.isnan(ds["iceumask"].values).any()
    # No ice expected at this (Panama-region) test grid's location -- both
    # the domain interior and its halo.
    assert float(ds["aicen"].sum()) == 0.0


def test_process_cice_forcing_with_reference_ice(tmp_path, gen_grid_topo_vgrid):
    """Same pipeline as test_process_cice_forcing_produces_output, but against
    the fast synthetic 'reference_ice' product -- no real restart/grid file,
    no /glade dependency, runs on every machine."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")

    n_halo_cells = 2
    ny, nx = grid.tlat.shape

    configurator = CICEConfigurator(
        cice_product_name="reference_ice",
        cice_function_name="get_reference_ice_data",
        n_halo_cells=n_halo_cells,
    )
    configurator.process(_make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc"))

    ds = xr.open_dataset(tmp_path / "sea_ice" / "cice_forcing.nc")

    assert ds.sizes["ny"] == ny + 2 * n_halo_cells
    assert ds.sizes["nx"] == nx + 2 * n_halo_cells
    assert "time" not in ds.dims
    assert "aicen" in ds and ds["aicen"].dims == ("ncat", "ny", "nx")
    assert "uvel" in ds and ds["uvel"].dims == ("ny", "nx")
    assert ds["uvel"].encoding.get("coordinates") == "lat lon"
    assert "_FillValue" not in ds["uvel"].encoding
    assert np.isfinite(ds["aicen"].values).all()
