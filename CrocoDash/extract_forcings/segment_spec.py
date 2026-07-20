"""Support for OBC boundaries that aren't one of the 4 cardinal full edges --
e.g. a partial edge or a fully interior line next to a masked coastal feature.

Every boundary -- cardinal or custom -- is built directly on
regional_mom6.segment.Segment (Segment.cardinal / Segment.from_hgrid);
CrocoDash does not construct a regional_mom6.experiment for boundary/tide
setup.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from regional_mom6.segment import Segment


@dataclass(frozen=True)
class CustomSegment:
    """A non-cardinal OBC boundary: a straight, index-aligned segment
    described in supergrid axis/index terms (see Segment.from_hgrid).

    ``name`` is this boundary's key everywhere a cardinal string would be
    used (config.json, filenames, ``OBC_SEGMENT_00N`` numbering).
    """

    name: str
    axis: str  # "nyp" (east-west line) or "nxp" (north-south line)
    index: int
    index_range: Optional[Tuple[int, int]] = None
    mom6_index_reverse: bool = False

    @classmethod
    def from_lonlat(
        cls,
        name,
        grid,
        *,
        axis,
        fixed_lat=None,
        fixed_lon=None,
        lon_range=None,
        lat_range=None,
        mom6_index_reverse=False,
    ):
        """Resolve a CustomSegment's supergrid axis/index/index_range from
        physical coordinates, using a mom6_forge-style Grid's own
        nearest-neighbour ``get_indices(lat, lon)``.

        For ``axis="nyp"`` (a line running east-west): pass ``fixed_lat`` and
        ``lon_range=(lon0, lon1)``. For ``axis="nxp"`` (a line running
        north-south): pass ``fixed_lon`` and ``lat_range=(lat0, lat1)``.

        This is a nearest-T-cell approximation intended for simple
        rectilinear domains -- exact for a uniform grid, since ``j`` only
        depends on ``fixed_lat`` and ``i`` only depends on ``fixed_lon``
        there.
        """
        if axis == "nyp":
            j0, i0 = grid.get_indices(fixed_lat, lon_range[0])
            j1, i1 = grid.get_indices(fixed_lat, lon_range[1])
            index = 2 * j0 + 1
            index_range = (2 * min(i0, i1), 2 * max(i0, i1) + 2)
        elif axis == "nxp":
            j0, i0 = grid.get_indices(lat_range[0], fixed_lon)
            j1, i1 = grid.get_indices(lat_range[1], fixed_lon)
            index = 2 * i0 + 1
            index_range = (2 * min(j0, j1), 2 * max(j0, j1) + 2)
        else:
            raise ValueError("axis must be one of: 'nyp', 'nxp'")
        return cls(
            name=name,
            axis=axis,
            index=index,
            index_range=index_range,
            mom6_index_reverse=mom6_index_reverse,
        )

    def to_dict(self):
        return {
            "axis": self.axis,
            "index": self.index,
            "index_range": list(self.index_range) if self.index_range else None,
            "mom6_index_reverse": self.mom6_index_reverse,
        }


def boundary_key(boundary):
    """The string identifier for a boundary entry: itself if a cardinal
    string, or its ``.name`` if a CustomSegment."""
    return boundary.name if isinstance(boundary, CustomSegment) else boundary


def build_segment(hgrid, boundary, segment_name, topo=None, custom_segments=None):
    """Build a Segment for one boundary entry.

    ``boundary`` may be a cardinal string, a CustomSegment instance, or (when
    called from code that only has config.json, e.g. extract_forcings/obc.py)
    a plain boundary-key string paired with ``custom_segments`` -- the
    ``general.custom_segments`` dict read back from config, mapping boundary
    key -> CustomSegment.to_dict().
    """
    spec = boundary if isinstance(boundary, CustomSegment) else None
    if spec is None and custom_segments is not None and boundary in custom_segments:
        raw = custom_segments[boundary]
        spec = CustomSegment(
            name=boundary,
            axis=raw["axis"],
            index=raw["index"],
            index_range=(
                tuple(raw["index_range"]) if raw.get("index_range") else None
            ),
            mom6_index_reverse=raw.get("mom6_index_reverse", False),
        )

    if spec is None:
        return Segment.cardinal(hgrid, boundary, segment_name, topo=topo)

    index_range = slice(*spec.index_range) if spec.index_range else None
    return Segment.from_hgrid(
        hgrid,
        segment_name=segment_name,
        axis=spec.axis,
        index=spec.index,
        index_range=index_range,
        mom6_index_reverse=spec.mom6_index_reverse,
        topo=topo,
    )
