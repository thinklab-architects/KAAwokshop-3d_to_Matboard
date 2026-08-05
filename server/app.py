"""Upload a .skp, convert it, serve the result to the viewer."""

from __future__ import annotations

import json
import shutil
import threading
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "converter"))
# So `report` resolves whether this is loaded as server.app or as app.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from report import build_report  # noqa: E402
from skp2web import sdk  # noqa: E402
from skp2web.cli import convert  # noqa: E402

STORAGE = ROOT / "storage"
WEB_DIST = ROOT / "web" / "dist"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024

# SUInitialize/SUTerminate are process-global, so two conversions running at the
# same time would tear down each other's SDK session. One at a time.
_convert_lock = threading.Lock()

app = FastAPI(title="Matboard", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _project_dir(project_id: str) -> Path:
    # Reject anything that could climb out of storage/.
    if not project_id or not all(c.isalnum() or c == "-" for c in project_id):
        raise HTTPException(400, "bad project id")
    path = STORAGE / project_id
    if not path.is_dir():
        raise HTTPException(404, "project not found")
    return path


def _meta(path: Path) -> dict | None:
    f = path / "project.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    # A folder converted straight from the CLI has no project.json; synthesise
    # one so it still shows up in the list.
    model = path / "model.json"
    if not model.is_file():
        return None
    try:
        doc = json.loads(model.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    source = path / "source.skp"
    meta = {
        "id": path.name,
        "name": doc["source"].get("modelName") or Path(doc["source"]["file"]).stem,
        "originalName": doc["source"]["file"],
        "sizeBytes": source.stat().st_size if source.is_file() else 0,
        "uploadedAt": doc["source"]["generatedAt"],
        "status": "ready",
        "stats": doc["stats"],
        "bbox": doc["bbox"],
        "skpVersion": doc["source"]["skpVersion"],
        "materialCount": len(doc["materials"]),
    }
    f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def _engine_label() -> str:
    """What to call the parsing engine in the sidebar.

    A DLL found inside an installed SketchUp sits in a folder named after the
    release - "SketchUp 2022" - which is the useful thing to show. A copy
    bundled under vendor/ would show its directory name instead, so name it.
    """
    try:
        sdk.DLL_PATH.relative_to(ROOT / "vendor")
    except ValueError:
        return sdk.DLL_PATH.parent.name
    return "SketchUp SDK（內附）"


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "sdk": str(sdk.DLL_PATH),
        "sketchup": _engine_label(),
    }


@app.get("/api/projects")
def list_projects() -> list[dict]:
    STORAGE.mkdir(parents=True, exist_ok=True)
    out = [m for d in STORAGE.iterdir() if d.is_dir() and (m := _meta(d))]
    return sorted(out, key=lambda m: m.get("uploadedAt", ""), reverse=True)


@app.post("/api/projects")
async def create_project(file: UploadFile = File(...)) -> JSONResponse:
    name = Path(file.filename or "model.skp").name
    if not name.lower().endswith(".skp"):
        raise HTTPException(400, "只接受 .skp 檔")

    project_id = uuid.uuid4().hex[:12]
    target = STORAGE / project_id
    target.mkdir(parents=True, exist_ok=True)
    source = target / "source.skp"

    size = 0
    try:
        with source.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "檔案過大（上限 512 MB）")
                fh.write(chunk)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise

    meta = {
        "id": project_id,
        "name": Path(name).stem,
        "originalName": name,
        "sizeBytes": size,
        "uploadedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "converting",
    }
    (target / "project.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def _run() -> dict:
        with _convert_lock:
            return convert(source, target, quiet=True)

    def _fail(message: str, status: int):
        # The converter only ever sees the stored path, so put the user's own
        # filename back into anything we show them.
        message = message.replace(source.name, name)
        meta.update(status="error", error=message)
        (target / "project.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return HTTPException(status, message)

    try:
        doc = await run_in_threadpool(_run)
    except sdk.UnsupportedSkpVersion as exc:
        raise _fail(str(exc), 422) from exc
    except Exception as exc:  # noqa: BLE001 - surface whatever the SDK said
        raise _fail(f"{type(exc).__name__}: {exc}", 500) from exc

    meta.update(
        status="ready",
        stats=doc["stats"],
        bbox=doc["bbox"],
        skpVersion=doc["source"]["skpVersion"],
        materialCount=len(doc["materials"]),
    )
    (target / "project.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return JSONResponse(meta, status_code=201)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    meta = _meta(_project_dir(project_id))
    if meta is None:
        raise HTTPException(404, "project not found")
    return meta


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    shutil.rmtree(_project_dir(project_id), ignore_errors=True)
    return {"deleted": project_id}


# These live at a stable URL but their content changes whenever a project is
# reconverted, so browsers have to revalidate rather than reuse blindly.
# ETag/Last-Modified still make the common case a cheap 304.
_REVALIDATE = {"Cache-Control": "no-cache"}


@app.get("/api/projects/{project_id}/model.json")
def get_model(project_id: str) -> FileResponse:
    f = _project_dir(project_id) / "model.json"
    if not f.is_file():
        raise HTTPException(404, "not converted")
    return FileResponse(f, media_type="application/json", headers=_REVALIDATE)


@app.get("/api/projects/{project_id}/mesh.bin")
def get_mesh(project_id: str) -> FileResponse:
    f = _project_dir(project_id) / "mesh.bin"
    if not f.is_file():
        raise HTTPException(404, "not converted")
    return FileResponse(f, media_type="application/octet-stream", headers=_REVALIDATE)


@app.get("/api/projects/{project_id}/textures/{name}")
def get_texture(project_id: str, name: str) -> FileResponse:
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "bad texture name")
    f = _project_dir(project_id) / "textures" / name
    if not f.is_file():
        raise HTTPException(404, "texture not found")
    return FileResponse(f, headers=_REVALIDATE)


class ReportOptions(BaseModel):
    """What the report says on its face, and the basis it is produced on."""

    projectName: str | None = None
    site: str | None = None
    excluded: list[int] = []
    net: bool = False


@app.post("/api/projects/{project_id}/report.pdf")
async def get_report(project_id: str, options: ReportOptions | None = None) -> Response:
    path = _project_dir(project_id)
    model = path / "model.json"
    if not model.is_file():
        raise HTTPException(404, "not converted")
    meta = _meta(path) or {}
    doc = json.loads(model.read_text(encoding="utf-8"))
    options = options or ReportOptions()

    title = (options.projectName or "").strip() or meta.get("name") or project_id
    pdf = await run_in_threadpool(
        build_report,
        doc,
        project_name=title,
        site=(options.site or "").strip(),
        excluded=set(options.excluded),
        net=options.net,
        assets_dir=path,
    )
    # Keep the filename filesystem-safe; the user types this field freely.
    safe = "".join(c for c in title if c not in '\\/:*?"<>|').strip() or "建材彙整"
    name = f"{safe}_建材彙整.pdf"
    quoted = urllib.parse.quote(name)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            # RFC 5987, so the Chinese filename survives the download.
            "Content-Disposition": f"attachment; filename=\"report.pdf\"; filename*=UTF-8''{quoted}",
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/projects/{project_id}/source.skp")
def get_source(project_id: str) -> FileResponse:
    meta = _meta(_project_dir(project_id)) or {}
    f = _project_dir(project_id) / "source.skp"
    if not f.is_file():
        raise HTTPException(404, "source not found")
    return FileResponse(f, filename=meta.get("originalName", "model.skp"))


class _Viewer(StaticFiles):
    """Static files with the cache policy a hashed bundle actually wants.

    Asset filenames carry a content hash, so they can be cached forever. The
    entry HTML cannot: a cached copy keeps pointing at the previous build's
    bundle, and the app silently stays on the old version after a redeploy.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path in ("", ".", "index.html") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        elif "/assets/" in f"/{path}":
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# The built viewer, when there is one. Mounted last so /api wins.
if WEB_DIST.is_dir():
    app.mount("/", _Viewer(directory=WEB_DIST, html=True), name="web")
