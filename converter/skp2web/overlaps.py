"""Find faces that sit on top of each other, so area is not counted twice.

A model assembled from solids has a lot of buried surface. Where a paving slab
rests on the lawn, both the lawn's top and the slab's underside exist as real
faces at the same place; a raw takeoff counts each of them, and neither can be
seen. In the reference house this is 18.7% of the total area.

Three cases, and they are deducted differently:

* **back-to-back** (normals opposed, coplanar) - two solids meeting face to
  face. *Both* faces are buried, so the shared area comes off twice: once from
  each side.
* **duplicate** (normals aligned, coplanar) - the same surface modelled twice.
  One copy is still visible, so the shared area comes off once.
* **plate** (normals opposed, parallel but offset) - the two skins of one thin
  element, such as a floor slab or a pane of glass. The material is laid or
  bought once, so one skin comes off. See the notes on `_PLATE_UPWARD` for why
  a wall is excluded from this.

The shared area is exact rather than estimated. Faces are already triangulated
and triangles are convex, so clipping one against another with Sutherland-
Hodgman yields the intersection polygon directly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .extract import Extraction
from .regions import Region

_PLANE_ANGLE = 1e-3  # normal quantisation for plane bucketing
_PLANE_OFFSET = 1e-3  # 1 mm
_MIN_AREA = 1e-5  # ignore slivers, in m^2

# --- thin plates -----------------------------------------------------------
# A plate's two skins are parallel with their outward normals pointing *away*
# from each other; two solids merely touching have theirs pointing *towards*.
# That sign is the whole discriminator - thickness cannot do the job, because a
# 300 mm lawn slab (deduct the buried underside) and a 300 mm wall (both faces
# are real finishes) are indistinguishable by it.
#
# Nothing here is an absolute length. A rule written in millimetres only holds
# for models of the size it was written against, and this has to survive a
# furniture detail and a masterplan alike. So the tests are a direction, a
# grouping the model already asserts, and a property of the material:
#
#   * the two skins must belong to the *same element* - that is the model's own
#     statement that they are one thing, and it needs no distance at all;
#   * **horizontal** - flooring, roofing and paving are laid on the upper face,
#     so the underside comes off whatever the thickness. Universal convention,
#     no threshold needed;
#   * **vertical** - only glazing comes off, identified by the material being
#     translucent rather than by being under some hard-coded thickness. Glass is
#     bought by the sheet; an opaque wall, panel or door leaf shows both faces
#     and keeps them.
_PLATE_UPWARD = 0.35  # |nz| above this counts as floor/roof-like (a direction)
_OPAQUE = 0.99  # below this the material is glazing


@dataclass
class Overlap:
    a: int  # region id
    b: int  # region id
    area: float  # m^2 shared between them
    opposed: bool  # True = back-to-back interface, False = duplicated geometry
    kind: str = "interface"  # "interface" | "duplicate" | "plate"


def _canonical_plane(normal: np.ndarray, point: np.ndarray):
    """Plane key shared by a face and anything coincident with it.

    The normal is flipped to a canonical direction first, so a face and its
    back-to-back twin - which have opposite normals - land in the same bucket.
    """
    n = np.array(normal, dtype=np.float64)
    for c in n:
        if abs(c) > 1e-6:
            if c < 0:
                n = -n
            break
    d = float(np.dot(n, point))
    key = (
        round(float(n[0]) / _PLANE_ANGLE),
        round(float(n[1]) / _PLANE_ANGLE),
        round(float(n[2]) / _PLANE_ANGLE),
        round(d / _PLANE_OFFSET),
    )
    return key, n


def _plane_axes(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seed = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(n, seed))) > 0.9:
        seed = np.array([1.0, 0.0, 0.0])
    u = np.cross(n, seed)
    u = u / np.linalg.norm(u)
    return u, np.cross(n, u)


def _as_ccw(tri: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman needs the clipping polygon wound consistently."""
    cross = (tri[1, 0] - tri[0, 0]) * (tri[2, 1] - tri[0, 1]) - (tri[1, 1] - tri[0, 1]) * (
        tri[2, 0] - tri[0, 0]
    )
    return tri[::-1] if cross < 0 else tri


def _clip(subject: list[np.ndarray], clipper: np.ndarray) -> list[np.ndarray]:
    out = list(subject)
    for i in range(len(clipper)):
        if not out:
            return []
        a, b = clipper[i], clipper[(i + 1) % len(clipper)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        prev, out = out, []
        for j in range(len(prev)):
            p, q = prev[j], prev[(j + 1) % len(prev)]
            sp = ex * (p[1] - a[1]) - ey * (p[0] - a[0])
            sq = ex * (q[1] - a[1]) - ey * (q[0] - a[0])
            if sp >= 0:
                out.append(p)
            if (sp > 0) != (sq > 0):
                out.append(p + (q - p) * (sp / (sp - sq)))
    return out


def _area(poly: list[np.ndarray]) -> float:
    if len(poly) < 3:
        return 0.0
    total = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


class _Projected:
    """A region's triangles flattened into its plane, with per-triangle areas."""

    __slots__ = ("tris", "areas", "bmin", "bmax", "tri_bmin", "tri_bmax", "covered")

    def __init__(self, region: Region, ex: Extraction, u: np.ndarray, v: np.ndarray):
        tris: list[np.ndarray] = []
        for fid in region.face_ids:
            f = ex.faces[fid]
            for t in f.tris:
                p = f.positions[t]
                tris.append(_as_ccw(np.stack([p @ u, p @ v], axis=1)))
        self.tris = tris
        self.areas = np.array([_area(list(t)) for t in tris])
        self.tri_bmin = np.array([t.min(axis=0) for t in tris]) if tris else np.zeros((0, 2))
        self.tri_bmax = np.array([t.max(axis=0) for t in tris]) if tris else np.zeros((0, 2))
        self.bmin = self.tri_bmin.min(axis=0) if tris else np.zeros(2)
        self.bmax = self.tri_bmax.max(axis=0) if tris else np.zeros(2)
        self.covered = np.zeros(len(tris))


def _find_plates(
    ex: Extraction, regions: list[Region], hidden: dict[int, float]
) -> list[Overlap]:
    """The two skins of a thin plate, counted once instead of twice.

    Buckets by normal *direction* only - unlike a coplanar overlap the two faces
    sit on different planes - then walks each bucket in offset order so only
    faces within a plate's thickness of each other are ever compared.
    """
    buckets: dict[tuple, list[tuple[Region, np.ndarray]]] = defaultdict(list)
    for r in regions:
        n = np.array(r.normal, dtype=np.float64)
        for c in n:
            if abs(c) > 1e-6:
                if c < 0:
                    n = -n
                break
        key = (
            round(float(n[0]) / _PLANE_ANGLE),
            round(float(n[1]) / _PLANE_ANGLE),
            round(float(n[2]) / _PLANE_ANGLE),
        )
        buckets[key].append((r, n))

    pairs: list[Overlap] = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        axis = items[0][1]
        u, v = _plane_axes(axis)
        ordered = sorted(
            ((float(np.dot(axis, r.centroid)), r) for r, _ in items), key=lambda e: e[0]
        )

        flat: dict[int, list[np.ndarray]] = {}
        for _, r in ordered:
            acc: list[np.ndarray] = []
            for fid in r.face_ids:
                f = ex.faces[fid]
                for t in f.tris:
                    p = f.positions[t]
                    acc.append(_as_ccw(np.stack([p @ u, p @ v], axis=1)))
            flat[r.id] = acc

        for i in range(len(ordered)):
            lo_d, lo = ordered[i]
            for j in range(i + 1, len(ordered)):
                hi_d, hi = ordered[j]
                gap = hi_d - lo_d
                if gap < _PLANE_OFFSET:
                    continue  # coplanar; the other pass owns it
                if lo.element != hi.element:
                    continue  # the model does not call these one thing
                if lo.material != hi.material:
                    continue  # two different finishes, both real
                if float(np.dot(lo.normal, hi.normal)) > -0.999:
                    continue  # not a parallel opposed pair

                # Outward normals must point away from each other. `hi` sits at
                # +gap along the axis, so it must face +axis and `lo` face -axis;
                # the reverse means the faces look at each other, which is two
                # solids touching, not one plate.
                if not (float(np.dot(hi.normal, axis)) > 0 > float(np.dot(lo.normal, axis))):
                    continue

                vertical = abs(float(axis[2])) < _PLATE_UPWARD
                if vertical:
                    # Only glazing is bought once per sheet; an opaque wall,
                    # panel or door shows both faces and keeps them.
                    material = ex.materials[lo.material] if lo.material >= 0 else None
                    if material is None or material.opacity >= _OPAQUE:
                        continue

                shared = 0.0
                # The buried skin is the underside for anything floor- or roof-
                # like; for a pane either face will do, so pick deterministically.
                drop = lo if not vertical else max((lo, hi), key=lambda r: r.id)
                keep_tris = flat[hi.id] if drop is lo else flat[lo.id]
                for x in flat[drop.id]:
                    xmin, xmax = x.min(axis=0), x.max(axis=0)
                    for y in keep_tris:
                        if (xmax < y.min(axis=0)).any() or (y.max(axis=0) < xmin).any():
                            continue
                        shared += _area(_clip(list(x), y))
                if shared <= _MIN_AREA:
                    continue

                room = max(drop.area - hidden.get(drop.id, 0.0), 0.0)
                take = min(shared, room)
                if take <= _MIN_AREA:
                    continue
                hidden[drop.id] = hidden.get(drop.id, 0.0) + take
                pairs.append(Overlap(lo.id, hi.id, take, True, "plate"))
    return pairs


def find_overlaps(
    ex: Extraction, regions: list[Region]
) -> tuple[list[Overlap], dict[int, float]]:
    """(overlapping pairs, hidden area per region id).

    Hidden area is accumulated per triangle and clamped to that triangle's own
    area, so a patch covered by two different counterparts is never deducted
    twice. That clamp is per triangle rather than over the whole region, which
    is exact whenever the counterparts do not overlap each other inside a single
    triangle - the normal case in building geometry.
    """
    buckets: dict[tuple, list[tuple[Region, np.ndarray]]] = defaultdict(list)
    for r in regions:
        key, n = _canonical_plane(r.normal, r.centroid)
        buckets[key].append((r, n))

    pairs: list[Overlap] = []
    hidden: dict[int, float] = defaultdict(float)

    for items in buckets.values():
        if len(items) < 2:
            continue
        u, v = _plane_axes(items[0][1])
        proj: dict[int, _Projected] = {}
        for region, _ in items:
            proj[region.id] = _Projected(region, ex, u, v)

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ra, rb = items[i][0], items[j][0]
                pa, pb = proj[ra.id], proj[rb.id]
                if not pa.tris or not pb.tris:
                    continue
                if (pa.bmax < pb.bmin).any() or (pb.bmax < pa.bmin).any():
                    continue

                opposed = float(np.dot(ra.normal, rb.normal)) < 0
                shared = 0.0
                for x, (xmin, xmax) in enumerate(zip(pa.tri_bmin, pa.tri_bmax)):
                    for y, (ymin, ymax) in enumerate(zip(pb.tri_bmin, pb.tri_bmax)):
                        if (xmax < ymin).any() or (ymax < xmin).any():
                            continue
                        a = _area(_clip(list(pa.tris[x]), pb.tris[y]))
                        if a <= _MIN_AREA:
                            continue
                        shared += a
                        # Back-to-back buries both sides; a duplicate leaves one
                        # copy visible, so only one side gives up its area.
                        pa.covered[x] += a
                        if opposed:
                            pb.covered[y] += a
                if shared > _MIN_AREA:
                    pairs.append(Overlap(
                        ra.id, rb.id, shared, opposed,
                        "interface" if opposed else "duplicate",
                    ))

        for region, _ in items:
            p = proj[region.id]
            if len(p.tris):
                hidden[region.id] += float(np.minimum(p.covered, p.areas).sum())

    # Plates are found after the coplanar pass so they can see how much of each
    # face is already spoken for and never deduct the same area twice.
    pairs.extend(_find_plates(ex, regions, hidden))

    return pairs, {k: v for k, v in hidden.items() if v > _MIN_AREA}
