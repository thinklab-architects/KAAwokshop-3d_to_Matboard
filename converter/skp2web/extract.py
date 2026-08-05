"""Walk a .skp model into a flat list of world-space triangulated faces.

Three things here are easy to get wrong and are the reason this file exists:

1. **Transforms.** Geometry inside a group or component is stored in that
   container's local space. World position needs the accumulated 4x4, and
   SketchUp's matrices are column-major and may carry a scale in ``values[15]``,
   so the homogeneous divide is not optional.

2. **Material inheritance.** A face very often has *no* material of its own -
   the material sits on the enclosing group. (Every face in the sample model is
   like this.) The effective material is the first one found walking
   face -> enclosing group/instance -> ... -> model default.

3. **Hidden geometry.** Tags that are switched off, and elements flagged hidden,
   are excluded by default so the takeoff matches what the model actually shows.
"""

from __future__ import annotations

from ctypes import byref, c_bool, c_double, c_size_t
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import sdk
from .sdk import (
    Ref,
    SUPoint3D,
    SUTransformation,
    SUVector3D,
    check,
    get_list,
    get_string,
    optional,
    read_attributes,
)

INCH_TO_M = sdk.INCH_TO_M

# SketchUp writes bookkeeping dictionaries onto entities; they are noise here.
_SKIP_DICTS = ("SU_DefinitionSet", "SU_InstanceSet", "GSU_ContributorsInfo", "dynamic_attributes")


@dataclass
class Element:
    """A group or component instance in the model tree."""

    id: int
    name: str
    kind: str  # "group" | "instance" | "model"
    path: str
    parent: int | None
    tag: str | None
    attrs: dict = field(default_factory=dict)


@dataclass
class RawFace:
    id: int
    element: int
    container: int  # instance-path id; faces only merge within one container
    material: int  # index into Extraction.materials, -1 for the default material
    tag: str | None
    positions: np.ndarray  # (V, 3) world metres
    normals: np.ndarray  # (V, 3) unit
    uvs: np.ndarray  # (V, 2)
    tris: np.ndarray  # (T, 3) indices into positions
    outline: np.ndarray  # (K, 3) outer loop, world metres
    normal: np.ndarray  # (3,) unit, world
    area: float  # m^2, true area with holes removed


@dataclass
class MaterialInfo:
    id: int
    name: str
    color: tuple[int, int, int]
    opacity: float
    texture_file: str | None  # filename written into the texture dir, if any
    texture_size_m: tuple[float, float] | None  # real-world size of one tile
    attrs: dict = field(default_factory=dict)


@dataclass
class Extraction:
    faces: list[RawFace]
    elements: list[Element]
    materials: list[MaterialInfo]
    model_name: str | None
    skp_version: str
    skipped_hidden: int


# ---------------------------------------------------------------------------
# maths
# ---------------------------------------------------------------------------


def _matrix(t: SUTransformation) -> np.ndarray:
    """SUTransformation (column-major, values[col*4+row]) -> row-major 4x4."""
    return np.array(t.values, dtype=np.float64).reshape(4, 4).T


def _transform_points(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply a 4x4 to (N,3) points, with the homogeneous divide."""
    if pts.size == 0:
        return pts
    homo = np.empty((pts.shape[0], 4), dtype=np.float64)
    homo[:, :3] = pts
    homo[:, 3] = 1.0
    out = homo @ m.T
    w = out[:, 3:4]
    # SketchUp stores a uniform scale in values[15]; w is never 0 in practice,
    # but guard so a degenerate matrix cannot produce inf.
    w = np.where(np.abs(w) < 1e-12, 1.0, w)
    return out[:, :3] / w


def _normal_matrix(m: np.ndarray) -> np.ndarray:
    """Inverse-transpose of the linear part, for transforming normals."""
    linear = m[:3, :3]
    try:
        return np.linalg.inv(linear).T
    except np.linalg.LinAlgError:  # pragma: no cover - degenerate transform
        return linear


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.divide(v, np.where(n < 1e-12, 1.0, n))


# ---------------------------------------------------------------------------
# per-entity readers
# ---------------------------------------------------------------------------


def _layer_name(drawing_element: Ref) -> tuple[str | None, bool]:
    """(tag name, visible)."""
    layer = Ref()
    if not optional(sdk.SUDrawingElementGetLayer(drawing_element, byref(layer)), "GetLayer"):
        return None, True
    name = get_string(sdk.SULayerGetName, layer)
    visible = c_bool(True)
    sdk.SULayerGetVisibility(layer, byref(visible))
    return name, bool(visible.value)


def _is_hidden(drawing_element: Ref) -> bool:
    hidden = c_bool(False)
    if sdk.SUDrawingElementGetHidden(drawing_element, byref(hidden)) != sdk.SU_ERROR_NONE:
        return False
    return bool(hidden.value)


def _element_material(drawing_element: Ref) -> Ref | None:
    mat = Ref()
    if optional(sdk.SUDrawingElementGetMaterial(drawing_element, byref(mat)), "GetMaterial"):
        return mat if mat.ptr else None
    return None


def _loop_points(loop: Ref) -> np.ndarray:
    verts = get_list(sdk.SULoopGetNumVertices, sdk.SULoopGetVertices, loop)
    if not verts:
        return np.zeros((0, 3), dtype=np.float64)
    out = np.empty((len(verts), 3), dtype=np.float64)
    p = SUPoint3D()
    for i, v in enumerate(verts):
        check(sdk.SUVertexGetPosition(v, byref(p)), "SUVertexGetPosition")
        out[i] = (p.x, p.y, p.z)
    return out


def _triangulate(face: Ref) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(positions, normals, uvs, tris) in the face's own local space."""
    mesh = Ref()
    check(sdk.SUMeshHelperCreate(byref(mesh), face), "SUMeshHelperCreate")
    try:
        nv, nt = c_size_t(0), c_size_t(0)
        check(sdk.SUMeshHelperGetNumVertices(mesh, byref(nv)), "GetNumVertices")
        check(sdk.SUMeshHelperGetNumTriangles(mesh, byref(nt)), "GetNumTriangles")
        if nv.value == 0 or nt.value == 0:
            z = np.zeros((0, 3), dtype=np.float64)
            return z, z, np.zeros((0, 2), dtype=np.float64), np.zeros((0, 3), dtype=np.int64)

        got = c_size_t(0)
        vbuf = (SUPoint3D * nv.value)()
        check(sdk.SUMeshHelperGetVertices(mesh, nv.value, vbuf, byref(got)), "GetVertices")
        positions = np.frombuffer(vbuf, dtype=np.float64).reshape(-1, 3).copy()

        nbuf = (SUVector3D * nv.value)()
        if optional(sdk.SUMeshHelperGetNormals(mesh, nv.value, nbuf, byref(got)), "GetNormals"):
            normals = np.frombuffer(nbuf, dtype=np.float64).reshape(-1, 3).copy()
        else:
            normals = np.zeros_like(positions)

        stq = (SUPoint3D * nv.value)()
        if optional(
            sdk.SUMeshHelperGetFrontSTQCoords(mesh, nv.value, stq, byref(got)), "GetFrontSTQ"
        ):
            raw = np.frombuffer(stq, dtype=np.float64).reshape(-1, 3).copy()
            q = raw[:, 2:3]
            q = np.where(np.abs(q) < 1e-12, 1.0, q)
            uvs = raw[:, :2] / q
        else:
            uvs = np.zeros((nv.value, 2), dtype=np.float64)

        ibuf = (c_size_t * (nt.value * 3))()
        check(
            sdk.SUMeshHelperGetVertexIndices(mesh, nt.value * 3, ibuf, byref(got)),
            "GetVertexIndices",
        )
        tris = np.ctypeslib.as_array(ibuf).astype(np.int64).reshape(-1, 3).copy()
        return positions, normals, uvs, tris
    finally:
        sdk.SUMeshHelperRelease(byref(mesh))


def _triangle_area(positions: np.ndarray, tris: np.ndarray) -> float:
    if tris.size == 0:
        return 0.0
    a = positions[tris[:, 0]]
    b = positions[tris[:, 1]]
    c = positions[tris[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() * 0.5)


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------


def _safe_filename(name: str, idx: int) -> str:
    keep = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name)
    return f"{idx:03d}_{keep[:60] or 'material'}.png"


def _read_materials(
    model: sdk.Model, texture_dir: Path | None
) -> tuple[list[MaterialInfo], dict[int, int]]:
    """Read the material palette. Textures are written out here because the
    SUTextureRef is only valid while the model is open."""
    infos: list[MaterialInfo] = []
    by_ptr: dict[int, int] = {}
    for ref in model.materials():
        idx = len(infos)
        by_ptr[ref.ptr] = idx

        name = get_string(sdk.SUMaterialGetName, ref) or f"Material {idx}"
        color = (204, 204, 204)
        col = sdk.SUColor()
        if optional(sdk.SUMaterialGetColor(ref, byref(col)), "SUMaterialGetColor"):
            color = (col.red, col.green, col.blue)

        opacity = 1.0
        use_op = c_bool(False)
        sdk.SUMaterialGetUseOpacity(ref, byref(use_op))
        o = c_double(1.0)
        if optional(sdk.SUMaterialGetOpacity(ref, byref(o)), "SUMaterialGetOpacity"):
            opacity = float(o.value)

        tex_file: str | None = None
        tex_size: tuple[float, float] | None = None
        t = Ref()
        if optional(sdk.SUMaterialGetTexture(ref, byref(t)), "SUMaterialGetTexture") and t.ptr:
            w, h = c_size_t(0), c_size_t(0)
            s_scale, t_scale = c_double(0), c_double(0)
            if optional(
                sdk.SUTextureGetDimensions(t, byref(w), byref(h), byref(s_scale), byref(t_scale)),
                "SUTextureGetDimensions",
            ):
                # s_scale/t_scale are texture repeats per inch of model space, so
                # one tile spans 1/scale inches. (Verified against a model whose
                # tiles are documented as 600/800/900/1200/2000 mm - all exact.)
                if s_scale.value > 1e-9 and t_scale.value > 1e-9:
                    tex_size = (
                        INCH_TO_M / s_scale.value,
                        INCH_TO_M / t_scale.value,
                    )
            if texture_dir is not None:
                fname = _safe_filename(name, idx)
                dest = texture_dir / fname
                if sdk.SUTextureWriteToFile(t, str(dest).encode("utf-8")) == sdk.SU_ERROR_NONE:
                    tex_file = fname
                elif dest.exists():  # partial write
                    dest.unlink()

        attrs = read_attributes(sdk.SUMaterialToEntity(ref), skip=_SKIP_DICTS)
        infos.append(
            MaterialInfo(
                id=idx,
                name=name,
                color=color,
                opacity=opacity,
                texture_file=tex_file,
                texture_size_m=tex_size,
                attrs=attrs,
            )
        )
    return infos, by_ptr


# ---------------------------------------------------------------------------
# traversal
# ---------------------------------------------------------------------------


class _Walker:
    def __init__(self, mat_by_ptr: dict[int, int], include_hidden: bool):
        self.mat_by_ptr = mat_by_ptr
        self.include_hidden = include_hidden
        self.faces: list[RawFace] = []
        self.elements: list[Element] = []
        self.skipped_hidden = 0
        self._container_seq = 0

    def _add_element(self, name, kind, path, parent, tag, attrs) -> int:
        self.elements.append(
            Element(
                id=len(self.elements),
                name=name,
                kind=kind,
                path=path,
                parent=parent,
                tag=tag,
                attrs=attrs,
            )
        )
        return self.elements[-1].id

    def _material_index(self, ref: Ref | None) -> int:
        if ref is None or not ref.ptr:
            return -1
        return self.mat_by_ptr.get(ref.ptr, -1)

    def walk(self, entities: Ref, world: np.ndarray, inherited: Ref | None,
             element_id: int, container: int, tag: str | None) -> None:
        self._walk_faces(entities, world, inherited, element_id, container, tag)

        for group in get_list(sdk.SUEntitiesGetNumGroups, sdk.SUEntitiesGetGroups, entities):
            de = sdk.SUGroupToDrawingElement(group)
            child_tag, visible = _layer_name(de)
            if not self.include_hidden and (_is_hidden(de) or not visible):
                self.skipped_hidden += 1
                continue
            t = SUTransformation()
            check(sdk.SUGroupGetTransform(group, byref(t)), "SUGroupGetTransform")
            name = get_string(sdk.SUGroupGetName, group) or "(group)"
            attrs = read_attributes(sdk.SUGroupToEntity(group), skip=_SKIP_DICTS)
            child = self._add_element(
                name, "group", f"{self.elements[element_id].path}/{name}",
                element_id, child_tag or tag, attrs,
            )
            child_ents = Ref()
            check(sdk.SUGroupGetEntities(group, byref(child_ents)), "SUGroupGetEntities")
            self._container_seq += 1
            self.walk(
                child_ents,
                world @ _matrix(t),
                _element_material(de) or inherited,
                child,
                self._container_seq,
                child_tag or tag,
            )

        for inst in get_list(sdk.SUEntitiesGetNumInstances, sdk.SUEntitiesGetInstances, entities):
            de = sdk.SUComponentInstanceToDrawingElement(inst)
            child_tag, visible = _layer_name(de)
            if not self.include_hidden and (_is_hidden(de) or not visible):
                self.skipped_hidden += 1
                continue
            definition = Ref()
            check(sdk.SUComponentInstanceGetDefinition(inst, byref(definition)), "GetDefinition")
            t = SUTransformation()
            check(sdk.SUComponentInstanceGetTransform(inst, byref(t)), "GetTransform")
            name = (
                get_string(sdk.SUComponentInstanceGetName, inst)
                or get_string(sdk.SUComponentDefinitionGetName, definition)
                or "(component)"
            )
            attrs = read_attributes(sdk.SUComponentInstanceToEntity(inst), skip=_SKIP_DICTS)
            child = self._add_element(
                name, "instance", f"{self.elements[element_id].path}/{name}",
                element_id, child_tag or tag, attrs,
            )
            child_ents = Ref()
            check(sdk.SUComponentDefinitionGetEntities(definition, byref(child_ents)), "DefEntities")
            self._container_seq += 1
            self.walk(
                child_ents,
                world @ _matrix(t),
                _element_material(de) or inherited,
                child,
                self._container_seq,
                child_tag or tag,
            )

    def _walk_faces(self, entities: Ref, world: np.ndarray, inherited: Ref | None,
                    element_id: int, container: int, tag: str | None) -> None:
        faces = get_list(sdk.SUEntitiesGetNumFaces, sdk.SUEntitiesGetFaces, entities)
        if not faces:
            return
        nrm_m = _normal_matrix(world)
        flipped = np.linalg.det(world[:3, :3]) < 0

        for face in faces:
            de = sdk.SUFaceToDrawingElement(face)
            face_tag, visible = _layer_name(de)
            if not self.include_hidden and (_is_hidden(de) or not visible):
                self.skipped_hidden += 1
                continue

            positions, normals, uvs, tris = _triangulate(face)
            if tris.size == 0:
                continue

            positions = _transform_points(world, positions) * INCH_TO_M
            normals = _normalize(normals @ nrm_m.T)
            if flipped:
                # A mirroring transform reverses winding; keep it consistent so
                # front faces stay front.
                tris = tris[:, ::-1].copy()

            outer = Ref()
            outline = np.zeros((0, 3), dtype=np.float64)
            if optional(sdk.SUFaceGetOuterLoop(face, byref(outer)), "SUFaceGetOuterLoop"):
                outline = _transform_points(world, _loop_points(outer)) * INCH_TO_M

            n = SUVector3D()
            if optional(sdk.SUFaceGetNormal(face, byref(n)), "SUFaceGetNormal"):
                world_n = _normalize(np.array([[n.x, n.y, n.z]]) @ nrm_m.T)[0]
            else:
                world_n = _normalize(normals.mean(axis=0)[None, :])[0]

            # Face material first, then whatever it inherits from its container.
            own = _element_material(de)
            material = self._material_index(own if own is not None else inherited)

            self.faces.append(
                RawFace(
                    id=len(self.faces),
                    element=element_id,
                    container=container,
                    material=material,
                    tag=(face_tag if face_tag and face_tag != "Layer0" else tag),
                    positions=positions,
                    normals=normals,
                    uvs=uvs,
                    tris=tris,
                    outline=outline,
                    normal=world_n,
                    area=_triangle_area(positions, tris),
                )
            )


def extract(
    path: str, texture_dir: Path | None = None, include_hidden: bool = False
) -> Extraction:
    if texture_dir is not None:
        texture_dir.mkdir(parents=True, exist_ok=True)
    with sdk.Model(path) as model:
        materials, by_ptr = _read_materials(model, texture_dir)
        walker = _Walker(by_ptr, include_hidden)
        root = walker._add_element(model.name or "Model", "model", "", None, None, {})
        walker.walk(model.entities, np.eye(4), None, root, 0, None)
        return Extraction(
            faces=walker.faces,
            elements=walker.elements,
            materials=materials,
            model_name=model.name,
            skp_version=model.version,
            skipped_hidden=walker.skipped_hidden,
        )
