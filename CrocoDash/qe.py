"""The CrocoDash rules: advice that applies to a case's grid, compset and run.

Case() and configure_forcings() query these rules and print what applies. Places
the rules share are in qe_places.py. Most rules come from expert interviews and
cite the passage they rest on; all are drafts until an expert has reviewed them.

`python -m CrocoDash.qe CrocoDash/qe_rules.geojson` writes the rules to a rule
file that vizqueryearth can show on a globe.
"""

import json
import sys
from pathlib import Path

import queryearth as qe

from CrocoDash.qe_places import (
    ENERGETIC_STRUCTURES,
    ITF_STRAITS,
    PLACES,
    STRONG_CURRENTS,
    label,
    union,
)

INTERVIEW_1 = {
    "title": "Expert interview 1: Coral Triangle & Benguela Upwelling",
    "url": "https://aidanjanney.github.io/RegionalOceanModelingInterviews/transcripts/Edited_Transcript_1.json",
}


def rule(code, title, message, *, quote=None, space=None, dimensions=None, **fields):
    """A rule from interview 1, citing the passage it rests on."""
    if quote is not None:
        fields.setdefault("references", [INTERVIEW_1])
        fields.setdefault("evidence", [{"quote": quote}])
    scope = qe.Scope(space=space, dimensions=dimensions or {})
    return qe.Rule(code=code, title=title, message=message, scope=scope, **fields)


def registry() -> qe.Registry:
    """Build the CrocoDash registry."""
    dimensions = [
        qe.Axis("resolution", "km"),  # the grid's range of cell sizes
        qe.Labels("product"),  # the ocean forcing product, such as glorys
        qe.Labels("variable"),
        qe.Labels("atmosphere"),  # the compset's DATM option, such as jra or nyf
        qe.Labels("ice"),  # the compset's ice component: cice, dice or sice
    ]
    registry = qe.Registry("crocodash", dimensions=dimensions)
    for r in RULES:
        registry.add(r)
    add_computed_rules(registry)
    return registry


RULES = [
    # ---- any domain -------------------------------------------------------------------
    rule(
        "CROC001",
        "Turn off GM parametrization at high resolution",
        "Below 8 km, eddies are partly resolved, so GM thickness diffusion is usually turned off.",
        changes=[qe.Change("MOM_input", "THICKNESSDIFFUSE", False)],
        dimensions={"resolution": {"lt": 8}},
    ),
    # ---- high latitudes -----------------------------------------------------------------
    rule(
        "CROC010",
        "Consider active sea ice (CICE)",
        "Part of this domain is poleward of 60 degrees, where sea ice forms in winter.",
        level="warning",
        changes=[qe.Change("compset", "ice", "CICE")],
        space=union("arctic_60", "antarctic_60"),
        dimensions={"ice": ["sice"]},  # only when the compset has no active ice
    ),
    rule(
        "CROC011",
        "Use a polar projection for a high-latitude grid",
        "Latitude-longitude cells shrink toward the pole, and the time step must suit the "
        "smallest cells. A polar stereographic grid keeps cells more even.",
        level="info",
        instruction="Build the grid with mom6_forge's Grid.from_projection, using "
        "EPSG:3995 in the Arctic or EPSG:3031 in the Antarctic.",
        space=union("arctic_60", "antarctic_60"),
        quote="if you’re working at higher latitudes, a polar projection would probably make more sense.",
    ),
    rule(
        "CROC012",
        "Finer resolution pays off in the Arctic",
        "Global models struggle at high latitudes, where resolution is coarse and data "
        "sparse. A regional domain at about 1/10 of a degree can improve the simulation "
        "markedly.",
        level="info",
        space=PLACES["arctic"],
        dimensions={
            "resolution": {"gt": 10}
        },  # about 1/10 degree; the km is a judgement
        quote="moving to a higher-resolution domain—on the order of 1/10°—can significantly improve simulation quality.",
    ),
    rule(
        "CROC013",
        "For Antarctic overflows, topography is the main gain",
        "Higher resolution brings better dynamics and better topography. For dense-water "
        "overflows the topography matters most, because it sets their pathways; for SST "
        "or heat transport the dynamics matter more.",
        level="info",
        space=PLACES["antarctic_60"],
        quote="if you work on Antarctic overflows,  the improved topography is the bigger gain because it's essential for capturing the pathways of dense water.",
    ),
    # ---- Coral Triangle and the Indonesian Throughflow ------------------------------------
    rule(
        "CROC101",
        "Force tides: tidal mixing dominates here",
        "This region is a maze of shallow basins and narrow straits where tidal mixing "
        "dominates, amplified by resonance in the passages. Models without tides make up "
        "for it by raising local mixing; with tides, the model mixes where it really happens.",
        changes=[
            qe.Change(
                "configure_forcings",
                "tidal_constituents",
                ["M2", "S2", "K1", "O1"],
                "Tides here are semidiurnal, diurnal or mixed, so force both kinds",
            )
        ],
        instruction="Give configure_forcings the TPXO files and these constituents, and "
        "check tidal phase and amplitude against the region's tide gauges.",
        space=union("coral_triangle", "indonesian_seas"),
        quote="the region consists of many small, shallow, and interconnected basins with narrow straits, where intense tidal mixing plays a dominant role.",
    ),
    rule(
        "CROC102",
        "Measure transport through the Indonesian Throughflow straits",
        "The Throughflow branches across several passages, and observations give the "
        "transport through each. Matching them is the main test of a model here.",
        level="info",
        instruction="Compute transport through Makassar Strait, Lombok Strait, Ombai "
        "Strait and Timor Passage, and compare each with observed estimates such as the "
        "INSTANT moorings'. Agree the targets before tuning, and stop when the magnitudes "
        "match.",
        space=PLACES["indonesian_seas"],
        quote="One critical evaluation metric is the transport through the main ITF channels.",
    ),
    rule(
        "CROC103",
        "Expect to edit the bathymetry of the Throughflow straits",
        "Realistic transport through each strait took 20 or more rounds of bathymetry "
        "edits; tuning viscosity was not enough. Interpolated, smoothed bathymetry often "
        "lowers sills or closes channels where a cell centre falls on land.",
        level="warning",
        instruction="Smooth for stability first, then restore sills toward their observed "
        "depths and open channels the land mask closed. If a strait still carries too much "
        "or too little, widen or narrow it, even if that departs a little from the observed "
        "bathymetry.",
        space=union(*ITF_STRAITS),
        quote="The model required multiple iterations—potentially 20 or more—to arrive at a configuration that gave realistic transports.",
    ),
    rule(
        "CROC104",
        "Lombok Strait spans only a few cells",
        "Lombok Strait is thousands of metres deep on either side of a sill about 200 m "
        "deep. Even at 5 km it spans only a few cells, and its steep slopes cause spurious "
        "diapycnal mixing unless smoothed.",
        level="warning",
        instruction="Count the cells across the strait, set its sill depth to observed "
        "estimates after smoothing, and compare its transport with observations.",
        space=PLACES["lombok_strait"],
        dimensions={
            "resolution": {"gt": 2}
        },  # a judgement: the expert gave no threshold
        quote="Even at a 5-km resolution, the strait might only span a few grid cells.",
    ),
    rule(
        "CROC105",
        "Torres Strait is too coarse to leave open",
        "Torres Strait is very shallow, with near-zero mean transport. At coarse "
        "resolution one cell is too wide or too deep and lets far too much through, so "
        "many models close it.",
        level="warning",
        confidence="possible",
        instruction="Close Torres Strait in the bathymetry, or check that its mean "
        "transport stays near zero.",
        space=PLACES["torres_strait"],
        dimensions={
            "resolution": {"gt": 10}
        },  # a judgement: the expert gave no threshold
        quote="that strait might be represented by a single grid cell that’s too wide or too deep—leading to exaggerated transport.",
    ),
    rule(
        "CROC106",
        "Keep Torres Strait open",
        "At this resolution the model can resolve the tidal reversals that dominate the "
        "strait's flow, while its mean transport stays near zero.",
        level="info",
        instruction="Check that the strait is open in the bathymetry and that its mean "
        "transport is near zero.",
        space=PLACES["torres_strait"],
        dimensions={"resolution": {"le": 10}},
        quote="in higher-resolution configurations, it can be left open, and the model can then resolve tidal reversals",
    ),
    rule(
        "CROC107",
        "Consider rotating the grid to follow the flow",
        "A Coral Triangle configuration rotated by about 20 degrees lined its boundaries "
        "up with the main flows, and was about 30% smaller than a latitude-longitude box.",
        level="info",
        instruction="Try a rotated grid (mom6_forge's Grid.from_center with angle_deg) so "
        "the main currents cross the open boundaries at right angles.",
        space=PLACES["coral_triangle"],
        quote="rotated the grid by about 20 degrees to better match the orientation of the key flows. That also made the model about 30% smaller",
    ),
    rule(
        "CROC108",
        "Evaluate coral heat stress the way satellites do",
        "Degree Heating Weeks come from satellite SST. Process the model's SST the same "
        "way before comparing. A high-resolution model can show local warming, as in "
        "upwelling zones, that satellite products miss.",
        level="info",
        space=PLACES["coral_triangle"],
        quote="SST was important, especially for assessing coral stress using metrics like Degree Heating Weeks.",
    ),
    # ---- Benguela -------------------------------------------------------------------------
    rule(
        "CROC201",
        "Benguela: resolution helps, but biases persist",
        "Models keep a warm SST bias here even at high resolution. Local causes include "
        "coarse coastal winds that weaken the coastal jet and the upwelling; remote "
        "causes include tropical Atlantic SST biases that reach the region through the "
        "boundaries. The front between the Angola and Benguela currents, near 16°S, is "
        "tied to the bathymetry.",
        level="info",
        confidence="possible",
        instruction="Get the bathymetry and coastline right, then check the mean state: "
        "the currents, the position of the front and the cold SST of the upwelling. Tune "
        "the winds and the boundary inflow before mixing or viscosity.",
        space=PLACES["benguela"],
        quote="the Benguela still lags behind other upwelling systems in terms of model fidelity",
    ),
    rule(
        "CROC202",
        "Coarse winds weaken the Benguela upwelling",
        "This atmospheric forcing is coarse next to the coastal winds that drive the "
        "upwelling. Smoothed winds weaken the coastal jet and the upwelling, which warms "
        "the SST.",
        level="warning",
        confidence="possible",
        instruction="If the upwelling matters to your study, consider finer winds, and "
        "compare the upwelling's SST with observations.",
        space=PLACES["benguela"],
        dimensions={"atmosphere": ["jra", "nyf"]},
        quote="insufficient resolution in the coastal wind forcing, which can weaken coastal jets and reduce upwelling.",
    ),
    rule(
        "CROC203",
        "Where to put the edges of a Benguela domain",
        "Include the Benguela upwelling and part of the Angola coast. Extend west to at "
        "least 0°E, past the Cape of Good Hope, to take in the Agulhas retroflection. "
        "Stop short of the tropical Atlantic, where the flow turns zonal and would cross "
        "the northern boundary at a steep angle; the expert suggested a northern edge "
        "around 7°S.",
        level="info",
        space=PLACES["benguela"],
        quote="the domain might extend slightly west of the Cape of Good Hope to capture the Agulhas retroflection and reach north to just below the Angola–Benguela Front—perhaps around 7°S.",
    ),
    # ---- straits elsewhere --------------------------------------------------------------
    rule(
        "CROC301",
        "Keep the Strait of Gibraltar open",
        "Gibraltar is under 50 km wide, about half a cell at 1 degree, but it is the "
        "Mediterranean's only exchange with the Atlantic. Closed, the Mediterranean "
        "grows far too salty.",
        level="warning",
        instruction="Edit the land mask and bathymetry to keep a channel open, and check "
        "the exchange and the salinity of the Mediterranean outflow.",
        space=PLACES["gibraltar_strait"],
        dimensions={
            "resolution": {"gt": 10}
        },  # a judgement: the strait is about 14 km wide
        quote="you cannot close it because it is the only exchange between the Mediterranean and the Atlantic.",
    ),
]


def add_computed_rules(registry: qe.Registry) -> None:
    """Rules that depend on the shape of the domain, not just where it is."""

    @registry.rule(
        "CROC020",
        level="info",
        dimensions={"resolution": {"gt": 0}},
        message="Cell sizes vary a lot in this grid.",
        references=[INTERVIEW_1],
        evidence=[
            {
                "quote": "You’ll have to set your time step based on the smallest grid cells in your domain"
            }
        ],
    )
    def smallest_cells(query, match):
        """The time step is set by the smallest cells"""
        sizes = match.dimensions["resolution"].overlap[0]
        if sizes.hi < 2 * sizes.lo:
            return None
        return {
            "message": f"Cells range from {sizes.lo:.1f} to {sizes.hi:.1f} km, so the "
            f"time step must suit the {sizes.lo:.1f} km cells everywhere. A grid with "
            "more even cells, such as an area-conserving projection, or a polar one at "
            "high latitudes, can run with a longer step."
        }

    @registry.rule(
        "CROC401",
        level="warning",
        space=union(*STRONG_CURRENTS),
        message="The domain's edge cuts a strong current.",
        references=[INTERVIEW_1],
        evidence=[
            {
                "quote": "Open boundary conditions are more stable when energetic currents cross them perpendicularly."
            }
        ],
    )
    def edge_cuts_current(query, match):
        """The domain's edge cuts a strong current"""
        cut = _cut(query, STRONG_CURRENTS)
        if not cut:
            return None
        return {
            "message": f"The open boundary crosses {cut}. Boundaries work best where "
            "strong currents cross them at right angles; a current entering at a steep "
            "angle reflects and causes artifacts. Move the edge, or rotate the grid so "
            "the current crosses it squarely."
        }

    @registry.rule(
        "CROC402",
        level="warning",
        space=union(*ENERGETIC_STRUCTURES),
        message="The domain's edge cuts a retroflection or front.",
        references=[INTERVIEW_1],
        evidence=[
            {
                "quote": "If the current system includes something like a retroflection, that feature really needs to be included within the domain—placing a boundary right at a retroflection usually leads to trouble."
            }
        ],
    )
    def edge_cuts_structure(query, match):
        """The domain's edge cuts a retroflection or front"""
        cut = _cut(query, ENERGETIC_STRUCTURES)
        if not cut:
            return None
        return {
            "message": f"The open boundary crosses {cut}. Strong currents are fine at a "
            "boundary; chaotic flow is not. Take the whole structure into the domain, or "
            "move the edge well away from it."
        }


def _cut(query, names):
    """The places among names that the edge of the query's domain crosses."""
    if query.space is None:
        return ""
    edge = query.space.geometry.boundary
    crossed = [label(name) for name in names if edge.intersects(PLACES[name].geometry)]
    return " and ".join(crossed)


def save(path) -> None:
    """Write the rules to a rule file that declares its dimensions. Computed
    rules are code, so only the others go in it."""
    collection = {
        "type": "FeatureCollection",
        "dimensions": registry().describe()["dimensions"],
        "features": [r.to_feature() for r in RULES],
    }
    text = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        save(sys.argv[1])
    else:
        print(qe.report(registry().query(include_conditional=True)))
