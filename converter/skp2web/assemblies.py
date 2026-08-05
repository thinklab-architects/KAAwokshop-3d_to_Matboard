"""Group a run of louvre slats back into the screen they form.

A timber screen is modelled as twenty separate battens, so a face-by-face
takeoff returns the surface area of twenty sticks - every side, every end cap -
when what gets specified and priced is one screen of so many square metres in
elevation. On the reference model that is 13.17 m2 of stick versus the 6.88 m2
the screen actually measures.

Detection is geometric, so it does not depend on how the groups were named:

* each member is stick-like - its longest dimension well clear of the other two;
* members share a material, run parallel, and are close to the same size;
* they are evenly spaced along one axis;
* and the spacing is small relative to the members themselves.

That last test is what separates a screen from a colonnade. A row of columns is
also a set of parallel sticks at regular centres; what it is not is densely
packed, so a spacing limit tied to member width keeps it out.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .extract import Extraction
from .regions import Region

# Every threshold here is a ratio or a count, never a length. A screen detected
# by millimetres would only be detected in models built at the size this was
# written against; expressed as proportions the same rule reads a furniture
# detail and a facade alike.
MIN_MEMBERS = 5  # fewer than this is a few loose battens, not a screen
_STICK_RATIO = 4.0  # longest dimension vs the next one down
_SIZE_TOL = 0.25  # members may differ this much in cross-section
_LENGTH_TOL = 0.10  # ...and this much in length
_SPACING_TOL = 0.20  # centre-to-centre regularity
_SPACING_VS_WIDTH = 6.0  # a screen is packed; a colonnade is not
_DEPTH_VS_FACE = 0.25  # the set as a whole must read as a panel, not a volume


@dataclass
class Assembly:
    id: int
    name: str
    material: int
    region_ids: list[int]
    element_ids: list[int]
    area: float  # m^2 measured in elevation, the way a screen is specified
    width: float
    height: float
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    members: int = 0
    kind: str = "louvre"
    attrs: dict = field(default_factory=dict)


def _element_boxes(ex: Extraction, regions: list[Region]):
    """Bounding box, material and region list for each leaf element."""
    grouped: dict[int, list[Region]] = defaultdict(list)
    for r in regions:
        grouped[r.element].append(r)

    out = {}
    for element_id, members in grouped.items():
        materials = {m.material for m in members}
        if len(materials) != 1:
            continue  # a mixed-material group is not a single batten
        lo = np.min([m.bbox_min for m in members], axis=0)
        hi = np.max([m.bbox_max for m in members], axis=0)
        out[element_id] = (lo, hi, materials.pop(), members)
    return out


def _common_prefix(names: list[str]) -> str:
    """Longest shared prefix, trimmed at a separator so it reads as a name."""
    if not names:
        return "格柵"
    prefix = names[0]
    for name in names[1:]:
        while not name.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return "格柵"
    return prefix.rstrip("_- 0123456789") or "格柵"


def find_assemblies(ex: Extraction, regions: list[Region]) -> list[Assembly]:
    boxes = _element_boxes(ex, regions)

    # Keep only stick-like elements, keyed so identical battens land together.
    sticks: dict[tuple, list[tuple]] = defaultdict(list)
    for element_id, (lo, hi, material, members) in boxes.items():
        size = hi - lo
        order = np.argsort(size)[::-1]  # long, mid, short
        long_i, mid_i, short_i = (int(i) for i in order)
        if size[mid_i] <= 1e-6 or size[long_i] < _STICK_RATIO * size[mid_i]:
            continue
        key = (
            material,
            long_i,
            round(float(size[long_i]), 2),
            round(float(size[mid_i]), 2),
            round(float(size[short_i]), 2),
        )
        sticks[key].append((element_id, lo, hi, size, members, long_i, mid_i, short_i))

    assemblies: list[Assembly] = []
    for key, group in sticks.items():
        if len(group) < MIN_MEMBERS:
            continue
        material, long_i = key[0], key[1]

        # Members must agree on size; the rounded key gets close, this confirms.
        lengths = np.array([g[3][long_i] for g in group])
        if lengths.std() > _LENGTH_TOL * max(lengths.mean(), 1e-9):
            continue

        # Spacing axis: the one the centres actually spread along.
        centres = np.array([(g[1] + g[2]) / 2 for g in group])
        spread = centres.max(axis=0) - centres.min(axis=0)
        spread[long_i] = -1  # never the members' own length
        spacing_axis = int(np.argmax(spread))
        if spread[spacing_axis] <= 1e-6:
            continue

        order = np.argsort(centres[:, spacing_axis])
        ordered = [group[i] for i in order]
        pitches = np.diff(np.sort(centres[:, spacing_axis]))
        if pitches.mean() <= 1e-9:
            continue
        if pitches.std() > _SPACING_TOL * pitches.mean():
            continue  # irregular: not a manufactured screen

        member_width = float(np.mean([g[3][spacing_axis] for g in ordered]))
        if member_width <= 1e-9 or pitches.mean() > _SPACING_VS_WIDTH * member_width:
            continue  # spaced out like a colonnade, not packed like a louvre

        lo = np.min([g[1] for g in ordered], axis=0)
        hi = np.max([g[2] for g in ordered], axis=0)
        extent = hi - lo

        dims = np.sort(extent)[::-1]
        width, height = float(dims[0]), float(dims[1])
        # Panel-like relative to its own size, so the test holds at any scale.
        if float(dims[2]) > _DEPTH_VS_FACE * height:
            continue
        # Report width across and height up when the panel actually stands up.
        if extent[2] > 1e-6 and abs(extent[2] - height) > abs(extent[2] - width):
            width, height = height, width

        names = [ex.elements[g[0]].name for g in ordered]
        assemblies.append(
            Assembly(
                id=len(assemblies),
                name=_common_prefix(names),
                material=material,
                region_ids=[r.id for g in ordered for r in g[4]],
                element_ids=[g[0] for g in ordered],
                area=width * height,
                width=width,
                height=height,
                bbox_min=lo,
                bbox_max=hi,
                members=len(ordered),
            )
        )
    return assemblies
