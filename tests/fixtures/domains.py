"""
The domain catalog: one row per lat/lon topology CrocoDash has to survive.

The whole suite's grid coverage used to be `panama1` -- a 4x3 degree box at
xstart=278, ystart=7, which is the easiest possible corner of the parameter
space (northern hemisphere, mid-latitude, 0-360 convention, no seam,
axis-aligned). Every seam and high-latitude bug found so far was found by hand
on a one-off case, never by the suite.

This file is deliberately the *whole* framework -- dataclass, catalog,
selection, fixtures -- in one place. Adding a domain is adding one DomainSpec
row to DOMAINS; nothing else needs touching. It is auto-loaded by the
`fixtures/*.py` glob in tests/conftest.py, so there is no plugin to register.

Any test that takes a `domain`-family fixture is parametrized over the selected
subset of the catalog:

    def test_something(domain_grid):
        ...

By default that is the `cheap` tier. Widen it with --all-domains,
--domain-tags=seam,polar, or narrow it with --domains=arctic_cap. See
select_domains() and the pytest_generate_tests hook in tests/conftest.py.

Everything here is pure: grids are built in memory, and nothing touches the
network, CESM, or a case directory. That is deliberate. Sweeping the *full*
forcing pipeline across domains needs a real CESM root and costs minutes per
domain, so it belongs in crocontainer rather than in pytest -- and it would
not buy much here anyway, since the synthetic forcing product generates data
for whatever bounding box it is handed and so cannot detect a wrong one. The
bounding boxes are therefore checked directly, in test_bounding_boxes.py.
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from CrocoDash.grid import Grid


@dataclass(frozen=True)
class DomainSpec:
    """One entry in the catalog. `kwargs` go straight to the constructor."""

    key: str
    description: str
    builder: str  # "rect" | "projection" | "center"
    kwargs: dict
    tags: frozenset
    rectangular: bool = True  # expected Grid.is_rectangular()
    # Reason this domain cannot produce forcing at all. Applied as a strict
    # xfail by the tests that need bounding boxes or a full pipeline; grid
    # construction itself may still work fine, so this is deliberately NOT
    # applied globally at parametrization time.
    xfail: Optional[str] = None

    def build_grid(self) -> Grid:
        if self.builder == "rect":
            return Grid(**self.kwargs)
        if self.builder == "projection":
            return Grid.from_projection(**self.kwargs)
        if self.builder == "center":
            return Grid.from_center(**self.kwargs)
        raise ValueError(f"Unknown builder {self.builder!r} for domain {self.key!r}")

    def marks(self):
        """Strict-xfail mark for this domain, or nothing."""
        if self.xfail:
            return [pytest.mark.xfail(reason=self.xfail, strict=True)]
        return []


def _rect(key, description, tags, **kwargs):
    # nx/ny and resolution are mutually exclusive in Grid.__init__.
    if "nx" not in kwargs:
        kwargs.setdefault("resolution", 0.1)
    kwargs.setdefault("name", key)
    return DomainSpec(
        key=key,
        description=description,
        builder="rect",
        kwargs=kwargs,
        tags=frozenset(tags),
    )


DOMAINS = [
    # -- ordinary boxes, one per hemisphere ---------------------------------
    _rect(
        "nh_atlantic",
        "Northern hemisphere, mid-latitude, 0-360 convention. The easy case.",
        ["cheap", "regular"],
        xstart=300.0,
        lenx=6.0,
        ystart=30.0,
        leny=6.0,
    ),
    _rect(
        "sh_indian",
        "Southern hemisphere, eastern longitudes. Negative latitudes only.",
        ["cheap", "regular"],
        xstart=60.0,
        lenx=6.0,
        ystart=-40.0,
        leny=6.0,
    ),
    # -- the same physical domain in both longitude conventions -------------
    # Gulf of Mexico, expressed 0-360 and -180/180. Any code that normalizes
    # longitude inconsistently produces two different answers for these two,
    # which is exactly the shape of the GLORYS slicing bug (CrocoDash #230).
    _rect(
        "western_hemi_360",
        "Gulf of Mexico in 0-360 convention; pairs with western_hemi_neg.",
        ["cheap", "regular", "convention"],
        xstart=265.0,
        lenx=6.0,
        ystart=20.0,
        leny=6.0,
    ),
    _rect(
        "western_hemi_neg",
        "Gulf of Mexico in -180/180 convention; pairs with western_hemi_360.",
        ["regular", "convention"],
        xstart=-95.0,
        lenx=6.0,
        ystart=20.0,
        leny=6.0,
    ),
    # -- discontinuities ----------------------------------------------------
    _rect(
        "equator_straddle",
        "Straddles the equator, so latitude changes sign inside the domain.",
        ["cheap", "equator"],
        xstart=-10.0,
        lenx=6.0,
        ystart=-3.0,
        leny=6.0,
    ),
    _rect(
        "prime_meridian_seam",
        "Crosses longitude 0, so lon changes sign in -180/180 convention.",
        ["cheap", "seam"],
        xstart=-3.0,
        lenx=6.0,
        ystart=45.0,
        leny=6.0,
    ),
    _rect(
        "dateline_seam_360",
        "Crosses the antimeridian, running 177->183 in 0-360 convention.",
        ["seam"],
        xstart=177.0,
        lenx=6.0,
        ystart=-5.0,
        leny=6.0,
    ),
    _rect(
        "dateline_seam_neg",
        "Same antimeridian crossing as dateline_seam_360, as -183->-177.",
        ["seam", "convention"],
        xstart=-183.0,
        lenx=6.0,
        ystart=-5.0,
        leny=6.0,
    ),
    # -- high latitude, without a projection --------------------------------
    _rect(
        "high_lat_north",
        "72-80N: meridians converge hard, so dx shrinks relative to dy.",
        ["high_lat"],
        xstart=-20.0,
        lenx=8.0,
        ystart=72.0,
        leny=8.0,
    ),
    # -- degenerate shapes --------------------------------------------------
    _rect(
        "thin_channel",
        "High aspect ratio: 100 cells wide, 5 tall.",
        ["aspect"],
        xstart=0.0,
        lenx=10.0,
        ystart=0.0,
        leny=0.5,
    ),
    _rect(
        "tiny",
        "Smallest domain CESM will accept: 4x4 cells. visualCaseGen requires "
        "OCN_NX >= 2, OCN_NY >= 2 and OCN_NX * OCN_NY >= 16 "
        "(relational_constraints.py:129), so anything smaller builds as a Grid "
        "but is rejected at case creation.",
        ["cheap", "degenerate"],
        xstart=0.0,
        lenx=0.4,
        ystart=0.0,
        leny=0.4,
        nx=4,
        ny=4,
    ),
    # -- the other Grid.__init__ branch -------------------------------------
    _rect(
        "cartesian_rectilinear",
        "type='rectilinear_cartesian' (RectilinearCartesianSupergrid), the "
        "second branch of Grid.__init__ and otherwise untested.",
        ["gridtype"],
        xstart=300.0,
        lenx=6.0,
        ystart=30.0,
        leny=6.0,
        type="rectilinear_cartesian",
    ),
    # -- polar caps, via projection -----------------------------------------
    # Both span essentially the full -180..180 longitude range, because a cap
    # containing the pole touches every meridian. That makes the source-data
    # bounding box near-global in lon -- the case that broke GLORYS download.
    DomainSpec(
        key="arctic_cap",
        description="North pole inside the domain (EPSG:3995, +/-400 km).",
        builder="projection",
        kwargs=dict(
            crs="EPSG:3995",
            x_min=-400e3,
            x_max=400e3,
            y_min=-400e3,
            y_max=400e3,
            resolution_m=20e3,
            name="arctic_cap",
        ),
        tags=frozenset(["polar", "projected", "seam"]),
        rectangular=False,
    ),
    DomainSpec(
        key="antarctic_cap",
        description="South pole inside the domain (EPSG:3031, +/-400 km).",
        builder="projection",
        kwargs=dict(
            crs="EPSG:3031",
            x_min=-400e3,
            x_max=400e3,
            y_min=-400e3,
            y_max=400e3,
            resolution_m=20e3,
            name="antarctic_cap",
        ),
        tags=frozenset(["polar", "projected", "seam"]),
        rectangular=False,
    ),
    # -- rotated grids ------------------------------------------------------
    DomainSpec(
        key="rotated_estuary",
        description="Rotated 45 deg off north, mid-latitude Atlantic coast.",
        builder="center",
        kwargs=dict(
            center_lat=40.0,
            center_lon=-70.0,
            width_m=400e3,
            height_m=300e3,
            resolution_m=10e3,
            angle_deg=45.0,
            name="rotated_estuary",
        ),
        tags=frozenset(["rotated", "projected"]),
        rectangular=False,
    ),
    DomainSpec(
        key="rotated_on_dateline",
        description="Rotated 30 deg AND centred on the antimeridian -- the "
        "composition of two independently hard cases.",
        builder="center",
        kwargs=dict(
            center_lat=-20.0,
            center_lon=180.0,
            width_m=400e3,
            height_m=400e3,
            resolution_m=20e3,
            angle_deg=30.0,
            name="rotated_on_dateline",
        ),
        tags=frozenset(["rotated", "projected", "seam"]),
        rectangular=False,
    ),
    # -- known-unsupported, pinned so v1 documents the limit ----------------
    DomainSpec(
        key="cyclic_global",
        description="Globally cyclic in x. Grid.get_bounding_boxes asserts "
        "not is_cyclic_x, so every forcing path is a hard failure today.",
        builder="rect",
        kwargs=dict(
            resolution=1.0,
            xstart=0.0,
            lenx=360.0,
            ystart=-10.0,
            leny=20.0,
            cyclic_x=True,
            name="cyclic_global",
        ),
        tags=frozenset(["cyclic"]),
        xfail="Cyclic-x domains are unsupported: Grid.get_bounding_boxes "
        "asserts not is_cyclic_x. Pinned as a known v1 limitation.",
    ),
]

DOMAINS_BY_KEY = {d.key: d for d in DOMAINS}
ALL_TAGS = sorted({t for d in DOMAINS for t in d.tags})

# Pairs of (key_a, key_b) describing the same physical region in different
# longitude conventions. Consumed by the convention-pair tests.
CONVENTION_PAIRS = [
    ("western_hemi_360", "western_hemi_neg"),
    ("dateline_seam_360", "dateline_seam_neg"),
]


def select_domains(config, apply_xfail=False):
    """Resolve the CLI options into a list of pytest.param()s.

    Precedence: --domains > --all-domains > --domain-tags > the `cheap` tier.

    apply_xfail attaches each spec's DomainSpec.xfail as a strict xfail mark.
    It is opt-in per test module (via the `needs_forcing` marker, see
    pytest_generate_tests in tests/conftest.py) because a domain can be
    perfectly constructible and still unable to produce forcing -- cyclic_global
    is exactly that. Marking it globally would XPASS every grid test.

    It has to happen here, at collection time, rather than via
    request.applymarker inside a fixture: pytest evaluates xfail before
    fixtures run, so a marker applied mid-fixture cannot convert a
    fixture-raised error into an xfail.
    """
    keys = config.getoption("--domains")
    tags = config.getoption("--domain-tags")

    if keys:
        requested = [k.strip() for k in keys.split(",") if k.strip()]
        unknown = [k for k in requested if k not in DOMAINS_BY_KEY]
        if unknown:
            raise pytest.UsageError(
                f"Unknown domain key(s): {', '.join(unknown)}. "
                f"Valid keys: {', '.join(sorted(DOMAINS_BY_KEY))}"
            )
        selected = [DOMAINS_BY_KEY[k] for k in requested]
    elif config.getoption("--all-domains"):
        selected = list(DOMAINS)
    elif tags:
        wanted = {t.strip() for t in tags.split(",") if t.strip()}
        unknown = wanted - set(ALL_TAGS)
        if unknown:
            raise pytest.UsageError(
                f"Unknown domain tag(s): {', '.join(sorted(unknown))}. "
                f"Valid tags: {', '.join(ALL_TAGS)}"
            )
        selected = [d for d in DOMAINS if d.tags & wanted]
    else:
        selected = [d for d in DOMAINS if "cheap" in d.tags]

    return [
        pytest.param(d, id=d.key, marks=d.marks() if apply_xfail else [])
        for d in selected
    ]


# ---------------------------------------------------------------------------
# Fixtures. All function-scoped: these grids are at most 100x100 cells and
# build in well under a second, so caching would buy nothing and cost clarity.
# ---------------------------------------------------------------------------


@pytest.fixture
def domain_grid(domain):
    """The Grid for the current domain."""
    return domain.build_grid()


# ---------------------------------------------------------------------------
# Known upstream bugs, pinned rather than papered over
# ---------------------------------------------------------------------------
#
# Every entry here is a real mom6_forge defect that this catalog surfaced. They
# are applied as *strict* xfails, so the day one is fixed the corresponding
# test XPASSes loudly and this entry can be deleted -- that is the whole point
# of pinning them rather than loosening the assertion.

# mom6_forge/_supergrid.py::_calc_dx_dy computes, for the default
# type="smallangle":
#     dx = R * cos(y) * deg2rad(np.diff(x, axis=1))
#     dy = R * deg2rad(np.diff(y, axis=0))
# np.diff is *signed* and there is no abs() and no antimeridian wrapping, so:
#   - on a polar cap, longitude decreases with increasing i over half the
#     domain, making dx negative there (~half of all cells);
#   - on a cell straddling 180, np.diff(x) is about -360 instead of a small
#     positive number, giving dx of roughly -37,000 km.
# The type="haversine" branch is immune to both, but is not the default.
NEGATIVE_METRIC_DOMAINS = {
    "arctic_cap": "polar cap: dx/dy sign flips where lon/lat are non-monotonic in i/j",
    "antarctic_cap": "polar cap: dx/dy sign flips where lon/lat are non-monotonic in i/j",
    "rotated_on_dateline": "antimeridian column: np.diff(lon) wraps to about -360",
}

DX_DY_SIGN_BUG = (
    "mom6_forge _calc_dx_dy(type='smallangle') takes a signed np.diff with no "
    "abs() and no antimeridian wrapping (_supergrid.py:99-100), so {reason}."
)

# mom6_forge/grid.py::_compute_MOM6_grid_metrics sums the four supergrid
# quadrants of each T-cell to get tarea, but sums sg.area[::2, 1::2] twice and
# sg.area[1::2, ::2] never (grid.py:832-836). The four quadrants are equal only
# on a perfectly uniform grid, so this is wrong everywhere -- about 1.6e-4
# relative error even on the plain nh_atlantic box, and it makes total domain
# area disagree with the supergrid it was built from.
TAREA_QUADRANT_BUG = (
    "mom6_forge _compute_MOM6_grid_metrics double-counts supergrid quadrant "
    "[::2, 1::2] and omits [1::2, ::2] when summing tarea (grid.py:832-836)."
)

# mom6_forge/grid.py::get_bounding_boxes takes a plain float(hgrid.x.min()) /
# float(hgrid.x.max()) over the raw supergrid longitudes (grid.py:414-419). For
# a grid whose longitudes wrap through +/-180 -- which a rotated or projected
# grid centred near the antimeridian does -- min lands near -180 and max near
# +180, so a domain a few hundred km wide reports a bounding box spanning
# essentially the whole planet. Downstream that is a near-global data fetch
# instead of a small subset. Note this is NOT the same as a polar cap, whose
# near-global lon span is genuinely correct: a cap really does touch every
# meridian. See test_bbox_lon_span_matches_domain_width.
BBOX_ANTIMERIDIAN_SPAN_BUG = (
    "mom6_forge get_bounding_boxes uses raw min/max over supergrid longitudes "
    "(grid.py:414-419) with no antimeridian branch handling, so a domain "
    "wrapping +/-180 reports a near-global lon span."
)
INFLATED_BBOX_DOMAINS = {"rotated_on_dateline"}
