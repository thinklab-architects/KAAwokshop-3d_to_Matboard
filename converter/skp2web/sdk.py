"""ctypes bindings for the SketchUp C API (SketchUpAPI.dll).

Only the subset needed to read geometry, materials, tags and attributes out of a
.skp file is declared here. Everything in the C API follows the same shape:

  * every handle is an 8-byte struct wrapping a void* (``Ref`` below), passed and
    returned by value;
  * every call returns an ``SUResult`` int, with real output written to
    out-parameters;
  * strings come back as ``SUStringRef`` and must be drained then released.

The DLL ships with the SketchUp application, so no compiler and no separate SDK
download is needed on a machine that has SketchUp installed. Set
``MATBOARD_SU_DLL`` to point at a different copy (e.g. the redistributable from
the official SketchUp SDK, which is what a deployed server should use).
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import POINTER, byref, c_bool, c_char_p, c_double, c_int, c_int32, c_size_t, c_ubyte
from pathlib import Path

# ---------------------------------------------------------------------------
# Result codes
# ---------------------------------------------------------------------------

SU_ERROR_NONE = 0
SU_ERROR_NULL_POINTER_INPUT = 1
SU_ERROR_INVALID_INPUT = 2
SU_ERROR_NULL_POINTER_OUTPUT = 3
SU_ERROR_INVALID_OUTPUT = 4
SU_ERROR_OVERWRITE_VALID = 5
SU_ERROR_GENERIC = 6
SU_ERROR_SERIALIZATION = 7
SU_ERROR_OUT_OF_RANGE = 8
SU_ERROR_NO_DATA = 9
SU_ERROR_INSUFFICIENT_SIZE = 10
SU_ERROR_UNKNOWN_EXCEPTION = 11
SU_ERROR_MODEL_INVALID = 12
SU_ERROR_MODEL_VERSION = 13

_RESULT_NAMES = {
    v: k for k, v in list(globals().items()) if k.startswith("SU_ERROR_")
}

# Materials whose type says they carry a texture.
SU_MATERIAL_TYPE_COLORIZED_TEXTURED = 2
SU_MATERIAL_TYPE_TEXTURED = 1

# SUTypedValueType
TV_EMPTY, TV_BYTE, TV_SHORT, TV_INT32, TV_FLOAT, TV_DOUBLE = 0, 1, 2, 3, 4, 5
TV_BOOL, TV_COLOR, TV_TIME, TV_STRING, TV_VECTOR3D, TV_ARRAY = 6, 7, 8, 9, 10, 11

INCH_TO_M = 0.0254


class SketchUpError(RuntimeError):
    def __init__(self, fn: str, code: int):
        self.fn = fn
        self.code = code
        super().__init__(f"{fn} failed: {_RESULT_NAMES.get(code, code)} ({code})")


class UnsupportedSkpVersion(RuntimeError):
    """The .skp was written by a SketchUp newer than the loaded DLL understands."""


# ---------------------------------------------------------------------------
# Structs
# ---------------------------------------------------------------------------


class Ref(ctypes.Structure):
    """Every SU*Ref handle: a struct wrapping one pointer."""

    _fields_ = [("ptr", ctypes.c_void_p)]

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return bool(self.ptr)


class SUPoint3D(ctypes.Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]


class SUVector3D(ctypes.Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]


class SUTransformation(ctypes.Structure):
    """4x4, column-major: values[col * 4 + row]."""

    _fields_ = [("values", c_double * 16)]


class SUColor(ctypes.Structure):
    _fields_ = [
        ("red", c_ubyte),
        ("green", c_ubyte),
        ("blue", c_ubyte),
        ("alpha", c_ubyte),
    ]


class SUPlane3D(ctypes.Structure):
    _fields_ = [("a", c_double), ("b", c_double), ("c", c_double), ("d", c_double)]


# ---------------------------------------------------------------------------
# DLL discovery + loading
# ---------------------------------------------------------------------------


def _candidate_dlls() -> list[Path]:
    explicit = os.environ.get("MATBOARD_SU_DLL")
    if explicit:
        return [Path(explicit)]

    found: list[Path] = []
    for base in (r"C:\Program Files\SketchUp", r"C:\Program Files (x86)\SketchUp"):
        root = Path(base)
        if not root.is_dir():
            continue
        # Newest SketchUp first, so a 2024 install wins over a 2022 one.
        for child in sorted(root.iterdir(), reverse=True):
            dll = child / "SketchUpAPI.dll"
            if dll.is_file():
                found.append(dll)
    # A redistributable SDK unpacked next to the project.
    here = Path(__file__).resolve().parents[2]
    for extra in (here / "vendor" / "sketchup-sdk" / "binaries" / "sketchup" / "x64",
                  here / "vendor" / "sketchup-sdk"):
        dll = extra / "SketchUpAPI.dll"
        if dll.is_file():
            found.insert(0, dll)
    return found


def _load() -> tuple[ctypes.CDLL, Path]:
    candidates = _candidate_dlls()
    if not candidates:
        raise RuntimeError(
            "SketchUpAPI.dll not found. Install SketchUp, or download the SketchUp "
            "SDK and set MATBOARD_SU_DLL to the SketchUpAPI.dll inside it."
        )
    errors = []
    for dll in candidates:
        try:
            if sys.platform == "win32":
                os.add_dll_directory(str(dll.parent))
            return ctypes.CDLL(str(dll)), dll
        except OSError as exc:  # pragma: no cover - environment specific
            errors.append(f"{dll}: {exc}")
    raise RuntimeError("Could not load SketchUpAPI.dll:\n  " + "\n  ".join(errors))


lib, DLL_PATH = _load()


# ---------------------------------------------------------------------------
# Signature declarations
# ---------------------------------------------------------------------------

_P = POINTER


def _decl(name: str, argtypes, restype=c_int, optional: bool = False):
    fn = getattr(lib, name, None)
    if fn is None:
        if optional:
            return None
        raise RuntimeError(f"SketchUpAPI.dll does not export {name}")
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


# lifecycle -----------------------------------------------------------------
SUInitialize = _decl("SUInitialize", [], None)
SUTerminate = _decl("SUTerminate", [], None)
SUModelCreateFromFile = _decl("SUModelCreateFromFile", [_P(Ref), c_char_p])
SUModelRelease = _decl("SUModelRelease", [_P(Ref)])
SUModelGetVersion = _decl("SUModelGetVersion", [Ref, _P(c_int), _P(c_int), _P(c_int)])
SUModelGetName = _decl("SUModelGetName", [Ref, _P(Ref)])
SUModelGetEntities = _decl("SUModelGetEntities", [Ref, _P(Ref)])
SUModelGetNumMaterials = _decl("SUModelGetNumMaterials", [Ref, _P(c_size_t)])
SUModelGetMaterials = _decl("SUModelGetMaterials", [Ref, c_size_t, _P(Ref), _P(c_size_t)])

# strings -------------------------------------------------------------------
SUStringCreate = _decl("SUStringCreate", [_P(Ref)])
SUStringRelease = _decl("SUStringRelease", [_P(Ref)])
SUStringGetUTF8Length = _decl("SUStringGetUTF8Length", [Ref, _P(c_size_t)])
SUStringGetUTF8 = _decl("SUStringGetUTF8", [Ref, c_size_t, c_char_p, _P(c_size_t)])

# entities ------------------------------------------------------------------
SUEntitiesGetNumFaces = _decl("SUEntitiesGetNumFaces", [Ref, _P(c_size_t)])
SUEntitiesGetFaces = _decl("SUEntitiesGetFaces", [Ref, c_size_t, _P(Ref), _P(c_size_t)])
SUEntitiesGetNumGroups = _decl("SUEntitiesGetNumGroups", [Ref, _P(c_size_t)])
SUEntitiesGetGroups = _decl("SUEntitiesGetGroups", [Ref, c_size_t, _P(Ref), _P(c_size_t)])
SUEntitiesGetNumInstances = _decl("SUEntitiesGetNumInstances", [Ref, _P(c_size_t)])
SUEntitiesGetInstances = _decl("SUEntitiesGetInstances", [Ref, c_size_t, _P(Ref), _P(c_size_t)])

SUGroupGetEntities = _decl("SUGroupGetEntities", [Ref, _P(Ref)])
SUGroupGetTransform = _decl("SUGroupGetTransform", [Ref, _P(SUTransformation)])
SUGroupGetName = _decl("SUGroupGetName", [Ref, _P(Ref)])

SUComponentInstanceGetTransform = _decl("SUComponentInstanceGetTransform", [Ref, _P(SUTransformation)])
SUComponentInstanceGetDefinition = _decl("SUComponentInstanceGetDefinition", [Ref, _P(Ref)])
SUComponentInstanceGetName = _decl("SUComponentInstanceGetName", [Ref, _P(Ref)])
SUComponentDefinitionGetEntities = _decl("SUComponentDefinitionGetEntities", [Ref, _P(Ref)])
SUComponentDefinitionGetName = _decl("SUComponentDefinitionGetName", [Ref, _P(Ref)])

# faces / loops -------------------------------------------------------------
SUFaceGetArea = _decl("SUFaceGetArea", [Ref, _P(c_double)])
SUFaceGetNormal = _decl("SUFaceGetNormal", [Ref, _P(SUVector3D)])
SUFaceGetPlane = _decl("SUFaceGetPlane", [Ref, _P(SUPlane3D)])
SUFaceGetFrontMaterial = _decl("SUFaceGetFrontMaterial", [Ref, _P(Ref)])
SUFaceGetBackMaterial = _decl("SUFaceGetBackMaterial", [Ref, _P(Ref)])
SUFaceGetOuterLoop = _decl("SUFaceGetOuterLoop", [Ref, _P(Ref)])
SUFaceGetNumInnerLoops = _decl("SUFaceGetNumInnerLoops", [Ref, _P(c_size_t)])
SUFaceGetInnerLoops = _decl("SUFaceGetInnerLoops", [Ref, c_size_t, _P(Ref), _P(c_size_t)])
SULoopGetNumVertices = _decl("SULoopGetNumVertices", [Ref, _P(c_size_t)])
SULoopGetVertices = _decl("SULoopGetVertices", [Ref, c_size_t, _P(Ref), _P(c_size_t)])
SUVertexGetPosition = _decl("SUVertexGetPosition", [Ref, _P(SUPoint3D)])

# triangulation -------------------------------------------------------------
SUMeshHelperCreate = _decl("SUMeshHelperCreate", [_P(Ref), Ref])
SUMeshHelperRelease = _decl("SUMeshHelperRelease", [_P(Ref)])
SUMeshHelperGetNumTriangles = _decl("SUMeshHelperGetNumTriangles", [Ref, _P(c_size_t)])
SUMeshHelperGetNumVertices = _decl("SUMeshHelperGetNumVertices", [Ref, _P(c_size_t)])
SUMeshHelperGetVertexIndices = _decl("SUMeshHelperGetVertexIndices", [Ref, c_size_t, _P(c_size_t), _P(c_size_t)])
SUMeshHelperGetVertices = _decl("SUMeshHelperGetVertices", [Ref, c_size_t, _P(SUPoint3D), _P(c_size_t)])
SUMeshHelperGetNormals = _decl("SUMeshHelperGetNormals", [Ref, c_size_t, _P(SUVector3D), _P(c_size_t)])
SUMeshHelperGetFrontSTQCoords = _decl(
    "SUMeshHelperGetFrontSTQCoords", [Ref, c_size_t, _P(SUPoint3D), _P(c_size_t)]
)

# materials -----------------------------------------------------------------
SUMaterialGetName = _decl("SUMaterialGetName", [Ref, _P(Ref)])
SUMaterialGetNameLegacyBehavior = _decl(
    "SUMaterialGetNameLegacyBehavior", [Ref, _P(Ref)], optional=True
)
SUMaterialGetColor = _decl("SUMaterialGetColor", [Ref, _P(SUColor)])
SUMaterialGetOpacity = _decl("SUMaterialGetOpacity", [Ref, _P(c_double)])
SUMaterialGetUseOpacity = _decl("SUMaterialGetUseOpacity", [Ref, _P(c_bool)])
SUMaterialGetType = _decl("SUMaterialGetType", [Ref, _P(c_int)])
SUMaterialGetTexture = _decl("SUMaterialGetTexture", [Ref, _P(Ref)])
SUTextureGetFileName = _decl("SUTextureGetFileName", [Ref, _P(Ref)])
SUTextureWriteToFile = _decl("SUTextureWriteToFile", [Ref, c_char_p])
SUTextureGetDimensions = _decl(
    "SUTextureGetDimensions", [Ref, _P(c_size_t), _P(c_size_t), _P(c_double), _P(c_double)]
)

# drawing element / layer ---------------------------------------------------
SUDrawingElementGetMaterial = _decl("SUDrawingElementGetMaterial", [Ref, _P(Ref)])
SUDrawingElementGetLayer = _decl("SUDrawingElementGetLayer", [Ref, _P(Ref)])
SUDrawingElementGetHidden = _decl("SUDrawingElementGetHidden", [Ref, _P(c_bool)])
SULayerGetName = _decl("SULayerGetName", [Ref, _P(Ref)])
SULayerGetVisibility = _decl("SULayerGetVisibility", [Ref, _P(c_bool)])

# attributes ----------------------------------------------------------------
SUEntityGetNumAttributeDictionaries = _decl("SUEntityGetNumAttributeDictionaries", [Ref, _P(c_size_t)])
SUEntityGetAttributeDictionaries = _decl(
    "SUEntityGetAttributeDictionaries", [Ref, c_size_t, _P(Ref), _P(c_size_t)]
)
SUEntityGetPersistentID = _decl("SUEntityGetPersistentID", [Ref, _P(ctypes.c_int64)], optional=True)
SUAttributeDictionaryGetName = _decl("SUAttributeDictionaryGetName", [Ref, _P(Ref)])
SUAttributeDictionaryGetNumKeys = _decl("SUAttributeDictionaryGetNumKeys", [Ref, _P(c_size_t)])
SUAttributeDictionaryGetKeys = _decl("SUAttributeDictionaryGetKeys", [Ref, c_size_t, _P(Ref), _P(c_size_t)])
SUAttributeDictionaryGetValue = _decl("SUAttributeDictionaryGetValue", [Ref, c_char_p, _P(Ref)])
SUTypedValueCreate = _decl("SUTypedValueCreate", [_P(Ref)])
SUTypedValueRelease = _decl("SUTypedValueRelease", [_P(Ref)])
SUTypedValueGetType = _decl("SUTypedValueGetType", [Ref, _P(c_int)])
SUTypedValueGetString = _decl("SUTypedValueGetString", [Ref, _P(Ref)])
SUTypedValueGetDouble = _decl("SUTypedValueGetDouble", [Ref, _P(c_double)])
SUTypedValueGetFloat = _decl("SUTypedValueGetFloat", [Ref, _P(ctypes.c_float)], optional=True)
SUTypedValueGetInt32 = _decl("SUTypedValueGetInt32", [Ref, _P(c_int32)], optional=True)
SUTypedValueGetBool = _decl("SUTypedValueGetBool", [Ref, _P(c_bool)], optional=True)

# casts (return a struct by value) ------------------------------------------
SUFaceToDrawingElement = _decl("SUFaceToDrawingElement", [Ref], Ref)
SUFaceToEntity = _decl("SUFaceToEntity", [Ref], Ref)
SUGroupToDrawingElement = _decl("SUGroupToDrawingElement", [Ref], Ref)
SUGroupToEntity = _decl("SUGroupToEntity", [Ref], Ref)
SUComponentInstanceToDrawingElement = _decl("SUComponentInstanceToDrawingElement", [Ref], Ref)
SUComponentInstanceToEntity = _decl("SUComponentInstanceToEntity", [Ref], Ref)
SUMaterialToEntity = _decl("SUMaterialToEntity", [Ref], Ref)


# ---------------------------------------------------------------------------
# Pythonic helpers
# ---------------------------------------------------------------------------


def check(code: int, fn: str) -> None:
    if code != SU_ERROR_NONE:
        raise SketchUpError(fn, code)


def optional(code: int, fn: str) -> bool:
    """True when the call produced data; False on the 'nothing there' codes."""
    if code == SU_ERROR_NONE:
        return True
    if code in (SU_ERROR_NO_DATA, SU_ERROR_NULL_POINTER_INPUT, SU_ERROR_INVALID_INPUT):
        return False
    raise SketchUpError(fn, code)


def get_string(getter, ref: Ref) -> str | None:
    """Drain an SUStringRef-returning getter into a Python str."""
    s = Ref()
    check(SUStringCreate(byref(s)), "SUStringCreate")
    try:
        if not optional(getter(ref, byref(s)), getattr(getter, "__name__", "getter")):
            return None
        n = c_size_t(0)
        check(SUStringGetUTF8Length(s, byref(n)), "SUStringGetUTF8Length")
        buf = ctypes.create_string_buffer(n.value + 1)
        got = c_size_t(0)
        check(SUStringGetUTF8(s, n.value + 1, buf, byref(got)), "SUStringGetUTF8")
        return buf.value.decode("utf-8", "replace")
    finally:
        SUStringRelease(byref(s))


def get_list(count_fn, fill_fn, owner: Ref) -> list[Ref]:
    """Standard two-call 'how many / give me that many' pattern."""
    n = c_size_t(0)
    if not optional(count_fn(owner, byref(n)), getattr(count_fn, "__name__", "count")):
        return []
    if n.value == 0:
        return []
    arr = (Ref * n.value)()
    got = c_size_t(0)
    check(fill_fn(owner, n.value, arr, byref(got)), getattr(fill_fn, "__name__", "fill"))
    return [arr[i] for i in range(got.value)]


def get_string_list(count_fn, fill_fn, owner: Ref) -> list[str]:
    """Two-call pattern for APIs returning an array of SUStringRef.

    Unlike every other ref type, each element must already be a *live* string -
    a zeroed array makes the call fail with SU_ERROR_INVALID_OUTPUT - and the
    caller owns them afterwards.
    """
    n = c_size_t(0)
    if not optional(count_fn(owner, byref(n)), getattr(count_fn, "__name__", "count")):
        return []
    if n.value == 0:
        return []
    arr = (Ref * n.value)()
    for i in range(n.value):
        check(SUStringCreate(byref(arr[i])), "SUStringCreate")
    try:
        got = c_size_t(0)
        check(fill_fn(owner, n.value, arr, byref(got)), getattr(fill_fn, "__name__", "fill"))
        return [s for i in range(got.value) if (s := _string_from_ref(arr[i])) is not None]
    finally:
        for i in range(n.value):
            SUStringRelease(byref(arr[i]))


def read_typed_value(tv: Ref):
    """Convert an SUTypedValue into a Python scalar (arrays become strings)."""
    kind = c_int(0)
    if not optional(SUTypedValueGetType(tv, byref(kind)), "SUTypedValueGetType"):
        return None
    k = kind.value
    if k == TV_STRING:
        return get_string(SUTypedValueGetString, tv)
    if k in (TV_DOUBLE, TV_FLOAT):
        d = c_double(0)
        if SUTypedValueGetDouble(tv, byref(d)) == SU_ERROR_NONE:
            return d.value
        if SUTypedValueGetFloat is not None:
            f = ctypes.c_float(0)
            if SUTypedValueGetFloat(tv, byref(f)) == SU_ERROR_NONE:
                return float(f.value)
        return None
    if k in (TV_INT32, TV_SHORT, TV_BYTE) and SUTypedValueGetInt32 is not None:
        i = c_int32(0)
        if SUTypedValueGetInt32(tv, byref(i)) == SU_ERROR_NONE:
            return i.value
    if k == TV_BOOL and SUTypedValueGetBool is not None:
        b = c_bool(False)
        if SUTypedValueGetBool(tv, byref(b)) == SU_ERROR_NONE:
            return bool(b.value)
    if k == TV_EMPTY:
        return None
    # Anything else (colour, time, vector, array) - fall back to its string form.
    return get_string(SUTypedValueGetString, tv)


def read_attributes(entity: Ref, skip: tuple[str, ...] = ()) -> dict[str, dict]:
    """All attribute dictionaries on an entity, as {dict_name: {key: value}}."""
    out: dict[str, dict] = {}
    dicts = get_list(SUEntityGetNumAttributeDictionaries, SUEntityGetAttributeDictionaries, entity)
    for d in dicts:
        name = get_string(SUAttributeDictionaryGetName, d)
        if not name or name in skip:
            continue
        keys = get_string_list(SUAttributeDictionaryGetNumKeys, SUAttributeDictionaryGetKeys, d)
        entries: dict[str, object] = {}
        for key in keys:
            if not key:
                continue
            tv = Ref()
            check(SUTypedValueCreate(byref(tv)), "SUTypedValueCreate")
            try:
                if optional(
                    SUAttributeDictionaryGetValue(d, key.encode("utf-8"), byref(tv)),
                    "SUAttributeDictionaryGetValue",
                ):
                    entries[key] = read_typed_value(tv)
            finally:
                SUTypedValueRelease(byref(tv))
        if entries:
            out[name] = entries
    return out


def _string_from_ref(s: Ref) -> str | None:
    """Read an SUStringRef we already own (as returned in key arrays)."""
    n = c_size_t(0)
    if SUStringGetUTF8Length(s, byref(n)) != SU_ERROR_NONE:
        return None
    buf = ctypes.create_string_buffer(n.value + 1)
    got = c_size_t(0)
    if SUStringGetUTF8(s, n.value + 1, buf, byref(got)) != SU_ERROR_NONE:
        return None
    return buf.value.decode("utf-8", "replace")


class Model:
    """RAII wrapper: ``with Model(path) as m: ...``."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.ref = Ref()

    def __enter__(self) -> "Model":
        SUInitialize()
        code = SUModelCreateFromFile(byref(self.ref), str(self.path).encode("utf-8"))
        if code == SU_ERROR_MODEL_VERSION:
            SUTerminate()
            raise UnsupportedSkpVersion(
                f"「{self.path.name}」的 SketchUp 版本太新，目前的解析引擎"
                f"（{DLL_PATH.parent.name}）讀不了。請在 SketchUp 中另存為較舊版本，"
                "或改用較新的 SketchUpAPI.dll（設定環境變數 MATBOARD_SU_DLL）。"
            )
        if code in (SU_ERROR_MODEL_INVALID, SU_ERROR_SERIALIZATION):
            SUTerminate()
            raise UnsupportedSkpVersion(
                f"「{self.path.name}」不是有效的 SketchUp 檔案，或檔案已毀損"
                f"（{self.path.stat().st_size:,} bytes）。請確認檔案完整後再上傳。"
            )
        if code != SU_ERROR_NONE:
            SUTerminate()
            raise SketchUpError("SUModelCreateFromFile", code)
        return self

    def __exit__(self, *exc) -> None:
        if self.ref.ptr:
            SUModelRelease(byref(self.ref))
            self.ref = Ref()
        SUTerminate()

    @property
    def version(self) -> str:
        a, b, c = c_int(0), c_int(0), c_int(0)
        if SUModelGetVersion(self.ref, byref(a), byref(b), byref(c)) != SU_ERROR_NONE:
            return "unknown"
        return f"{a.value}.{b.value}.{c.value}"

    @property
    def name(self) -> str | None:
        return get_string(SUModelGetName, self.ref)

    @property
    def entities(self) -> Ref:
        e = Ref()
        check(SUModelGetEntities(self.ref, byref(e)), "SUModelGetEntities")
        return e

    def materials(self) -> list[Ref]:
        return get_list(SUModelGetNumMaterials, SUModelGetMaterials, self.ref)
