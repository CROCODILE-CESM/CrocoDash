"""Tests for CICEConfigurator: validate_args and process()."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr

from CrocoDash.forcing.base import WorkflowContext
from CrocoDash.forcing import cice as cice_mod
from CrocoDash.forcing.cice import (
    CICEConfigurator,
    FORCING_FILENAME,
    RESTORE_PARAMS,
    SEA_ICE_SUBDIR,
)

# Reference files for the cice_restart product -- same as
# tests/raw_data_access/test_cice.py. Duplicated here (rather than imported)
# since each test file in this suite is self-contained.
_CICE_GRID_PATH = "/glade/campaign/cesm/community/omwg/grids/tx2_3v3_grid.nc"
_CICE_RESTART_PATH = (
    "/glade/u/home/dbailey/"
    "b.e30_alpha09b.B1850C_MTso.ne30_t233_wgx3.360.cice.r.0201-01-01-00000.nc"
)


def _restoring(**kwargs):
    """The full opt-in trio, since restoring needs all three of restore_ice,
    cice_product_name and cice_function_name (any partial combination raises).
    Defaults to the synthetic reference_ice pair; override either by keyword.
    """
    return {
        "cice_product_name": "reference_ice",
        "cice_function_name": "get_reference_ice_data",
        "restore_ice": True,
        **kwargs,
    }


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
    # A registered product of the wrong flavor (a MOM6 forcing product) and an
    # entirely unknown name are both rejected, with distinct messages.
    with pytest.raises(ValueError, match="not a CICEForcingProduct"):
        CICEConfigurator(**_restoring(cice_product_name="reference_ocean"))

    with pytest.raises(ValueError, match="Unknown forcing product"):
        CICEConfigurator(**_restoring(cice_product_name="not_a_real_product"))


def test_cice_configurator_accepts_matching_product():
    # Doesn't raise -- both the real restart product and the fast synthetic
    # stand-in are valid CICEForcingProducts.
    CICEConfigurator(**_restoring(cice_product_name="reference_ice"))
    CICEConfigurator(**_restoring(cice_product_name="cice_restart"))


def test_cice_configurator_defaults_to_none_product():
    # None (unset) means "generate no restoring forcing" (handled in
    # configure()/process()) -- a valid CICE configuration, not something
    # validate_args should reject.
    CICEConfigurator()


def _configure_without_a_case(configurator):
    """Run configure() with the namelist write stubbed out -- CICE's outputs
    are all UserNLConfigParams, which would otherwise be written into a real
    case directory."""
    with patch("CrocoDash.forcing.user_nl_blocks.write"):
        configurator.configure()


def test_configure_leaves_restore_ice_off_without_a_product():
    """Restoring is opt-in, so restore_ice must stay off unless process() will
    actually produce a file to restore toward -- otherwise CICE is pointed at a
    restoring target that doesn't exist. ice_ic falls back to CICE's own
    internal initialization for the same reason."""
    configurator = CICEConfigurator()
    _configure_without_a_case(configurator)
    # Not written at all (CICE's own default is .false.): the restore_* namelist
    # variables only exist from cesm3_cice6_6_3_22 on, and CIME rejects unknown
    # user_nl variables, so writing them would break a CICE case on an older CICE.
    declared = {p.name for p in configurator.output_params}
    assert not declared & set(RESTORE_PARAMS)
    assert configurator.get_output_param("ice_ic") == "'default'"


@pytest.mark.parametrize("restoring", [False, True])
def test_restore_params_survive_a_config_json_round_trip(tmp_path, restoring):
    """config.json only holds the restore_* params when the case restores, and
    deserialize() must rebuild the configurator either way."""
    kwargs = (
        dict(
            cice_product_name="reference_ice",
            cice_function_name="get_reference_ice_data",
            case_inputdir=tmp_path,
            restore_ice=True,
        )
        if restoring
        else {}
    )
    configurator = CICEConfigurator(**kwargs)
    _configure_without_a_case(configurator)
    data = configurator.serialize()
    assert (set(RESTORE_PARAMS) <= set(data["outputs"])) == restoring

    rebuilt = CICEConfigurator.deserialize(data)
    assert rebuilt.serialize() == data
    if restoring:
        assert rebuilt.get_output_param("restore_ice") == ".true."
        assert rebuilt.get_output_param("restore_flds") == "'state'"


def test_configure_turns_restore_ice_on_with_a_product(tmp_path):
    """With all three opt-in arguments given, the namelist flag goes on and
    ice_ic points at the expanded-grid restart process() will write."""
    configurator = CICEConfigurator(
        cice_product_name="reference_ice",
        cice_function_name="get_reference_ice_data",
        case_inputdir=tmp_path,
        restore_ice=True,
    )
    _configure_without_a_case(configurator)
    assert configurator.get_output_param("restore_ice") == ".true."
    assert (
        configurator.get_output_param("ice_ic")
        == f"'{tmp_path / SEA_ICE_SUBDIR / FORCING_FILENAME}'"
    )


def test_configure_named_product_without_restore_ice_raises(tmp_path):
    """Naming the product/function pair but leaving restore_ice at its False
    default used to generate nothing silently -- indistinguishable from a case
    that never asked for restoring. All three or none."""
    with pytest.raises(ValueError, match="needs all three"):
        CICEConfigurator(
            cice_product_name="reference_ice",
            cice_function_name="get_reference_ice_data",
            case_inputdir=tmp_path,
            restore_ice=False,
        )


@pytest.mark.parametrize("restoring", [True, False])
def test_configure_always_sets_restart_ext(restoring, tmp_path):
    """CICE's own set_nml.bczerogradient pairs zero_gradient boundaries with
    restart_ext = .true., and the ghost ring only exists on disk with it --
    so it goes on regardless of whether restoring is active."""
    kwargs = _restoring(cice_product_name="reference_ice") if restoring else {}
    configurator = CICEConfigurator(case_inputdir=tmp_path, **kwargs)
    _configure_without_a_case(configurator)
    assert configurator.get_output_param("restart_ext") == ".true."
    assert configurator.get_output_param("ns_boundary_type") == "'zero_gradient'"
    assert configurator.get_output_param("ew_boundary_type") == "'zero_gradient'"


def test_configure_restoring_without_a_case_inputdir_raises():
    """There's nowhere for ice_ic to point without it -- fail with a named
    error rather than writing a bogus relative path into user_nl_cice."""
    configurator = CICEConfigurator(**_restoring(cice_product_name="reference_ice"))
    with pytest.raises(ValueError, match="case_inputdir is unset"):
        _configure_without_a_case(configurator)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cice_product_name": "reference_ice"},
        {"cice_function_name": "get_reference_ice_data"},
        {"restore_ice": True},
        {"restore_ice": True, "cice_product_name": "reference_ice"},
        {
            "cice_product_name": "reference_ice",
            "cice_function_name": "get_reference_ice_data",
        },
    ],
    ids=["product", "function", "restore_ice", "restore+product", "pair-no-restore"],
)
def test_cice_partially_specified_raises(kwargs):
    """Restoring takes all three of restore_ice, cice_product_name and
    cice_function_name. Any subset is a typo or a forgotten argument, not a
    request to skip -- skipping silently would hide it behind a case that
    still runs, with no forcing file and ice_ic left at 'default'."""
    with pytest.raises(ValueError, match="needs all three"):
        CICEConfigurator(**kwargs)


def test_cice_none_of_the_three_is_valid():
    """The other half of the rule: asking for none of it is a real
    configuration, not an error -- CICE cold-starts with no restart file."""
    configurator = CICEConfigurator()
    assert configurator._resolve_forcing_source() == (None, None)


def test_u_point_vars_regrid_onto_the_ne_corner(tmp_path, gen_grid_topo_vgrid):
    """CICE's ULON/ULAT are "longitude/latitude of velocity pts, NE corner of
    T pts" (ice_grid.F90), so uvel/vvel/iceumask and the stress fields must be
    sampled north-east of each T centre. The old code used qlon[1:, :-1], the
    NW corner, putting every velocity point one cell too far west -- a silent
    data error, since shapes and dtypes are identical either way.

    Asserted as the NE-of-centre invariant rather than against a literal
    slice, because process() regrids onto the halo-expanded grid, not the
    supergrid passed in.
    """
    grid, _, _ = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")

    seen = {}
    real = cice_mod._regrid_point_group

    def _spy(ds, vars_, src_lon, src_lat, tgt_lon, tgt_lat):
        if vars_:
            key = "u" if any(cice_mod._is_u_point_var(v) for v in vars_) else "t"
            seen[key] = (tgt_lon, tgt_lat)
        return real(ds, vars_, src_lon, src_lat, tgt_lon, tgt_lat)

    with patch.object(cice_mod, "_regrid_point_group", _spy):
        CICEConfigurator(**_restoring()).process(
            _make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc")
        )

    assert {"t", "u"} <= set(seen), f"expected both point groups, got {sorted(seen)}"
    (t_lon, t_lat), (u_lon, u_lat) = seen["t"], seen["u"]
    assert u_lon.shape == t_lon.shape

    # NE corner: strictly east and strictly north of the T centre. The NW-corner
    # bug inverts the longitude comparison while leaving latitude alone.
    assert (u_lon > t_lon).all(), "U points are not east of T centres (NW corner?)"
    assert (u_lat > t_lat).all(), "U points are not north of T centres"


# =============================================================================
# process()
# =============================================================================


def test_process_cice_forcing_skipped_without_product(tmp_path, gen_grid_topo_vgrid):
    """With neither product nor function named, process() must generate nothing
    at all rather than fall back to the real cice_restart product (which needs
    a restart_path/grid_path most users don't have)."""
    grid, topo, vgrid = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")

    CICEConfigurator().process(_make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc"))

    assert not (tmp_path / SEA_ICE_SUBDIR).exists()
    assert not (tmp_path / "extract_forcings" / "cice").exists()


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

    n_halo_cells = 1
    ny, nx = grid.tlat.shape

    configurator = CICEConfigurator(
        cice_product_name="cice_restart",
        cice_function_name="get_cice_restart_subset",
        cice_function_args={
            "restart_path": _CICE_RESTART_PATH,
            "grid_path": _CICE_GRID_PATH,
        },
        restore_ice=True,
    )
    configurator.process(_make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc"))

    ds = xr.open_dataset(tmp_path / "ice" / "cice_forcing.nc")

    # nj/ni, not ny/nx: these are the dimension names CICE's restart reader
    # expects, since configure() points ice_ic at this file.
    assert ds.sizes["nj"] == ny + 2 * n_halo_cells
    assert ds.sizes["ni"] == nx + 2 * n_halo_cells
    assert "ny" not in ds.dims and "nx" not in ds.dims
    assert "time" not in ds.dims
    assert "aicen" in ds and ds["aicen"].dims == ("ncat", "nj", "ni")
    assert "uvel" in ds and ds["uvel"].dims == ("nj", "ni")
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

    n_halo_cells = 1
    ny, nx = grid.tlat.shape

    configurator = CICEConfigurator(**_restoring())
    configurator.process(_make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc"))

    ds = xr.open_dataset(tmp_path / "ice" / "cice_forcing.nc")

    # nj/ni, not ny/nx: these are the dimension names CICE's restart reader
    # expects, since configure() points ice_ic at this file.
    assert ds.sizes["nj"] == ny + 2 * n_halo_cells
    assert ds.sizes["ni"] == nx + 2 * n_halo_cells
    assert "ny" not in ds.dims and "nx" not in ds.dims
    assert "time" not in ds.dims
    assert "aicen" in ds and ds["aicen"].dims == ("ncat", "nj", "ni")
    assert "uvel" in ds and ds["uvel"].dims == ("nj", "ni")
    assert ds["uvel"].encoding.get("coordinates") == "lat lon"
    assert "_FillValue" not in ds["uvel"].encoding
    assert np.isfinite(ds["aicen"].values).all()


# ---------------------------------------------------------------------------
# get_output_filepaths
# ---------------------------------------------------------------------------
#
# CICE's output_params are all namelist settings, so the base implementation
# (which walks output_params for is_file entries) finds nothing. Left that way,
# CaseBundle.bundle() silently ships a bundle with no CICE forcing in it and
# validate_output_filepaths() passes without checking anything.


def test_get_output_filepaths_finds_the_forcing_file(tmp_path):
    """The file lives beside ocn/, not in it."""
    ice_dir = tmp_path / SEA_ICE_SUBDIR
    ice_dir.mkdir()
    expected = ice_dir / FORCING_FILENAME
    expected.touch()

    paths = CICEConfigurator().get_output_filepaths(tmp_path / "ocn")
    assert [Path(p) for p in paths] == [expected]


def test_get_output_filepaths_empty_when_not_yet_processed(tmp_path):
    (tmp_path / "ocn").mkdir()
    assert CICEConfigurator().get_output_filepaths(tmp_path / "ocn") == []


def test_get_output_filepaths_agrees_with_process(tmp_path, gen_grid_topo_vgrid):
    """The writer and the reader must point at the same path.

    This is the regression that matters: process() and get_output_filepaths()
    each built the path independently before they were given shared constants,
    so either could move without the other noticing.
    """
    grid, _, _ = gen_grid_topo_vgrid
    grid.write_supergrid(tmp_path / "grid.nc")

    configurator = CICEConfigurator(**_restoring(cice_product_name="reference_ice"))
    configurator.process(_make_ctx(tmp_path, supergrid_path=tmp_path / "grid.nc"))

    paths = configurator.get_output_filepaths(tmp_path / "ocn")
    assert len(paths) == 1
    assert Path(paths[0]).exists()
    assert configurator.validate_output_filepaths(tmp_path / "ocn")


@pytest.mark.parametrize(
    "ice_dt, min_dx, expected",
    [(3600, 5450.0, 3), (1800, 5450.0, 2), (3600, 100_000.0, 1), (3600, 14_400.0, 1)],
)
def test_dynamics_substeps(ice_dt, min_dx, expected):
    """At most a quarter cell per substep for ice at MAX_ICE_SPEED; never zero."""
    from CrocoDash.forcing.cice import (
        MAX_CELL_FRACTION,
        MAX_ICE_SPEED,
        dynamics_substeps,
    )

    ndtd = dynamics_substeps(ice_dt, min_dx)
    assert ndtd == expected
    assert MAX_ICE_SPEED * ice_dt / ndtd <= MAX_CELL_FRACTION * min_dx
