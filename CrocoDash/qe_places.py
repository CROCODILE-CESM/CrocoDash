"""Places the CrocoDash rules share, as queryearth spaces.

Rules name a place here instead of carrying their own copy of its shape, so one
shape serves every rule about it. The shapes are first drafts traced by hand:
the straits are good to a few tenths of a degree, the currents and fronts are
rough bands. Refine a shape here and every rule that uses it follows.
"""

import shapely
from queryearth import space as sp


def _polygon(*points):
    """A polygon from (lon, lat) points; the ring is closed for you."""
    ring = [list(p) for p in points] + [list(points[0])]
    return sp.polygon({"type": "Polygon", "coordinates": [ring]})


PLACES = {
    # ---- regions ------------------------------------------------------------------
    "arctic": sp.box(-180, 66.5, 180, 90),
    "arctic_60": sp.box(-180, 60, 180, 90),
    "antarctic_60": sp.box(-180, -90, 180, -60),
    "coral_triangle": sp.box(115, -12, 162, 20),
    "indonesian_seas": sp.box(105, -15, 135, 8),
    "benguela": sp.box(8, -35, 20, -14),
    # ---- straits ------------------------------------------------------------------
    "makassar_strait": sp.box(116.5, -5.5, 119.5, 1.5),
    "lombok_strait": sp.box(115.4, -9.0, 116.1, -8.0),
    "ombai_strait": sp.box(124.0, -8.9, 126.0, -8.0),
    "timor_passage": sp.box(122.5, -11.8, 125.5, -10.2),
    "torres_strait": sp.box(141.5, -11.0, 143.5, -9.0),
    "gibraltar_strait": sp.box(-6.1, 35.7, -5.3, 36.2),
    # ---- strong currents ----------------------------------------------------------
    "gulf_stream": _polygon(
        (-81.0, 24.0),
        (-79.0, 24.0),
        (-78.5, 28.0),
        (-76.5, 31.0),
        (-74.0, 34.0),
        (-70.0, 36.5),
        (-60.0, 38.5),
        (-45.0, 40.5),
        (-45.0, 43.5),
        (-60.0, 41.5),
        (-70.0, 39.5),
        (-74.5, 36.5),
        (-77.0, 34.0),
        (-79.5, 31.0),
        (-80.5, 27.5),
    ),
    "kuroshio": _polygon(
        (121.0, 21.5),
        (123.5, 21.5),
        (128.0, 27.0),
        (132.0, 30.0),
        (136.0, 32.0),
        (141.0, 33.5),
        (155.0, 34.0),
        (155.0, 37.5),
        (141.0, 37.0),
        (138.0, 34.5),
        (134.0, 33.5),
        (130.0, 32.0),
        (126.0, 28.5),
        (121.5, 25.0),
    ),
    "agulhas_current": _polygon(
        (32.5, -27.0),
        (35.0, -27.0),
        (31.0, -33.0),
        (26.0, -36.5),
        (21.0, -37.5),
        (20.0, -36.0),
        (25.0, -34.5),
        (30.0, -31.5),
    ),
    "east_australian_current": _polygon(
        (152.0, -24.0),
        (156.0, -24.0),
        (156.0, -35.0),
        (150.5, -35.0),
    ),
    # ---- retroflections, eddy-shedding regions and fronts -------------------------
    "north_brazil_retroflection": sp.box(-55, 3, -44, 10),
    "agulhas_retroflection": sp.box(14, -42, 25, -35),
    "agulhas_return_current": sp.box(25, -43, 70, -37),
    "brazil_malvinas_confluence": sp.box(-58, -42, -48, -34),
    "angola_benguela_front": sp.box(8, -18, 14, -14),
}

# Groups that rules share
ITF_STRAITS = ("makassar_strait", "lombok_strait", "ombai_strait", "timor_passage")
STRONG_CURRENTS = (
    "gulf_stream",
    "kuroshio",
    "agulhas_current",
    "east_australian_current",
)
ENERGETIC_STRUCTURES = (
    "north_brazil_retroflection",
    "agulhas_retroflection",
    "agulhas_return_current",
    "brazil_malvinas_confluence",
    "angola_benguela_front",
)


def union(*names):
    """One space covering several places, for a rule about any of them."""
    return sp.polygon(shapely.union_all([PLACES[name].geometry for name in names]))


# Names that title case gets wrong
_NAMES = {
    "brazil_malvinas_confluence": "Brazil–Malvinas Confluence",
    "angola_benguela_front": "Angola–Benguela Front",
}


def label(name):
    """A place's name for people: "gulf_stream" -> "the Gulf Stream"."""
    return "the " + _NAMES.get(name, name.replace("_", " ").title())
