"""Tests for coplanar overlap detection.

Run:  python -m tests.test_overlaps        (from converter/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skp2web.overlaps import find_overlaps  # noqa: E402
from skp2web.regions import build_regions  # noqa: E402
from tests.test_regions import approx, make, quad  # noqa: E402

# The plate rule asks the model whether two skins are one thing, so every pair
# in these fixtures has to share an element id (quad's default).


def run(faces):
    ex = make(faces)
    regions = build_regions(ex)
    pairs, hidden = find_overlaps(ex, regions)
    return regions, pairs, {k: round(v, 6) for k, v in hidden.items()}


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- back-to-back interfaces ----------------------------------------------


@case
def test_coincident_opposed_faces_bury_both_sides():
    """Two solids meeting face to face: neither surface can be seen."""
    up = quad([(0, 0, 3), (4, 0, 3), (4, 5, 3), (0, 5, 3)], container=0)
    down = quad([(0, 0, 3), (0, 5, 3), (4, 5, 3), (4, 0, 3)], container=1)
    regions, pairs, hidden = run([up, down])
    assert len(regions) == 2
    assert len(pairs) == 1, pairs
    p = pairs[0]
    assert p.opposed is True
    assert approx(p.area, 20.0, 1e-6), p.area
    # both give up the whole 20 m2
    assert len(hidden) == 2, hidden
    assert all(approx(v, 20.0, 1e-6) for v in hidden.values()), hidden


@case
def test_small_slab_on_a_big_one_hides_only_its_footprint():
    """A 2x2 pad resting on a 10x10 slab buries 4 m2, not the whole slab."""
    big = quad([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], container=0)
    pad = quad([(3, 3, 0), (3, 5, 0), (5, 5, 0), (5, 3, 0)], container=1)
    regions, pairs, hidden = run([big, pad])
    assert len(pairs) == 1 and pairs[0].opposed
    assert approx(pairs[0].area, 4.0, 1e-6), pairs[0].area
    big_id = next(r.id for r in regions if approx(r.area, 100.0))
    pad_id = next(r.id for r in regions if approx(r.area, 4.0))
    assert approx(hidden[big_id], 4.0, 1e-6), hidden
    assert approx(hidden[pad_id], 4.0, 1e-6), hidden
    exposed = sum(r.area - hidden.get(r.id, 0.0) for r in regions)
    assert approx(exposed, 96.0, 1e-6), exposed  # 100 + 4 - 4 - 4


@case
def test_partial_overlap_measured_exactly():
    """Half-lapped squares share exactly half of one."""
    a = quad([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)], container=0)
    b = quad([(2, 0, 0), (2, 4, 0), (6, 4, 0), (6, 0, 0)], container=1)
    _, pairs, _ = run([a, b])
    assert len(pairs) == 1
    assert approx(pairs[0].area, 8.0, 1e-6), pairs[0].area


# --- duplicated geometry ---------------------------------------------------


@case
def test_duplicate_faces_are_counted_once_not_zero():
    """Same surface modelled twice: one copy still shows, so deduct one."""
    a = quad([(0, 0, 0), (3, 0, 0), (3, 4, 0), (0, 4, 0)], container=0)
    b = quad([(0, 0, 0), (3, 0, 0), (3, 4, 0), (0, 4, 0)], container=1)
    regions, pairs, hidden = run([a, b])
    assert len(pairs) == 1
    assert pairs[0].opposed is False, "same winding means same normal"
    assert approx(pairs[0].area, 12.0, 1e-6)
    assert len(hidden) == 1, hidden  # only one side gives up its area
    assert approx(next(iter(hidden.values())), 12.0, 1e-6)
    exposed = sum(r.area - hidden.get(r.id, 0.0) for r in regions)
    assert approx(exposed, 12.0, 1e-6), exposed  # 24 raw -> 12 real


# --- thin plates -----------------------------------------------------------


def slab(z_bottom, z_top, size=4.0, material=0, container=0):
    """A horizontal plate: upward top skin, downward bottom skin."""
    s = size
    top = quad([(0, 0, z_top), (s, 0, z_top), (s, s, z_top), (0, s, z_top)],
               material=material, container=container)
    bottom = quad([(0, 0, z_bottom), (0, s, z_bottom), (s, s, z_bottom), (s, 0, z_bottom)],
                  material=material, container=container)
    return top, bottom


@case
def test_floor_slab_counts_its_top_only():
    """A 30 mm slab: flooring is laid on the upper face, not underneath it."""
    top, bottom = slab(0.0, 0.03)
    regions, pairs, hidden = run([top, bottom])
    plates = [p for p in pairs if p.kind == "plate"]
    assert len(plates) == 1, [(p.kind, p.area) for p in pairs]
    assert approx(plates[0].area, 16.0, 1e-6)
    # exactly one of the two skins gives up its area
    assert len(hidden) == 1, hidden
    down = next(r for r in regions if r.normal[2] < 0)
    assert down.id in hidden, "the underside is the one that should come off"
    exposed = sum(r.area - hidden.get(r.id, 0.0) for r in regions)
    assert approx(exposed, 16.0, 1e-6), exposed  # 32 raw -> 16


@case
def test_thick_ground_slab_still_counts_its_top_only():
    """Thickness is irrelevant for a horizontal plate: 300 mm behaves the same."""
    top, bottom = slab(-0.3, 0.0, size=6.0)
    regions, pairs, hidden = run([top, bottom])
    assert [p.kind for p in pairs] == ["plate"]
    exposed = sum(r.area - hidden.get(r.id, 0.0) for r in regions)
    assert approx(exposed, 36.0, 1e-6), exposed


@case
def test_wall_keeps_both_faces():
    """A 300 mm wall is finished on both sides; neither face comes off."""
    outer = quad([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)])
    inner = quad([(0, 0.3, 0), (0, 0.3, 3), (4, 0.3, 3), (4, 0.3, 0)])
    regions, pairs, hidden = run([outer, inner])
    assert not [p for p in pairs if p.kind == "plate"], "a wall is not a plate"
    assert hidden == {}, hidden
    assert approx(sum(r.area for r in regions), 24.0)


@case
def test_glass_pane_counts_once():
    """Glazing is bought by the sheet, so a pane gives up one face.

    Identified by the material being translucent rather than by thickness: a
    hard-coded millimetre limit would miss thicker glazing and would catch an
    opaque panel of the same build-up.
    """
    front = quad([(0, 0, 0), (3, 0, 0), (3, 0, 2), (0, 0, 2)], material=1)
    back = quad([(0, 0.03, 0), (0, 0.03, 2), (3, 0.03, 2), (3, 0.03, 0)], material=1)
    ex = make([front, back])
    ex.materials[1].opacity = 0.4  # glazing
    regions = build_regions(ex)
    pairs, hidden = find_overlaps(ex, regions)
    plates = [p for p in pairs if p.kind == "plate"]
    assert len(plates) == 1, [(p.kind, p.area) for p in pairs]
    exposed = sum(r.area - hidden.get(r.id, 0.0) for r in regions)
    assert approx(exposed, 6.0, 1e-6), exposed


@case
def test_thick_glazing_counts_once_too():
    """No thickness limit: a 150 mm glazed unit is still one sheet."""
    front = quad([(0, 0, 0), (3, 0, 0), (3, 0, 2), (0, 0, 2)], material=1)
    back = quad([(0, 0.15, 0), (0, 0.15, 2), (3, 0.15, 2), (3, 0.15, 0)], material=1)
    ex = make([front, back])
    ex.materials[1].opacity = 0.35
    regions = build_regions(ex)
    pairs, hidden = find_overlaps(ex, regions)
    assert [p.kind for p in pairs] == ["plate"], pairs
    assert approx(sum(r.area - hidden.get(r.id, 0.0) for r in regions), 6.0, 1e-6)


@case
def test_a_thin_opaque_panel_keeps_both_faces():
    """A 30 mm door leaf is seen from both sides; only glazing is halved."""
    front = quad([(0, 0, 0), (1, 0, 0), (1, 0, 2), (0, 0, 2)])
    back = quad([(0, 0.03, 0), (0, 0.03, 2), (1, 0.03, 2), (1, 0.03, 0)])
    _, pairs, hidden = run([front, back])
    assert not [p for p in pairs if p.kind == "plate"], pairs
    assert hidden == {}


@case
def test_plate_needs_the_same_material_on_both_skins():
    """Oak above, painted soffit below: two different finishes, both real."""
    top, bottom = slab(0.0, 0.03)
    bottom.material = 1
    regions, pairs, hidden = run([top, bottom])
    assert not [p for p in pairs if p.kind == "plate"], pairs
    assert hidden == {}


@case
def test_faces_looking_at_each_other_are_not_a_plate():
    """Two solids 30 mm apart face inwards - that is a gap, not a plate."""
    lower = quad([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)])           # faces up
    upper = quad([(0, 0, 0.03), (0, 4, 0.03), (4, 4, 0.03), (4, 0, 0.03)])  # faces down
    _, pairs, hidden = run([lower, upper])
    assert not [p for p in pairs if p.kind == "plate"], pairs
    assert hidden == {}


@case
def test_plate_and_coplanar_deductions_do_not_double_up():
    """A slab buried under paving must never lose more area than it has."""
    top, bottom = slab(0.0, 0.03)
    paving = quad([(0, 0, 0.03), (0, 4, 0.03), (4, 4, 0.03), (4, 0, 0.03)], container=1)
    regions, _, hidden = run([top, bottom, paving])
    for r in regions:
        assert r.area - hidden.get(r.id, 0.0) >= -1e-9, (r.id, r.area, hidden.get(r.id))


# --- things that must NOT be flagged --------------------------------------


@case
def test_coplanar_but_apart_is_not_an_overlap():
    a = quad([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], container=0)
    b = quad([(8, 0, 0), (10, 0, 0), (10, 2, 0), (8, 2, 0)], container=1)
    _, pairs, hidden = run([a, b])
    assert pairs == [] and hidden == {}


@case
def test_parallel_but_offset_is_not_an_overlap():
    """A 200 mm gap is two separate surfaces, not one buried one."""
    a = quad([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)], container=0)
    b = quad([(0, 0, 0.2), (0, 4, 0.2), (4, 4, 0.2), (4, 0, 0.2)], container=1)
    _, pairs, hidden = run([a, b])
    assert pairs == [] and hidden == {}


@case
def test_perpendicular_faces_are_not_an_overlap():
    a = quad([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)], container=0)
    b = quad([(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)], container=1)
    _, pairs, hidden = run([a, b])
    assert pairs == [] and hidden == {}


@case
def test_touching_edge_to_edge_is_not_an_overlap():
    """Sharing a boundary line is zero area, not an overlap."""
    a = quad([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], container=0)
    b = quad([(2, 0, 0), (4, 0, 0), (4, 2, 0), (2, 2, 0)], container=1)
    _, pairs, hidden = run([a, b])
    assert pairs == [] and hidden == {}


# --- accumulation ----------------------------------------------------------


@case
def test_two_pads_on_one_slab_both_deducted():
    slab = quad([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], container=0)
    p1 = quad([(1, 1, 0), (1, 3, 0), (3, 3, 0), (3, 1, 0)], container=1)
    p2 = quad([(6, 6, 0), (6, 8, 0), (8, 8, 0), (8, 6, 0)], container=2)
    regions, pairs, hidden = run([slab, p1, p2])
    assert len(pairs) == 2, pairs
    slab_id = next(r.id for r in regions if approx(r.area, 100.0))
    assert approx(hidden[slab_id], 8.0, 1e-6), hidden  # 4 + 4


@case
def test_hidden_never_exceeds_the_surface_itself():
    """Stacked coverings must not deduct more area than the face has."""
    slab = quad([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], container=0)
    c1 = quad([(0, 0, 0), (0, 2, 0), (2, 2, 0), (2, 0, 0)], container=1)
    c2 = quad([(0, 0, 0), (0, 2, 0), (2, 2, 0), (2, 0, 0)], container=2)
    regions, _, hidden = run([slab, c1, c2])
    slab_id = next(r.id for r in regions if r.id == 0)
    assert hidden[slab_id] <= 4.0 + 1e-9, hidden
    for r in regions:
        assert r.area - hidden.get(r.id, 0.0) >= -1e-9


def main() -> int:
    failures = []
    for fn in CASES:
        try:
            fn()
            print(f"  pass  {fn.__name__}")
        except AssertionError as exc:
            failures.append(fn.__name__)
            print(f"  FAIL  {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(fn.__name__)
            print(f"  ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
