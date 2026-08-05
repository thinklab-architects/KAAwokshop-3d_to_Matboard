"""Tests for louvre/screen detection.

Run:  python -m tests.test_assemblies        (from converter/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skp2web.assemblies import find_assemblies  # noqa: E402
from skp2web.extract import Element, Extraction, MaterialInfo  # noqa: E402
from skp2web.regions import build_regions  # noqa: E402
from tests.test_regions import approx, quad  # noqa: E402


def box(x, y, z, dx, dy, dz, material=0, element=1, container=1):
    """Six faces of an axis-aligned box, wound outwards."""
    x1, y1, z1 = x + dx, y + dy, z + dz
    corners = {
        "bottom": [(x, y, z), (x, y1, z), (x1, y1, z), (x1, y, z)],
        "top": [(x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1)],
        "front": [(x, y, z), (x1, y, z), (x1, y, z1), (x, y, z1)],
        "back": [(x, y1, z), (x, y1, z1), (x1, y1, z1), (x1, y1, z)],
        "left": [(x, y, z), (x, y, z1), (x, y1, z1), (x, y1, z)],
        "right": [(x1, y, z), (x1, y1, z), (x1, y1, z1), (x1, y, z1)],
    }
    return [
        quad(pts, material=material, container=container, element=element)
        for pts in corners.values()
    ]


def make(boxes: list[list], names: list[str]) -> Extraction:
    """One element per box, all under a single model root."""
    faces = []
    for group in boxes:
        faces.extend(group)
    for i, f in enumerate(faces):
        f.id = i
    elements = [Element(0, "Model", "model", "", None, None, {})]
    for i, name in enumerate(names, start=1):
        elements.append(Element(i, name, "group", f"/{name}", 0, None, {}))
    return Extraction(
        faces=faces,
        elements=elements,
        materials=[
            MaterialInfo(0, "Cedar", (150, 110, 70), 1.0, None, None, {}),
            MaterialInfo(1, "Other", (100, 100, 100), 1.0, None, None, {}),
        ],
        model_name="test",
        skp_version="22.0.0",
        skipped_hidden=0,
    )


def louvre(count=20, pitch=0.17, w=0.06, d=0.10, h=2.02, material=0):
    """A run of upright battens, the shape a timber screen actually is."""
    boxes, names = [], []
    for i in range(count):
        boxes.append(box(i * pitch, 0.0, 0.0, w, d, h, material=material,
                         element=i + 1, container=i + 1))
        names.append(f"Screen_Slat_{i + 1:02d}")
    return boxes, names


def detect(boxes, names):
    ex = make(boxes, names)
    return ex, build_regions(ex), find_assemblies(ex, build_regions(ex))


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_screen_is_measured_in_elevation_not_stick_by_stick():
    boxes, names = louvre()
    ex, regions, found = detect(boxes, names)
    assert len(found) == 1, found
    a = found[0]
    assert a.members == 20
    # 20 battens at 0.17 centres, last one 0.06 wide -> 19*0.17 + 0.06
    assert approx(a.width, 19 * 0.17 + 0.06, 1e-6), a.width
    assert approx(a.height, 2.02, 1e-6), a.height
    assert approx(a.area, a.width * a.height, 1e-9)
    raw = sum(r.area for r in regions if r.id in set(a.region_ids))
    assert raw > a.area * 1.5, (raw, a.area)  # the whole point of the exercise
    assert a.name.startswith("Screen_Slat")


@case
def test_a_colonnade_is_not_a_screen():
    """Columns are parallel sticks at regular centres too - but spaced out."""
    boxes, names = [], []
    for i in range(6):
        boxes.append(box(i * 4.0, 0.0, 0.0, 0.4, 0.4, 3.0, element=i + 1, container=i + 1))
        names.append(f"Column_{i + 1}")
    _, _, found = detect(boxes, names)
    assert found == [], [(a.name, a.members) for a in found]


@case
def test_too_few_members_is_not_a_screen():
    boxes, names = louvre(count=4)
    _, _, found = detect(boxes, names)
    assert found == []


@case
def test_irregular_spacing_is_not_a_screen():
    boxes, names = [], []
    for i, x in enumerate([0.0, 0.17, 0.9, 1.05, 2.4, 2.5, 3.9]):
        boxes.append(box(x, 0.0, 0.0, 0.06, 0.10, 2.02, element=i + 1, container=i + 1))
        names.append(f"Batten_{i}")
    _, _, found = detect(boxes, names)
    assert found == []


@case
def test_members_of_different_lengths_are_not_a_screen():
    boxes, names = [], []
    for i in range(8):
        boxes.append(box(i * 0.17, 0.0, 0.0, 0.06, 0.10, 1.0 + i * 0.3,
                         element=i + 1, container=i + 1))
        names.append(f"Batten_{i}")
    _, _, found = detect(boxes, names)
    assert found == []


@case
def test_mixed_materials_do_not_merge():
    boxes, names = louvre(count=10)
    for f in boxes[0]:
        f.material = 1
    _, _, found = detect(boxes, names)
    assert all(a.members != 10 for a in found), found


@case
def test_horizontal_louvre_is_detected_too():
    """Slats running across, stacked up the wall."""
    boxes, names = [], []
    for i in range(12):
        boxes.append(box(0.0, 0.0, i * 0.15, 2.4, 0.08, 0.05,
                         element=i + 1, container=i + 1))
        names.append(f"Blade_{i:02d}")
    _, _, found = detect(boxes, names)
    assert len(found) == 1, found
    a = found[0]
    assert approx(a.width, 2.4, 1e-6), a.width
    assert approx(a.height, 11 * 0.15 + 0.05, 1e-6), a.height


@case
def test_a_solid_panel_is_not_a_screen():
    """One board is not a run of battens."""
    boxes = [box(0, 0, 0, 3.0, 0.05, 2.0)]
    _, _, found = detect(boxes, ["Panel"])
    assert found == []


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
