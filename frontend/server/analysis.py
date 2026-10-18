"""Talk to the analysis backend (backend/, POST /api/analyze; see shared/analysis-contract.md).

Inko does not score handwriting itself. It sends the prepared photo to the backend and checks
the answer against the backend's own Pydantic contract (backend/app/schemas.py), so a field
that drifts fails here with a clear log line instead of breaking the page.
"""
import importlib.util
import json
import logging
from types import ModuleType

import httpx

from . import config
from .errors import InkoError

log = logging.getLogger("inko")


def _load_backend_module(name: str) -> ModuleType | None:
    """Import one file from backend/app by path. Both files used here only import pydantic/typing."""
    path = config.BACKEND_APP_DIR / f"{name}.py"
    try:
        spec = importlib.util.spec_from_file_location(f"analysis_backend_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        log.warning("Could not load %s; continuing without it", path)
        return None


schemas = _load_backend_module("schemas")
scoring_config = _load_backend_module("scoring_config")
SCHEMA_VERSION = schemas.SCHEMA_VERSION if schemas else None


def validate(body: dict) -> dict:
    """Check a backend response against the contract and return it as plain JSON."""
    if schemas is None:
        return body
    try:
        return schemas.AnalysisResponse.model_validate(body).model_dump(mode="json")
    except Exception as exc:
        log.error("The analysis backend's answer doesn't match shared/analysis-contract.md: %s", exc)
        raise InkoError("analysis_failed") from exc


def whole_image_corners(widthPx: int, heightPx: int) -> str:
    """cornerPointsPx (JSON) saying "the whole image is the page": top-left, top-right, bottom-right,
    bottom-left. Used for on-screen drawings and the bundled example, where there are no page edges
    to find; without it the backend can't tell "page fills the photo" from "no page found" and
    leaves textHeightCanvasRatio out."""
    return json.dumps([[0, 0], [widthPx, 0], [widthPx, heightPx], [0, heightPx]])


async def analyze(jpeg: bytes, wholePageSizePx: tuple[int, int] | None = None, drawing: bool = False) -> dict:
    """POST the photo to the backend. Returns a contract-valid AnalysisResponse (either status).

    wholePageSizePx: (width, height) of the JPEG when the whole image is known to be the page.
    drawing: an on-screen drawing (isDrawing): used whole, and letter size is "Not measured",
    because a screen isn't a page to compare letter size with.
    """
    if drawing:
        form = {"isDrawing": "true"}
    elif wholePageSizePx:
        form = {"cornerPointsPx": whole_image_corners(*wholePageSizePx)}
    else:
        form = None
    try:
        async with httpx.AsyncClient(timeout=config.ANALYSIS_TIMEOUT_S) as client:
            res = await client.post(f"{config.ANALYSIS_API_URL}/api/analyze", data=form,
                                    files={"imageFile": ("photo.jpg", jpeg, "image/jpeg")})
    except httpx.TimeoutException as exc:
        log.error("The analysis backend took longer than %ss", config.ANALYSIS_TIMEOUT_S)
        raise InkoError("analysis_failed") from exc
    except httpx.HTTPError as exc:
        log.error("Can't reach the analysis backend at %s (%s). Start it with: "
                  "cd backend && uvicorn app.main:app --reload", config.ANALYSIS_API_URL, exc)
        raise InkoError("analysis_offline") from exc
    if res.status_code != 200:
        # 422 means Inko sent a bad form field: our bug, not the person's photo
        log.error("The analysis backend answered %s: %s", res.status_code, res.text[:500])
        raise InkoError("analysis_failed")
    return validate(res.json())


async def health() -> dict:
    """Is the backend up, and does it speak the same contract version?"""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            body = (await client.get(f"{config.ANALYSIS_API_URL}/api/health")).json()
    except Exception:
        return {"url": config.ANALYSIS_API_URL, "reachable": False}
    version = body.get("schemaVersion")
    return {"url": config.ANALYSIS_API_URL, "reachable": True, "schemaVersion": version,
            "schemaMatches": SCHEMA_VERSION is None or version == SCHEMA_VERSION}


def scoring_model() -> dict | None:
    """The scoring curves, feature sources, weights and score bands, straight from
    backend/app/scoring_config.py, so the results screen can show ideal ranges without copying them."""
    c = scoring_config
    if c is None:
        return None
    curves = {name: {"kind": "sweetSpot", "a": a, "b": b, "c": cc, "d": d}
              for name, (a, b, cc, d) in c.SWEET_SPOT_CURVES.items()}
    curves.update({name: {"kind": "decreasing", "v0": v0, "v1": v1}
                   for name, (v0, v1) in c.DECREASING_CURVES.items()})
    return {
        "schemaVersion": SCHEMA_VERSION,
        "featureSources": {k: list(v) for k, v in c.FEATURE_SOURCES.items()},
        "featureWeights": dict(c.FEATURE_WEIGHTS),
        "curves": curves,
        "scoreBands": [{"minScore": lo, "label": label} for lo, label in c.SCORE_BANDS],
    }
