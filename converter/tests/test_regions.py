"""Tests for face merging and dimensioning.

The sample models are built from clean boxes, so nothing in them ever needs
merging - which means the merge path would otherwise ship unexercised. These
build the awkward cases by hand.

Run:  python -m tests.test_regions        (from converter/)
   or: pytest tests/
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skp2web.extract import Element, Extraction, MaterialInfo, RawFace  # noqa: E402
from skp2web.regions import build_regions  # noqa: E402


def quad(corners, material=0, container=0, element=1, area=None) -> RawFace:
    """A planar convex polygon from world-space corners, wound as given.

    ``area`` overrides the computed surface area, which is how a face with an
    opening is modelled here: the outline still encloses the full rectangle but
    the surface covers less.
    """
    pts = np.array(corners, dtype=np.float64)
    tris = np.array([[0, i, i + 1] for i in range(1, len(pts) - 1)], dtype=np.int64)
    # Newell's method rather than the first three points, which are collinear in
    # any outline that carries a split edge.
    n = np.zeros(3)
    for i in range(len(pts)):
        n = n + np.cross(pts[i], pts[(i + 1) % len(pts)])
    n = n / np.linalg.norm(n)
    a = float(
        sum(
            np.linalg.norm(np.cross(pts[t[1]] - pts[t[0]], pts[t[2]] - pts[t[0]])) * 0.5
            for t in tris
        )
    )
    if area is not None:
        a = area
    return RawFace(
        id=-1,  # assigned by make()
        element=element,
        container=container,
        material=material,
        tag=None,
        positions=pts,
        normals=np.tile(n, (len(pts), 1)),
        uvs=np.zeros((len(pts), 2)),
        tris=tris,
        outline=pts,
        normal=n,
        area=a,
    )


def make(faces: list[RawFace], names=("Model", "Wall")) -> Extraction:
    for i, f in enumerate(faces):
        f.id = i
    return Extraction(
        faces=faces,
        elements=[
            Element(0, names[0], "model", "", None, None, {}),
            Element(1, names[1], "group", f"/{names[1]}", 0, None, {}),
        ],
        materials=[
            MaterialInfo(0, "Mat A", (200, 200, 200), 1.0, None, None, {}),
            MaterialInfo(1, "Mat B", (100, 100, 100), 1.0, None, None, {}),
        ],
        model_name="test",
        skp_version="22.0.0",
        skipped_hidden=0,
    )


def approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- merging ---------------------------------------------------------------


@case
def test_coplanar_neighbours_merge():
    """Two halves of one wall, split by a stray edge, are one surface."""
    left = quad([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)])
    right = quad([(2, 0, 0), (5, 0, 0), (5, 0, 3), (2, 0, 3)])
    regions = build_regions(make([left, right]))
    assert len(regions) == 1, f"expected 1 region, got {len(regions)}"
    r = regions[0]
    assert approx(r.area, 15.0), r.area
    assert approx(r.length, 5.0) and approx(r.width, 3.0), (r.length, r.width)
    assert r.length_label == "寬 × 高"
    assert len(r.face_ids) == 2


@case
def test_different_materials_do_not_merge():
    left = quad([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)], material=0)
    right = quad([(2, 0, 0), (5, 0, 0), (5, 0, 3), (2, 0, 3)], material=1)
    assert len(build_regions(make([left, right]))) == 2


@case
def test_different_containers_do_not_merge():
    left = quad([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)], container=0)
    right = quad([(2, 0, 0), (5, 0, 0), (5, 0, 3), (2, 0, 3)], container=1)
    assert len(build_regions(make([left, right]))) == 2


@case
def test_perpendicular_neighbours_do_not_merge():
    """A box corner shares an edge but is two surfaces, not one."""
    front = quad([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)])
    side = quad([(2, 0, 0), (2, 4, 0), (2, 4, 3), (2, 0, 3)])
    assert len(build_regions(make([front, side]))) == 2


@case
def test_coplanar_but_apart_do_not_merge():
    a = quad([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)])
    b = quad([(9, 0, 0), (11, 0, 0), (11, 0, 3), (9, 0, 3)])
    assert len(build_regions(make([a, b]))) == 2


@case
def test_parallel_offset_planes_do_not_merge():
    """Same normal, 10 mm apart, touching edge-on: still two surfaces."""
    a = quad([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)])
    b = quad([(2, 0.01, 0), (5, 0.01, 0), (5, 0.01, 3), (2, 0.01, 3)])
    assert len(build_regions(make([a, b]))) == 2


@case
def test_chain_of_three_merges_transitively():
    a = quad([(0, 0, 0), (1, 0, 0), (1, 0, 3), (0, 0, 3)])
    b = quad([(1, 0, 0), (2, 0, 0), (2, 0, 3), (1, 0, 3)])
    c = quad([(2, 0, 0), (3, 0, 0), (3, 0, 3), (2, 0, 3)])
    regions = build_regions(make([a, b, c]))
    assert len(regions) == 1
    assert approx(regions[0].length, 3.0) and approx(regions[0].area, 9.0)


# --- dimensioning ----------------------------------------------------------


@case
def test_rotated_slab_reports_its_own_edges():
    """A 6x4 slab turned 30 degrees reports 6 and 4, not its 8.2x7.5 AABB."""
    t = math.radians(30)
    c, s = math.cos(t), math.sin(t)
    corners = [(0, 0), (6, 0), (6, 4), (0, 4)]
    rotated = [(x * c - y * s, x * s + y * c, 2.5) for x, y in corners]
    regions = build_regions(make([quad(rotated)], names=("Model", "Slab")))
    assert len(regions) == 1
    r = regions[0]
    assert r.category in ("floor", "site"), r.category
    assert r.shape == "rectangle", r.shape
    assert sorted(round(e, 6) for e in r.edges) == [4.0, 4.0, 6.0, 6.0], r.edges
    assert approx(r.length, 6.0, 1e-6) and approx(r.width, 4.0, 1e-6), (r.length, r.width)
    assert approx(r.area, 24.0, 1e-6)
    # The axis-aligned box would have been much larger - prove we beat it.
    pts = np.array(rotated)
    aabb = (pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min())
    assert aabb > 30.0 and r.length * r.width < aabb - 5


@case
def test_triangle_reports_three_sides_and_true_area():
    """A 3-4-5 right triangle: three sides, area 6, not a 3x4 box of area 12."""
    tri = quad([(0, 0, 0), (4, 0, 0), (0, 0, 3)])
    r = build_regions(make([tri]))[0]
    assert r.shape == "triangle", r.shape
    assert sorted(round(e, 6) for e in r.edges) == [3.0, 4.0, 5.0], r.edges
    assert approx(r.area, 6.0, 1e-6), r.area
    assert r.length_label == "底 × 高"
    # base is the longest side; height is the perpendicular onto it
    assert approx(r.length, 5.0, 1e-6), r.length
    assert approx(r.width, 2.4, 1e-6), r.width          # 2*6/5
    assert approx(r.length * r.width / 2, r.area, 1e-9)  # consistent triangle
    assert approx(r.solid_ratio, 1.0, 1e-6)              # no openings


@case
def test_sloped_triangle_gable_measures_along_the_slope():
    """A gable end leaning back: sides follow the real geometry, not the plan."""
    tri = quad([(0, 0, 0), (6, 0, 0), (3, 0, 4)])
    r = build_regions(make([tri], names=("Model", "Gable")))[0]
    assert r.shape == "triangle"
    assert approx(r.area, 12.0, 1e-6)
    assert sorted(round(e, 4) for e in r.edges) == [5.0, 5.0, 6.0], r.edges


@case
def test_opening_shows_up_as_solid_ratio():
    """A 4x3 wall with a 2 m2 window: outline still 12, surface only 10."""
    wall = quad([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)], area=10.0)
    r = build_regions(make([wall]))[0]
    assert r.shape == "rectangle"
    assert approx(r.area, 10.0)
    assert approx(r.length, 4.0) and approx(r.width, 3.0)
    assert approx(r.solid_ratio, 10.0 / 12.0, 1e-6), r.solid_ratio


@case
def test_collinear_split_points_do_not_become_a_polygon():
    """SketchUp splits edges where other geometry lands; still a rectangle."""
    wall = quad([(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 0, 3), (1, 0, 3), (0, 0, 3)])
    r = build_regions(make([wall]))[0]
    assert r.shape == "rectangle", (r.shape, r.edges)
    assert len(r.edges) == 4, r.edges
    assert approx(r.length, 4.0) and approx(r.width, 3.0)


@case
def test_sloped_roof_reports_rafter_length_not_plan():
    """A 30-degree pitch 4 m across in plan is 4/cos(30) = 4.619 m up the slope."""
    run, rise, width = 4.0, 4.0 * math.tan(math.radians(30)), 5.0
    face = quad([(0, 0, 0), (width, 0, 0), (width, run, rise), (0, run, rise)])
    regions = build_regions(make([face], names=("Model", "Roof_Plane")))
    r = regions[0]
    assert r.category == "roof", r.category
    slope = math.hypot(run, rise)
    assert approx(max(r.length, r.width), width, 1e-6)
    assert approx(min(r.length, r.width), slope, 1e-6), (min(r.length, r.width), slope)
    assert min(r.length, r.width) > run  # longer than the plan projection


@case
def test_wall_orientation_labels():
    wall = quad([(0, 0, 0), (4, 0, 0), (4, 0, 2.8), (0, 0, 2.8)])
    r = build_regions(make([wall]))[0]
    assert r.category == "wall"
    assert approx(r.length, 4.0) and approx(r.width, 2.8)


@case
def test_ceiling_detected_by_downward_normal():
    ceiling = quad([(0, 0, 3), (0, 4, 3), (5, 4, 3), (5, 0, 3)])
    r = build_regions(make([ceiling], names=("Model", "Plane")))[0]
    assert float(r.normal[2]) < 0, r.normal
    assert r.category == "ceiling", r.category


@case
def test_name_promotes_flat_slab_to_roof():
    """Geometry alone cannot tell a flat roof from a floor; the name can."""
    flat = quad([(0, 0, 7), (5, 0, 7), (5, 4, 7), (0, 4, 7)])
    r = build_regions(make([flat], names=("Model", "Main_Roof_Deck")))[0]
    assert r.category == "roof", r.category


@case
def test_name_never_turns_a_wall_into_a_floor():
    wall = quad([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)])
    r = build_regions(make([wall], names=("Model", "Ground_Floor_Partition")))[0]
    assert r.category == "wall", r.category


@case
def test_l_shape_traces_its_real_six_sided_outline():
    """Two arms of an L merge into one polygon with six sides, not a box.

    Note the extra vertex at (1,0,1) on the wide arm. SketchUp always splits an
    edge where another face meets it partway along, so a real model never has
    the T-junction a naive construction would produce - and edge matching is
    exact precisely because it can rely on that.
    """
    wide = quad([(0, 0, 0), (4, 0, 0), (4, 0, 1), (1, 0, 1), (0, 0, 1)])
    tall = quad([(0, 0, 1), (1, 0, 1), (1, 0, 4), (0, 0, 4)])
    regions = build_regions(make([wide, tall]))
    assert len(regions) == 1, len(regions)
    r = regions[0]
    assert r.shape == "polygon", r.shape
    assert approx(r.area, 4.0 + 3.0), r.area
    # The L's perimeter: 4 + 1 + 3 + 3 + 1 + ... traced right round.
    assert len(r.edges) == 6, r.edges
    assert approx(sum(r.edges), 4 + 1 + 3 + 1 + 3 + 4, 1e-6), r.edges
    # The reported pair is an extent, and says so.
    assert "範圍" in r.length_label, r.length_label
    assert approx(r.length, 4.0) and approx(r.width, 4.0)
    # No openings: the traced outline encloses exactly the surface.
    assert approx(r.solid_ratio, 1.0, 1e-6), r.solid_ratio


@case
def test_shallow_fall_still_measured_as_a_plan_rectangle():
    """A 1:50 drainage fall is a flat roof, not a pitched one."""
    face = quad([(0, 0, 3), (6, 0, 3), (6, 4, 3.08), (0, 4, 3.08)])
    r = build_regions(make([face], names=("Model", "Flat_Roof")))[0]
    assert approx(r.length, 6.0, 1e-3) and approx(r.width, 4.0, 1e-3), (r.length, r.width)


def main() -> int:
    failures = []
    for fn in CASES:
        try:
            fn()
            print(f"  pass  {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, exc))
            print(f"  FAIL  {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, exc))
            print(f"  ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
