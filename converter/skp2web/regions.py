"""Group raw faces into clickable regions and measure them.

A wall in SketchUp is rarely one face: edges, openings and stray splits chop it
into pieces. Clicking any piece should report the whole wall, so faces are merged
when they are in the same container, carry the same material, lie on the same
plane, and physically share an edge.

Dimensions come from the region's **actual outline**, not from a box drawn round
it. The boundary is traced by dropping every edge shared by two faces in the
region and chaining what is left, then collinear points are merged away (a
SketchUp rectangle is often five or six vertices because other geometry split
its edges). What gets reported depends on the shape that comes out:

* a **rectangle** reports its two side lengths - for a wall, ordered as width
  then height, so the numbers read the way an elevation does;
* a **triangle** reports its three sides;
* anything else reports every edge length, plus its overall extent as context.

Area is always the true surface area summed from triangles, so openings and
irregular outlines are already accounted for and it never depends on the shape
classification above.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field

import numpy as np

from .extract import Extraction, RawFace

# Merge tolerances.
_COPLANAR_DOT = 0.9998  # ~1.1 degrees
_PLANE_TOL_M = 0.001  # 1 mm
_WELD_M = 1e-4  # 0.1 mm vertex quantisation for edge matching

# Orientation thresholds on the world-space normal's Z component.
# cos(8 deg): anything flatter than that is measured as a plan rectangle. It has
# to be this tight because a normal roof pitch is nowhere near flat - a 30 deg
# pitch has nz = 0.87, and treating it as horizontal would report its plan
# projection instead of the real rafter length.
_HORIZONTAL = 0.990
_VERTICAL = 0.25

CATEGORY_LABELS = {
    "wall": "牆面",
    "floor": "地板／樓板",
    "ceiling": "天花",
    "roof": "屋頂／斜面",
    "site": "地坪／景觀",
    "other": "其他",
}

_KEYWORDS = (
    # (category, substrings) - checked against element name, tag and material name
    ("roof", ("roof", "屋頂", "屋面", "女兒牆頂", "parapet-top")),
    ("ceiling", ("ceiling", "soffit", "天花", "頂棚")),
    ("floor", ("floor", "slab", "地板", "樓板", "地坪")),
    ("site", ("site", "ground", "lawn", "grass", "paving", "terrain", "草皮", "鋪面", "基地", "水池", "planting", "landscape")),
    ("wall", ("wall", "cladding", "facade", "牆", "外牆", "隔間")),
)


@dataclass
class Region:
    id: int
    material: int
    category: str
    element: int
    tag: str | None
    face_ids: list[int]
    area: float  # m^2, true surface area summed from triangles
    shape: str  # "rectangle" | "triangle" | "polygon" | "unknown"
    edges: list[float]  # outline edge lengths in m, collinear points merged out
    length: float  # m, primary dimension (see length_label)
    width: float  # m, secondary dimension
    length_label: str  # what the pair means, e.g. "寬 × 高" or "底 × 高"
    normal: np.ndarray
    centroid: np.ndarray
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    solid_ratio: float  # area / outline area; below 1 means the face has openings
    tri_count: int = 0
    # Filled in by overlaps.find_overlaps: how much of this surface is buried
    # under a coplanar counterpart and therefore not really there to be finished.
    hidden: float = 0.0


# ---------------------------------------------------------------------------
# union-find
# ---------------------------------------------------------------------------


class _DisjointSet:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------


def _quantize(p: np.ndarray) -> tuple[int, int, int]:
    return (
        int(round(p[0] / _WELD_M)),
        int(round(p[1] / _WELD_M)),
        int(round(p[2] / _WELD_M)),
    )


def _trace_outline(group) -> np.ndarray:
    """The region's real boundary loop, in world metres.

    Edges used by two faces of the region are interior and dropped; the rest are
    chained head to tail. Faces in a region share a plane and a winding, so the
    survivors join up without any orientation fixing. Returns the longest loop,
    or an empty array if the boundary does not close (which happens with
    self-intersecting or otherwise malformed geometry).
    """
    undirected: dict[tuple, int] = {}
    directed: dict[tuple, tuple] = {}
    for f in group:
        pts = f.outline
        if len(pts) < 3:
            continue
        keys = [_quantize(p) for p in pts]
        for i in range(len(keys)):
            a, b = keys[i], keys[(i + 1) % len(keys)]
            if a == b:
                continue
            undirected[(a, b) if a < b else (b, a)] = (
                undirected.get((a, b) if a < b else (b, a), 0) + 1
            )
            directed[(a, b)] = (pts[i], pts[(i + 1) % len(pts)])

    nxt: dict[tuple, tuple] = {}
    for (a, b), (pa, _pb) in directed.items():
        if undirected.get((a, b) if a < b else (b, a), 0) == 1:
            nxt[a] = (b, pa)

    loops: list[np.ndarray] = []
    unvisited = set(nxt)
    while unvisited:
        start = next(iter(unvisited))
        loop: list[np.ndarray] = []
        node = start
        while node in nxt and node in unvisited:
            unvisited.discard(node)
            node, point = nxt[node]
            loop.append(point)
        if node == start and len(loop) >= 3:
            loops.append(np.array(loop))
    if not loops:
        return np.zeros((0, 3), dtype=np.float64)
    return max(loops, key=len)


def _drop_collinear(loop: np.ndarray, tol_deg: float = 0.75) -> np.ndarray:
    """Merge away vertices that only exist because SketchUp split an edge."""
    if len(loop) < 3:
        return loop
    sin_tol = math.sin(math.radians(tol_deg))
    keep: list[np.ndarray] = []
    n = len(loop)
    for i in range(n):
        prev = keep[-1] if keep else loop[(i - 1) % n]
        cur, nxt_pt = loop[i], loop[(i + 1) % n]
        a, b = cur - prev, nxt_pt - cur
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            continue
        if np.linalg.norm(np.cross(a, b)) / (na * nb) > sin_tol:
            keep.append(cur)
    # The first vertex was tested against the original predecessor; re-test it
    # now that its true neighbours are known.
    if len(keep) >= 3:
        a = keep[0] - keep[-1]
        b = keep[1] - keep[0]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na > 1e-9 and nb > 1e-9 and np.linalg.norm(np.cross(a, b)) / (na * nb) <= sin_tol:
            keep.pop(0)
    return np.array(keep) if len(keep) >= 3 else loop


def _polygon_area(loop: np.ndarray) -> float:
    """Area of a planar loop in 3D, via the vector-area formula."""
    if len(loop) < 3:
        return 0.0
    total = np.zeros(3)
    for i in range(len(loop)):
        total = total + np.cross(loop[i], loop[(i + 1) % len(loop)])
    return float(np.linalg.norm(total) * 0.5)


def _edge_lengths(loop: np.ndarray) -> list[float]:
    if len(loop) < 2:
        return []
    return [
        float(np.linalg.norm(loop[(i + 1) % len(loop)] - loop[i])) for i in range(len(loop))
    ]


def _is_rectangle(loop: np.ndarray, tol_deg: float = 1.5) -> bool:
    if len(loop) != 4:
        return False
    cos_tol = math.cos(math.radians(90 - tol_deg))
    for i in range(4):
        a = loop[i] - loop[i - 1]
        b = loop[(i + 1) % 4] - loop[i]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            return False
        if abs(float(np.dot(a, b)) / (na * nb)) > cos_tol:
            return False
    return True


def _plane_axes(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray, str]:
    """Two in-plane axes to describe a surface along, and what they mean."""
    z = np.array([0.0, 0.0, 1.0])
    nz = float(normal[2])
    horizontal = np.cross(normal, z)
    n = float(np.linalg.norm(horizontal))

    if n < 1e-9:  # dead flat: world X and Y
        return np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), "長 × 寬"

    u = horizontal / n
    if abs(nz) <= _VERTICAL:
        # Vertical surface: across, then straight up - the way an elevation reads.
        return u, z, "寬 × 高"
    if abs(nz) < _HORIZONTAL:
        # Sloped: along the ridge, then up the slope (true rafter length).
        v = np.cross(normal, u)
        return u, v / max(float(np.linalg.norm(v)), 1e-9), "沿屋脊 × 沿坡長"
    return np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), "長 × 寬"


def _measure(loop: np.ndarray, normal: np.ndarray) -> tuple[str, list[float], float, float, str]:
    """(shape, edge lengths, primary, secondary, label) from the real outline."""
    u, v, axis_label = _plane_axes(normal)
    if len(loop) < 3:
        return "unknown", [], 0.0, 0.0, axis_label
    edges = _edge_lengths(loop)

    if len(loop) == 3:
        # A triangle is dimensioned by its sides. The headline pair is the
        # longest side and the height standing on it, so length x width still
        # means something - but the three sides are what gets reported.
        base = max(edges)
        height = 2.0 * _polygon_area(loop) / base if base > 1e-9 else 0.0
        return "triangle", edges, base, height, "底 × 高"

    if _is_rectangle(loop):
        e0, e1 = loop[1] - loop[0], loop[2] - loop[1]
        l0, l1 = float(np.linalg.norm(e0)), float(np.linalg.norm(e1))
        if l0 < 1e-9 or l1 < 1e-9:
            return "rectangle", edges, max(l0, l1), min(l0, l1), axis_label
        # Order the pair to match the axis convention: across first, up second.
        if abs(float(np.dot(e0 / l0, v))) > abs(float(np.dot(e1 / l1, v))):
            return "rectangle", edges, l1, l0, axis_label
        return "rectangle", edges, l0, l1, axis_label

    # Any other outline: every edge is reported, and the pair is only an extent,
    # labelled as such rather than dressed up as a dimension.
    pu, pv = loop @ u, loop @ v
    return (
        "polygon",
        edges,
        float(pu.max() - pu.min()),
        float(pv.max() - pv.min()),
        f"{axis_label}（範圍）",
    )


def _normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def _classify(normal: np.ndarray, hints: str) -> str:
    nz = float(normal[2])
    if nz >= _HORIZONTAL:
        geometric = "floor"
    elif nz <= -_HORIZONTAL:
        geometric = "ceiling"
    elif abs(nz) <= _VERTICAL:
        geometric = "wall"
    else:
        geometric = "roof"

    text = _normalize_text(hints)
    for category, words in _KEYWORDS:
        if any(w in text for w in words):
            # Names disambiguate what geometry cannot: an upward horizontal face
            # is equally a floor, a flat roof or the site. But never let a name
            # turn a vertical surface into a floor.
            if geometric == "wall" and category not in ("wall",):
                continue
            if geometric in ("floor", "ceiling", "roof") and category == "wall":
                continue
            return category
    return geometric


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def build_regions(ex: Extraction) -> list[Region]:
    faces = ex.faces
    if not faces:
        return []

    dsu = _DisjointSet(len(faces))

    # Map every outer-loop edge to the faces that use it, then union faces that
    # share an edge and agree on container, material and plane.
    edge_owners: dict[tuple, list[int]] = {}
    planes: list[tuple[np.ndarray, float]] = []
    for f in faces:
        planes.append((f.normal, float(np.dot(f.normal, f.positions[0]))))
        outline = f.outline
        if len(outline) < 2:
            continue
        keys = [_quantize(p) for p in outline]
        for i in range(len(keys)):
            a, b = keys[i], keys[(i + 1) % len(keys)]
            if a == b:
                continue
            edge_owners.setdefault((a, b) if a < b else (b, a), []).append(f.id)

    for owners in edge_owners.values():
        if len(owners) < 2:
            continue
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a, b = faces[owners[i]], faces[owners[j]]
                if a.container != b.container or a.material != b.material:
                    continue
                na, da = planes[a.id]
                nb, db = planes[b.id]
                if float(np.dot(na, nb)) < _COPLANAR_DOT:
                    continue
                if abs(da - db) > _PLANE_TOL_M:
                    continue
                dsu.union(a.id, b.id)

    clusters: dict[int, list[int]] = {}
    for f in faces:
        clusters.setdefault(dsu.find(f.id), []).append(f.id)

    regions: list[Region] = []
    for members in clusters.values():
        group = [faces[i] for i in members]
        area = float(sum(f.area for f in group))
        if area <= 0:
            continue

        weights = np.array([max(f.area, 1e-12) for f in group])
        normal = (np.stack([f.normal for f in group]) * weights[:, None]).sum(axis=0)
        n = np.linalg.norm(normal)
        normal = normal / n if n > 1e-12 else group[0].normal

        pts = np.concatenate([f.outline if len(f.outline) else f.positions for f in group])
        bbox_min = pts.min(axis=0)
        bbox_max = pts.max(axis=0)
        centroid = _area_weighted_centroid(group)

        head = group[0]
        element = ex.elements[head.element]
        material_name = ex.materials[head.material].name if head.material >= 0 else ""
        hints = " ".join(filter(None, [element.name, element.path, head.tag or "", material_name]))
        category = _classify(normal, hints)

        loop = _drop_collinear(_trace_outline(group))
        shape, edges, length, width, label = _measure(loop, normal)
        # Below 1 means the outline encloses more than the surface actually
        # covers - i.e. the face has openings cut out of it.
        outline_area = _polygon_area(loop)
        solid = float(area / outline_area) if outline_area > 1e-9 else 1.0

        regions.append(
            Region(
                id=len(regions),
                material=head.material,
                category=category,
                element=head.element,
                tag=head.tag,
                face_ids=members,
                area=area,
                shape=shape,
                edges=edges,
                length=length,
                width=width,
                length_label=label,
                normal=normal,
                centroid=centroid,
                bbox_min=bbox_min,
                bbox_max=bbox_max,
                solid_ratio=min(solid, 1.0),
                tri_count=int(sum(len(f.tris) for f in group)),
            )
        )

    return regions


def _area_weighted_centroid(group: list[RawFace]) -> np.ndarray:
    total = 0.0
    acc = np.zeros(3)
    for f in group:
        if f.tris.size == 0:
            continue
        a = f.positions[f.tris[:, 0]]
        b = f.positions[f.tris[:, 1]]
        c = f.positions[f.tris[:, 2]]
        areas = np.linalg.norm(np.cross(b - a, c - a), axis=1) * 0.5
        acc += ((a + b + c) / 3.0 * areas[:, None]).sum(axis=0)
        total += float(areas.sum())
    return acc / total if total > 1e-12 else np.zeros(3)
