"""Saved results for signed-in users (the Progress page)."""
import json

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from . import db
from .auth import require_user
from .errors import InkoError
from .pending import pending

router = APIRouter(prefix="/api/history")


def save(user_id: int, entry: dict) -> None:
    result = entry["result"]
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO results (id, user_id, created_at, overall, data, width, height, preview, thumb) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (result["result_id"], user_id, result["created_at"], result["overall_score"],
             json.dumps(result), entry["width"], entry["height"], entry["preview"], entry["thumb"]),
        )


@router.get("")
def list_results(request: Request):
    user = require_user(request)
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, data FROM results WHERE user_id = ? ORDER BY created_at, rowid", (user["id"],)
        ).fetchall()
    items = []
    for row in rows:
        data = json.loads(row["data"])
        items.append({
            "id": row["id"],
            "created_at": row["created_at"],
            "overall_score": data["overall_score"],
            "scores": data["scores"],
            "thumb_url": f"/api/history/{row['id']}/thumb.jpg",
        })
    return {"items": items}


def _own_row(request: Request, result_id: str, columns: str):
    user = require_user(request)
    with db.connect() as conn:
        row = conn.execute(f"SELECT {columns} FROM results WHERE id = ? AND user_id = ?", (result_id, user["id"])).fetchone()
    if not row:
        raise InkoError("not_found")
    return row


@router.get("/{result_id}")
def get_result(request: Request, result_id: str):
    row = _own_row(request, result_id, "data, width, height")
    data = json.loads(row["data"])
    data["analysis"]["rectifiedImage"] = f"/api/history/{result_id}/image.jpg"   # the page overlays refer to
    data["saved"] = True
    return data


@router.get("/{result_id}/image.jpg")
def get_image(request: Request, result_id: str):
    row = _own_row(request, result_id, "preview")
    return Response(row["preview"], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{result_id}/thumb.jpg")
def get_thumb(request: Request, result_id: str):
    row = _own_row(request, result_id, "thumb")
    return Response(row["thumb"], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class SaveBody(BaseModel):
    result_id: str


@router.post("/save")
def save_pending(request: Request, body: SaveBody):
    user = require_user(request)
    entry = pending.get(body.result_id)
    if not entry:
        raise InkoError("not_found", "That result expired. Please scan it again to save it.")
    save(user["id"], entry)
    return {"saved": True}


@router.delete("")
def clear(request: Request):
    user = require_user(request)
    with db.connect() as conn:
        deleted = conn.execute("DELETE FROM results WHERE user_id = ?", (user["id"],)).rowcount
    return {"deleted": deleted}
