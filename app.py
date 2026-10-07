"""Local UI for reviewing OrcaSlicer settings and applying the result."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from advisor.apply import apply_changes
from advisor.profiles import delete_user_preset, list_user_presets
from advisor.feedback import review_changes
from advisor.filaments import filament_options
from advisor.grok_chat import send_to_grok
from advisor.mesh import mesh_stats
from advisor.snapshot import build_snapshot

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
UPLOADS = WORK / "uploads"
STATE_PATH = WORK / "state.json"

app = FastAPI(title="OrcaSlicer Advisor")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class StateIn(BaseModel):
    setup: int | None = None
    notes: str = ""
    brand: str = ""
    type: str = ""
    color: str = ""
    diameter_mm: str = ""


class FeedbackIn(BaseModel):
    setup: int
    feedback: str


class PresetIn(BaseModel):
    kind: str
    name: str


class GrokIn(BaseModel):
    prompt: str


class ChangeIn(BaseModel):
    setup: int
    diffs: list[dict] = Field(default_factory=list)
    label: str = ""


def _read_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    return json.loads(STATE_PATH.read_text())


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _attached_model() -> tuple[dict | None, Path | None]:
    raw = _read_state().get("model")
    if not raw:
        return None, None
    file_path = Path(raw)
    if not file_path.is_file():
        return None, None
    return mesh_stats(file_path), file_path


@app.get("/")
def index() -> FileResponse:
    # A new visit should not revive an STL from the last time the page was open.
    state = _read_state()
    if state.pop("model", None) is not None:
        _write_state(state)
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/filament-options")
def filament_choices() -> dict:
    return filament_options()


@app.post("/api/state")
def state(body: StateIn) -> dict:
    try:
        snapshot = build_snapshot(
            body.setup,
            body.notes,
            {
                "brand": body.brand,
                "type": body.type,
                "color": body.color,
                "diameter_mm": body.diameter_mm,
            },
            _attached_model()[0],
        )
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return snapshot


@app.post("/api/model")
async def upload_model(file: UploadFile = File(...)) -> dict:
    filename = Path(file.filename or "model.stl").name
    if not filename.lower().endswith(".stl"):
        raise HTTPException(status_code=400, detail="Choose an STL file.")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    destination = UPLOADS / filename
    destination.write_bytes(await file.read())
    try:
        stats = mesh_stats(destination)
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state = _read_state()
    state["model"] = str(destination)
    _write_state(state)
    return stats


@app.delete("/api/model")
def clear_model() -> dict:
    state = _read_state()
    state.pop("model", None)
    _write_state(state)
    return {"cleared": True}


@app.get("/api/user-presets")
def user_presets() -> dict:
    return {"presets": list_user_presets()}


@app.delete("/api/user-presets")
def remove_user_preset(body: PresetIn) -> dict:
    try:
        deleted = delete_user_preset(body.kind, body.name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "deleted": deleted,
        "note": "Quit OrcaSlicer and reopen it. The preset then leaves the User presets menu.",
    }


@app.post("/api/review")
def review(body: FeedbackIn) -> dict:
    try:
        return review_changes(body.setup, body.feedback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/apply")
def apply(body: ChangeIn) -> dict:
    try:
        return apply_changes(body.setup, body.diffs, body.label)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/grok")
async def ask_grok(body: GrokIn) -> dict:
    try:
        reply = await asyncio.to_thread(send_to_grok, body.prompt, _attached_model()[1])
    except (TimeoutError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"reply": reply}
