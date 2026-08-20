"""Bounding boxes: what the raw-data fetch actually subsets a global product on.

Split out from test_grids.py because these tests, unlike pure grid
construction, are the ones a DomainSpec.xfail applies to. A cyclic-x grid for
instance builds perfectly well and only falls over here, so applying its xfail
at parametrization time would XPASS every grid test in the other file.

Grid.get_bounding_boxes is the single chokepoint between a domain and the data
downloaded for it (CrocoDash/extract_forcings/obc.py:173 and
initial_condition.py:67), which makes it the highest-leverage place in the
codebase to sweep across topologies.
"""

import numpy as np
import pytest

from CrocoDash.grid import Grid
from tests.fixtures.domains import (
    BBOX_ANTIMERIDIAN_SPAN_BUG,
    INFLATED_BBOX_DOMAINS,
)

EDGES = ("north", "south", "east", "west")

# Above this true angular width a domain is near-global in longitude, so no
# bounding box can be meaningfully "too wide" for it. Polar caps land here.
NEAR_GLOBAL_SPAN_DEG = 180.0

# Opts this whole module into per-domain xfails, so a domain that cannot
# produce bounding boxes at all (cyclic_global) is pinned rather than erroring.
pytestmark = pytest.mark.needs_forcing


@pytest.fixture
def boxes(domain_grid):
    """Bounding boxes for the current domain."""
    return Grid.get_bounding_boxes(domain_grid)


def test_bounding_boxes_have_all_edges(boxes):
    assert set(boxes) == {"north", "south", "east", "west", "ic"}


def test_bounding_boxes_are_ordered(boxes):
    """lat_min <= lat_max on every edge, and on the IC box."""
    for edge, box in boxes.items():
        assert box["lat_min"] <= box["lat_max"], f"{edge} latitude range inverted"


def test_bounding_boxes_are_in_range(boxes):
    """Latitudes stay on the sphere."""
    for edge, box in boxes.items():
        assert -90.0 <= box["lat_min"] <= 90.0, f"{edge} lat_min off-sphere"
        assert -90.0 <= box["lat_max"] <= 90.0, f"{edge} lat_max off-sphere"


def test_boundary_boxes_lie_within_ic_box(boxes):
    """Each edge's box must be inside the full-domain box it was cut from.

    Only latitude is checked. For a seam-crossing domain the longitude bounds
    are the thing under test, and asserting containment here would just
    re-encode whatever convention get_bounding_boxes happens to use today.
    """
    ic = boxes["ic"]
    for edge in EDGES:
        box = boxes[edge]
        assert box["lat_min"] >= ic["lat_min"] - 1e-9, f"{edge} below IC box"
        assert box["lat_max"] <= ic["lat_max"] + 1e-9, f"{edge} above IC box"


def test_boundary_boxes_are_degenerate_in_their_own_direction(domain, boxes):
    """East/west boxes are a line in lon; north/south are a line in lat.

    Only meaningful for grids whose i/j axes align with lon/lat. A projected or
    rotated grid's "east" edge sweeps through many latitudes by construction.
    """
    if not domain.rectangular:
        pytest.skip("edge boxes are not lat/lon-aligned on a curvilinear grid")

    for edge in ("east", "west"):
        box = boxes[edge]
        assert box["lon_min"] == pytest.approx(box["lon_max"], abs=1e-9)
    for edge in ("north", "south"):
        box = boxes[edge]
        assert box["lat_min"] == pytest.approx(box["lat_max"], abs=1e-9)


def _angular_lon_span(lon):
    """True angular width of a longitude set, independent of branch cut.

    Sort the values onto [0, 360), find the widest empty gap, and the span is
    whatever is left. This is what makes a genuine polar cap (which really does
    touch every meridian, so has no large gap) distinguishable from a narrow
    domain that merely straddles the antimeridian.
    """
    values = np.sort(np.mod(np.ravel(np.asarray(lon, dtype=float)), 360.0))
    gaps = np.diff(np.concatenate([values, values[:1] + 360.0]))
    return 360.0 - gaps.max()


def test_bbox_lon_span_matches_domain_width(domain, domain_grid, boxes, request):
    """A modest domain must not get a near-global longitude bounding box.

    The failure this guards against turns a few-hundred-km subset into a
    whole-planet data fetch, silently, because raw min/max over longitudes that
    wrap through +/-180 spans almost 360 degrees.

    Domains that genuinely span most of the globe are exempt, and the exemption
    is the point rather than a loophole. A polar cap really does touch every
    meridian -- its true angular span is ~358.6 degrees -- so no bounding box
    can be "too wide" for it, and nothing useful is left to assert. Separating
    those from the spurious case is what _angular_lon_span is for: raw min/max
    cannot tell a 5-degree domain straddling the dateline from a cap, but the
    largest-gap method can.

    This is deliberately independent of whether mom6_forge#113 is present.
    That fix widens any >180-degree raw span to the full range instead of
    narrowing it, which leaves the caps (already exempt here) reporting ~360
    and leaves rotated_on_dateline just as inflated -- hence still xfailed.
    """
    true_span = _angular_lon_span(domain_grid.supergrid.to_ds().x.values)
    if true_span > NEAR_GLOBAL_SPAN_DEG:
        pytest.skip(
            f"{domain.key} genuinely spans {true_span:.1f} deg of longitude, so a "
            "near-global bounding box is correct, not inflated"
        )

    if domain.key in INFLATED_BBOX_DOMAINS:
        request.applymarker(
            pytest.mark.xfail(reason=BBOX_ANTIMERIDIAN_SPAN_BUG, strict=True)
        )

    bbox_span = boxes["ic"]["lon_max"] - boxes["ic"]["lon_min"]
    assert bbox_span <= true_span + 1e-6, (
        f"{domain.key}: bounding box spans {bbox_span:.3f} deg of longitude "
        f"but the domain is only {true_span:.3f} deg wide"
    )
