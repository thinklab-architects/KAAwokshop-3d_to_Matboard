"""Write the extraction out as model.json + mesh.bin + textures/.

Geometry goes in a flat binary buffer rather than JSON: a mid-sized house is
already a few hundred thousand vertices, which JSON handles slowly and stores at
roughly 5x the size.

``mesh.bin`` is five concatenated blocks - position, normal, uv, regionId, index
- each directly loadable as a typed array. Triangles are sorted by material so
each material becomes one contiguous draw group, and every vertex carries the id
of the region it belongs to, which is what turns a raycast hit into "you clicked
the south wall".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .extract import Extraction
from .regions import CATEGORY_LABELS, Region

SCHEMA = "matboard/1.0"
CONVERTER = "skp2web 0.1"


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _r(value, digits: int = 6):
    """Round for JSON; keeps files small and diffs readable."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_r(v, digits) for v in value]
    return round(float(value), digits)


def _build_mesh(ex: Extraction, regions: list[Region], default_material_id: int):
    """Pack geometry into typed-array blocks, grouped by material."""
    region_of_face: dict[int, int] = {}
    for region in regions:
        for fid in region.face_ids:
            region_of_face[fid] = region.id

    faces = [f for f in ex.faces if f.id in region_of_face and f.tris.size]
    # Sort by material so each material is a single contiguous draw group.
    faces.sort(key=lambda f: (f.material if f.material >= 0 else default_material_id, f.id))

    positions: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    uvs: list[np.ndarray] = []
    region_ids: list[np.ndarray] = []
    indices: list[np.ndarray] = []
    groups: list[dict] = []

    base = 0
    index_cursor = 0
    current_material: int | None = None
    group_start = 0

    for f in faces:
        mat = f.material if f.material >= 0 else default_material_id
        if mat != current_material:
            if current_material is not None:
                groups.append(
                    {
                        "materialId": current_material,
                        "indexStart": group_start,
                        "indexCount": index_cursor - group_start,
                    }
                )
            current_material = mat
            group_start = index_cursor

        positions.append(f.positions.astype(np.float32))
        normals.append(f.normals.astype(np.float32))
        uvs.append(f.uvs.astype(np.float32))
        region_ids.append(
            np.full(len(f.positions), region_of_face[f.id], dtype=np.uint32)
        )
        indices.append((f.tris + base).astype(np.uint32))
        base += len(f.positions)
        index_cursor += f.tris.size

    if current_material is not None:
        groups.append(
            {
                "materialId": current_material,
                "indexStart": group_start,
                "indexCount": index_cursor - group_start,
            }
        )

    def cat(blocks, dtype, width):
        if not blocks:
            return np.zeros((0, width), dtype=dtype)
        return np.concatenate(blocks).astype(dtype, copy=False)

    return (
        cat(positions, np.float32, 3),
        cat(normals, np.float32, 3),
        cat(uvs, np.float32, 2),
        np.concatenate(region_ids).astype(np.uint32) if region_ids else np.zeros(0, np.uint32),
        np.concatenate(indices).astype(np.uint32).ravel() if indices else np.zeros(0, np.uint32),
        groups,
    )


def _assembly_category(assembly) -> str:
    """A screen standing up is a wall; one lying flat is a brise-soleil."""
    extent = np.asarray(assembly.bbox_max) - np.asarray(assembly.bbox_min)
    return "roof" if int(np.argmin(extent)) == 2 else "wall"


def _summarise(
    ex: Extraction,
    regions: list[Region],
    materials: list[dict],
    assemblies: list = (),
) -> dict:
    by_material: dict[int, dict] = {}
    by_category: dict[str, dict] = {}

    # A screen is specified by its elevation, so its battens contribute that one
    # figure rather than the surface area of every stick in it.
    member_of: dict[int, int] = {}
    for a in assemblies:
        for rid in a.region_ids:
            member_of[rid] = a.id

    for region in regions:
        if region.id in member_of:
            continue
        exposed = max(region.area - region.hidden, 0.0)
        mid = region.material if region.material >= 0 else len(materials) - 1
        entry = by_material.setdefault(
            mid,
            {
                "materialId": mid,
                "name": materials[mid]["name"],
                "areaM2": 0.0,
                "exposedAreaM2": 0.0,
                "regionCount": 0,
                "categories": {},
            },
        )
        entry["areaM2"] += region.area
        entry["exposedAreaM2"] += exposed
        entry["regionCount"] += 1
        entry["categories"][region.category] = (
            entry["categories"].get(region.category, 0.0) + region.area
        )

        cat = by_category.setdefault(
            region.category,
            {
                "category": region.category,
                "label": CATEGORY_LABELS.get(region.category, region.category),
                "areaM2": 0.0,
                "exposedAreaM2": 0.0,
                "regionCount": 0,
            },
        )
        cat["areaM2"] += region.area
        cat["exposedAreaM2"] += exposed
        cat["regionCount"] += 1

    for a in assemblies:
        mid = a.material if a.material >= 0 else len(materials) - 1
        entry = by_material.setdefault(
            mid,
            {
                "materialId": mid,
                "name": materials[mid]["name"],
                "areaM2": 0.0,
                "exposedAreaM2": 0.0,
                "regionCount": 0,
                "categories": {},
            },
        )
        entry["areaM2"] += a.area
        entry["exposedAreaM2"] += a.area
        entry["regionCount"] += 1
        key = _assembly_category(a)
        label = CATEGORY_LABELS.get(key, key)
        entry["categories"][key] = entry["categories"].get(key, 0.0) + a.area
        cat = by_category.setdefault(
            key,
            {"category": key, "label": label, "areaM2": 0.0,
             "exposedAreaM2": 0.0, "regionCount": 0},
        )
        cat["areaM2"] += a.area
        cat["exposedAreaM2"] += a.area
        cat["regionCount"] += 1

    for entry in by_material.values():
        entry["areaM2"] = _r(entry["areaM2"], 4)
        entry["exposedAreaM2"] = _r(entry["exposedAreaM2"], 4)
        entry["categories"] = {k: _r(v, 4) for k, v in entry["categories"].items()}
    for entry in by_category.values():
        entry["areaM2"] = _r(entry["areaM2"], 4)
        entry["exposedAreaM2"] = _r(entry["exposedAreaM2"], 4)

    return {
        "byMaterial": sorted(by_material.values(), key=lambda e: -e["areaM2"]),
        "byCategory": sorted(by_category.values(), key=lambda e: -e["areaM2"]),
    }


def write(
    ex: Extraction,
    regions: list[Region],
    out_dir: Path,
    source: Path,
    overlaps: list | None = None,
    assemblies: list | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    overlaps = overlaps or []
    assemblies = assemblies or []

    materials = [
        {
            "id": m.id,
            "name": m.name,
            "colorHex": _hex(m.color),
            "opacity": _r(m.opacity, 3),
            "texture": f"textures/{m.texture_file}" if m.texture_file else None,
            "textureSizeM": _r(m.texture_size_m, 4) if m.texture_size_m else None,
            "attrs": m.attrs or None,
        }
        for m in ex.materials
    ]
    # Faces with no material anywhere in their inheritance chain land here.
    default_material_id = len(materials)
    materials.append(
        {
            "id": default_material_id,
            "name": "未指定材質",
            "colorHex": "#C8C8C8",
            "opacity": 1.0,
            "texture": None,
            "textureSizeM": None,
            "attrs": None,
        }
    )

    pos, nrm, uv, region_ids, index, groups = _build_mesh(ex, regions, default_material_id)

    blob = bytearray()
    layout: dict[str, dict] = {}
    for name, arr, comps, ctype in (
        ("position", pos, 3, "f32"),
        ("normal", nrm, 3, "f32"),
        ("uv", uv, 2, "f32"),
        ("regionId", region_ids, 1, "u32"),
    ):
        layout[name] = {
            "byteOffset": len(blob),
            "byteLength": arr.nbytes,
            "componentType": ctype,
            "components": comps,
        }
        blob.extend(arr.tobytes())
    index_info = {
        "byteOffset": len(blob),
        "byteLength": index.nbytes,
        "componentType": "u32",
        "count": int(index.size),
    }
    blob.extend(index.tobytes())
    (out_dir / "mesh.bin").write_bytes(bytes(blob))

    for g in groups:
        mat = materials[g["materialId"]]
        g["transparent"] = bool(mat["opacity"] < 0.99)

    if len(pos):
        bbox_min, bbox_max = pos.min(axis=0), pos.max(axis=0)
    else:
        bbox_min = bbox_max = np.zeros(3, dtype=np.float32)

    by_region: dict[int, list[dict]] = {}
    for o in overlaps:
        entry = {"m2": _r(o.area, 4), "kind": o.kind}
        by_region.setdefault(o.a, []).append({"regionId": o.b, **entry})
        by_region.setdefault(o.b, []).append({"regionId": o.a, **entry})
    for entries in by_region.values():
        entries.sort(key=lambda e: -e["m2"])

    in_assembly = {rid for a in assemblies for rid in a.region_ids}
    loose = [r for r in regions if r.id not in in_assembly]
    assembly_area = sum(a.area for a in assemblies)
    total_area = sum(r.area for r in loose) + assembly_area
    total_hidden = sum(min(r.hidden, r.area) for r in loose)
    assembly_of = {rid: a.id for a in assemblies for rid in a.region_ids}

    doc = {
        "schema": SCHEMA,
        "source": {
            "file": source.name,
            "modelName": ex.model_name,
            "skpVersion": ex.skp_version,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "converter": CONVERTER,
        },
        "units": {"length": "m", "area": "m2"},
        "upAxis": "Z",
        "bbox": {
            "min": _r(bbox_min, 4),
            "max": _r(bbox_max, 4),
            "size": _r(bbox_max - bbox_min, 4),
        },
        "stats": {
            "faces": len(ex.faces),
            "regions": len(regions),
            "triangles": int(index.size // 3),
            "vertices": int(len(pos)),
            "elements": len(ex.elements),
            "skippedHidden": ex.skipped_hidden,
        },
        "totals": {
            "areaM2": _r(total_area, 4),
            "hiddenM2": _r(total_hidden, 4),
            "exposedAreaM2": _r(total_area - total_hidden, 4),
        },
        "overlaps": {
            "pairCount": len(overlaps),
            "duplicatePairs": sum(1 for o in overlaps if o.kind == "duplicate"),
            "interfacePairs": sum(1 for o in overlaps if o.kind == "interface"),
            "platePairs": sum(1 for o in overlaps if o.kind == "plate"),
            "hiddenM2": _r(total_hidden, 4),
        },
        "assemblies": [
            {
                "id": a.id,
                "name": a.name,
                "kind": a.kind,
                "materialId": a.material if a.material >= 0 else default_material_id,
                "members": a.members,
                "category": _assembly_category(a),
                "categoryLabel": CATEGORY_LABELS.get(_assembly_category(a), ""),
                "regionIds": a.region_ids,
                "areaM2": _r(a.area, 4),
                # What a face-by-face sum would have produced, so the difference
                # is auditable rather than a number that silently changed.
                "rawAreaM2": _r(
                    sum(r.area for r in regions if r.id in set(a.region_ids)), 4
                ),
                "widthM": _r(a.width, 4),
                "heightM": _r(a.height, 4),
                "bbox": {"min": _r(a.bbox_min, 4), "max": _r(a.bbox_max, 4)},
            }
            for a in assemblies
        ],
        "materials": materials,
        "elements": [
            {
                "id": e.id,
                "name": e.name,
                "kind": e.kind,
                "path": e.path,
                "parent": e.parent,
                "tag": e.tag,
                "attrs": e.attrs or None,
            }
            for e in ex.elements
        ],
        "regions": [
            {
                "id": r.id,
                "materialId": r.material if r.material >= 0 else default_material_id,
                "category": r.category,
                "categoryLabel": CATEGORY_LABELS.get(r.category, r.category),
                "elementId": r.element,
                "tag": r.tag,
                "areaM2": _r(r.area, 4),
                "hiddenM2": _r(r.hidden, 4),
                "exposedAreaM2": _r(max(r.area - r.hidden, 0.0), 4),
                "overlapWith": by_region.get(r.id, []),
                "assemblyId": assembly_of.get(r.id),
                "shape": r.shape,
                "edgesM": _r(r.edges, 4),
                "lengthM": _r(r.length, 4),
                "widthM": _r(r.width, 4),
                "dimLabel": r.length_label,
                "solidRatio": _r(r.solid_ratio, 3),
                "normal": _r(r.normal, 4),
                "centroid": _r(r.centroid, 4),
                "bbox": {"min": _r(r.bbox_min, 4), "max": _r(r.bbox_max, 4)},
                "faceCount": len(r.face_ids),
                "triangleCount": r.tri_count,
            }
            for r in regions
        ],
        "summary": _summarise(ex, regions, materials, assemblies),
        "mesh": {
            "file": "mesh.bin",
            "vertexCount": int(len(pos)),
            "attributes": layout,
            "index": index_info,
            "groups": groups,
        },
    }

    (out_dir / "model.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return doc
