"""Grid-level invariants, swept across the domain catalog.

Everything here is pure -- no network, no disk beyond tmp_path, no CESM -- so
this file is cheap enough to run with --all-domains on every invocation:

    pytest tests/domains/test_grids.py --all-domains

The catalog lives in tests/fixtures/domains.py.
"""

import numpy as np
import pytest

from CrocoDash.grid import Grid
from tests.fixtures.domains import (
    CONVENTION_PAIRS,
    DOMAINS_BY_KEY,
    DX_DY_SIGN_BUG,
    NEGATIVE_METRIC_DOMAINS,
    TAREA_QUADRANT_BUG,
)

# Grid metrics that must be finite and strictly positive everywhere on every
# domain. A zero or negative cell width silently produces garbage forcing
# rather than an error, which is how the mom6_forge dx bug survived so long.
METRICS = ["dxt", "dyt", "dxCu", "dyCv", "dxCv", "dyCu", "tarea"]

# Convention pairs are compared with a loose relative tolerance: the two
# spellings differ by exactly 360 degrees in lon, so the trig that turns
# degrees into metres accumulates a little floating-point noise (observed
# around 2e-9). Anything genuinely convention-dependent is an O(1) error, so
# 1e-6 still catches it with room to spare.
CONVENTION_RTOL = 1e-6


def _to_360(lon):
    """Normalize longitude to [0, 360) so conventions can be compared."""
    return np.mod(np.asarray(lon, dtype=float), 360.0)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_grid_builds(domain, domain_grid):
    """The catalog entry produces a Grid with a sane shape."""
    assert domain_grid.nx > 0, domain.description
    assert domain_grid.ny > 0, domain.description


def test_coordinates_are_finite_and_in_range(domain_grid):
    ds = domain_grid.supergrid.to_ds()
    assert np.isfinite(ds.x.values).all(), "NaN/inf in supergrid longitude"
    assert np.isfinite(ds.y.values).all(), "NaN/inf in supergrid latitude"
    assert ds.y.min() >= -90.0 and ds.y.max() <= 90.0


def test_supergrid_shape_matches_nx_ny(domain_grid):
    """A supergrid is 2x the tracer grid in each direction, plus one."""
    ds = domain_grid.supergrid.to_ds()
    assert ds.x.shape == (2 * domain_grid.ny + 1, 2 * domain_grid.nx + 1)
    assert ds.y.shape == ds.x.shape


def test_is_rectangular_matches_catalog(domain, domain_grid):
    """Catches a constructor silently changing what shape it produces."""
    assert domain_grid.is_rectangular() is domain.rectangular


def test_grid_metrics_positive_and_finite(domain, domain_grid, request):
    """Cell widths and areas are physical quantities: positive and finite."""
    if domain.key in NEGATIVE_METRIC_DOMAINS:
        request.applymarker(
            pytest.mark.xfail(
                reason=DX_DY_SIGN_BUG.format(
                    reason=NEGATIVE_METRIC_DOMAINS[domain.key]
                ),
                strict=True,
            )
        )

    for name in METRICS:
        values = getattr(domain_grid, name).values
        assert np.isfinite(values).all(), f"{name} has non-finite entries"
        assert (values > 0).all(), f"{name} has non-positive entries"


@pytest.mark.xfail(reason=TAREA_QUADRANT_BUG, strict=True)
def test_tarea_matches_supergrid_quadrants(domain_grid):
    """Each T-cell's area is the sum of its four supergrid quadrants.

    Fails on every domain, not just the exotic ones -- see TAREA_QUADRANT_BUG.
    Pinned here so the fix, whenever it lands, is announced by an XPASS.
    """
    sg = domain_grid.supergrid
    ny, nx = domain_grid.ny, domain_grid.nx
    expected = sg.area[: 2 * ny, : 2 * nx].reshape(ny, 2, nx, 2).sum(axis=(1, 3))
    np.testing.assert_allclose(domain_grid.tarea.values, expected, rtol=1e-12)


def test_supergrid_roundtrips_through_file(domain_grid, tmp_path):
    """write_supergrid -> Grid.from_supergrid preserves the coordinates."""
    path = tmp_path / "ocean_hgrid.nc"
    domain_grid.write_supergrid(str(path))
    reloaded = Grid.from_supergrid(str(path))

    original_ds = domain_grid.supergrid.to_ds()
    reloaded_ds = reloaded.supergrid.to_ds()
    np.testing.assert_allclose(reloaded_ds.x.values, original_ds.x.values, atol=1e-9)
    np.testing.assert_allclose(reloaded_ds.y.values, original_ds.y.values, atol=1e-9)


# ---------------------------------------------------------------------------
# Convention pairs -- the same physical domain written two ways
# ---------------------------------------------------------------------------
#
# These are NOT parametrized over the catalog: each builds both halves of a
# pair directly, so they run regardless of which domain tier is selected.


@pytest.mark.parametrize("key_a,key_b", CONVENTION_PAIRS)
def test_convention_pair_covers_same_region(key_a, key_b):
    """0-360 and -180/180 spellings of one domain must agree once normalized.

    This is the shape of the GLORYS longitude-slicing bug (CrocoDash #230) and
    of the dateline reflection still open in glorys.py: code that normalizes
    longitude inconsistently gives two different answers for these two inputs.
    """
    grid_a = DOMAINS_BY_KEY[key_a].build_grid()
    grid_b = DOMAINS_BY_KEY[key_b].build_grid()

    ds_a = grid_a.supergrid.to_ds()
    ds_b = grid_b.supergrid.to_ds()

    np.testing.assert_allclose(ds_a.y.values, ds_b.y.values, atol=1e-9)
    np.testing.assert_allclose(
        _to_360(ds_a.x.values), _to_360(ds_b.x.values), atol=1e-9
    )


@pytest.mark.parametrize("key_a,key_b", CONVENTION_PAIRS)
def test_convention_pair_has_same_metrics(key_a, key_b):
    """Cell sizes are physical, so they cannot depend on how lon is spelled."""
    grid_a = DOMAINS_BY_KEY[key_a].build_grid()
    grid_b = DOMAINS_BY_KEY[key_b].build_grid()

    for name in METRICS:
        np.testing.assert_allclose(
            getattr(grid_a, name).values,
            getattr(grid_b, name).values,
            rtol=CONVENTION_RTOL,
            err_msg=f"{name} differs between {key_a} and {key_b}",
        )
