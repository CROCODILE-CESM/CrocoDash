"""The CrocoDash rules: advice that applies to a case's grid, compset and run.

Case() and configure_forcings() query RULES and print each rule that applies as
GeoJSON. Most rules come from expert interviews and cite the passage they rest
on; all are drafts until an expert has reviewed them. RULES.rules lists every rule.

The rules are two queryearth rule files next to this file: rules.geojson holds
Manish's rules, and rules_claude.geojson the rules Claude added from the
interviews on its own, until they are reviewed.

To add or change a rule, edit its GeoJSON Feature in one of the files. Its code
is its category's path plus a name, unique across both files, such as
"REGION/ITF/ITF007" for the Indonesian Throughflow; Claude's rules go in
rules_claude.geojson, under "CLAUDE/".
"""

from pathlib import Path

import numpy as np
import queryearth as qe
from queryearth import space as sp

HERE = Path(__file__).resolve().parent
DIMENSIONS = [
    qe.Axis("resolution", "km"),  # the grid's range of cell sizes
    qe.Axis("cell_size_ratio", "max/min"),  # the largest cell size over the smallest
    qe.Labels("product"),  # the ocean forcing product, such as glorys
    qe.Labels("variable"),
    qe.Labels("atmosphere"),  # the compset's DATM option, such as jra or nyf
    qe.Labels("ice"),  # the compset's ice component: cice, dice or sice
]
RULES = qe.Registry.from_file(
    HERE / "rules.geojson", HERE / "rules_claude.geojson", dimensions=DIMENSIONS
)


def grid_outline(qlon, qlat):
    """A grid's outline from its cell corners, shaped (ny + 1, nx + 1): the ring of
    its outer corners, which queryearth splits at +-180. queryearth takes no ring
    around a pole, so a grid around one becomes the polar cap beyond its outline."""
    edges = (np.s_[0, :], np.s_[1:, -1], np.s_[-1, -2::-1], np.s_[-2::-1, 0])
    lon = np.concatenate([qlon[e] for e in edges])
    lat = np.concatenate([qlat[e] for e in edges])
    if abs(np.sum((np.diff(lon) + 180) % 360 - 180)) > 180:  # once around a pole
        if lat.mean() > 0:
            return sp.box(-180, lat.min(), 180, 90)
        return sp.box(-180, -90, 180, lat.max())
    return sp.polygon(np.column_stack([lon, lat]).tolist())
