"""Inko web server: the web app, accounts and history, all on one port.

POST /analyze prepares the photo (HEIC, EXIF rotation, resize) and forwards it to the
analysis backend's POST /api/analyze (backend/, see shared/analysis-contract.md). The backend's
answer is passed through unchanged as `analysis`, wrapped with Inko's own fields.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import analysis, auth, config, db, history, imaging, jev_checks, photo_checks, social
from .errors import MESSAGES, InkoError
from .pending import pending

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("inko")
logging.getLogger("httpx").setLevel(logging.WARNING)   # one line per backend call is noise

app = FastAPI(title="Inko", docs_url="/api/docs", openapi_url="/api/openapi.json")
db.init()
app.include_router(auth.router)
app.include_router(history.router)
app.include_router(social.router)


@app.exception_handler(InkoError)
async def inko_error(_: Request, exc: InkoError):
    return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(
        {"error": {"code": "invalid_input", "message": MESSAGES["invalid_input"]}}, status_code=400
    )


@app.middleware("http")
async def no_stale_app_files(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if request.method == "GET" and not path.startswith("/api/"):
        # Revalidate app files every load (cheap 304s) so changes show up immediately.
        if not path.startswith(("/fonts/", "/icons/", "/img/")):
            response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/health")
async def health():
    return {"ok": True, "analysis": await analysis.health(), "jev": jev_checks.enabled()}


@app.get("/api/scoring-model")
def scoring_model():
    """Curves, weights and score bands from backend/app/scoring_config.py (ideal ranges for the UI)."""
    model = analysis.scoring_model()
    if model is None:
        raise InkoError("not_found")
    return model


def summary_scores(result: dict) -> dict:
    """featureScores as whole numbers out of 100 (null stays null), for Progress and Practice."""
    return {featureId: None if score is None else round(score * 100)
            for featureId, score in (result["featureScores"] or {}).items()}


@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...), whole_page: bool = Form(False)):
    """whole_page: the whole image is the page (on-screen drawing, bundled example), so the backend
    is told its exact bounds instead of looking for page edges that aren't there."""
    data = await file.read()
    image = await run_in_threadpool(imaging.prepare, data)
    tilt = await run_in_threadpool(photo_checks.detect_tilt, image.gray)

    # Jev looks at the photo while the backend scores it (skipped when there is no key).
    jev_task = asyncio.create_task(jev_checks.photo_check(image)) if jev_checks.enabled() else None
    try:
        result = await analysis.analyze(image.jpeg, (image.width, image.height) if whole_page else None)
        jev = await jev_task if jev_task else None
    finally:
        if jev_task and not jev_task.done():
            jev_task.cancel()
    if jev and jev["has_handwriting"] < jev_checks.NO_HANDWRITING_BELOW:
        raise InkoError("no_handwriting")

    tilted = tilt["tilted"] or bool(jev and jev["tilted"] >= jev_checks.TILTED_AT)
    shadows = bool(jev and jev["shadows"] >= jev_checks.SHADOWS_AT)
    response = {
        "result_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "photo_check": {"tilted": tilted, "shadows": shadows, "jev_used": jev is not None},
        "analysis": result,
        "saved": False,
    }
    complete = result["status"] == "complete" and result["legibilityScore"] is not None
    log.info("Analyzed %dx%d photo: %s, score %s, tilted %s%s", image.width, image.height, result["status"],
             result["legibilityScore"], tilted, f", jev {jev}" if jev else "")
    if not complete:
        return response   # needs_better_photo: nothing to save

    response["overall_score"] = result["legibilityScore"]
    response["scores"] = summary_scores(result)
    page_jpeg = imaging.data_url_bytes(result["rectifiedImage"])
    overlay = result["overlayData"]
    stored = {k: v for k, v in response.items() if k != "saved"}
    # The image lives in its own column, so the stored JSON leaves out the large data URL
    stored["analysis"] = {**result, "rectifiedImage": None}
    entry = {
        "result": stored,
        "width": overlay["imageWidthPx"],
        "height": overlay["imageHeightPx"],
        "preview": page_jpeg,
        "thumb": await run_in_threadpool(imaging.thumbnail_jpeg, page_jpeg),
    }
    pending.put(response["result_id"], entry)
    # Signed in: save straight to Progress, unless the photo is tilted (the person
    # decides first, and "Use this photo anyway" saves it).
    user = auth.current_user(request)
    if user and not tilted:
        history.save(user["id"], entry)
        response["saved"] = True
    return response


# The web app. Mounted last so the API routes above win.
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="app")
