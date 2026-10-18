"""The bundled example and on-screen drawings have no page edges to find.

The example is a photo of a page that fills the image: Inko sends it with whole_page, which becomes
full-image cornerPointsPx, so letter size is judged against that page. Without it the backend can't tell
"page fills the photo" from "no page found", so it leaves textHeightCanvasRatio (letter size) out.

A drawing is sent with drawing, which becomes isDrawing: the image is used whole too, but a screen isn't
a page, so letter size is "Not measured" and the score comes from the other seven features.
"""
import json
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from server import analysis, config
from server.main import app

client = TestClient(app)
EXAMPLE = (config.WEB_DIR / "img" / "example.jpg").read_bytes()
REAL_ANALYZE = analysis.analyze          # captured before the autouse fixture swaps in a fake


def post(whole_page=None, drawing=None):
    data = {k: v for k, v in {"whole_page": whole_page, "drawing": drawing}.items() if v is not None} or None
    return client.post("/analyze", data=data, files={"file": ("e.jpg", EXAMPLE, "image/jpeg")})


def test_drawing_flag_is_forwarded(backend):
    assert post(drawing="true").status_code == 200
    assert backend.drawingFlags[-1] is True and backend.wholePageSizes[-1] is None
    assert post("true").status_code == 200
    assert backend.drawingFlags[-1] is False                     # the example is a page, not a drawing


def test_drawing_form_field_names_match_the_backend():
    assert "isDrawing" in analysis.schemas.AnalyzeRequestFields.model_fields


def test_whole_page_flag_sends_the_image_size(backend):
    assert post("true").status_code == 200
    width, height = backend.wholePageSizes[-1]
    assert (width, height) == (1240, 1130)                      # the example photo's size


def test_ordinary_photos_still_use_page_detection(backend):
    assert post().status_code == 200
    assert backend.wholePageSizes[-1] is None


def test_whole_image_corners_are_in_contract_order():
    assert json.loads(analysis.whole_image_corners(100, 50)) == [[0, 0], [100, 0], [100, 50], [0, 50]]


def test_real_backend_scores_letter_size_only_with_the_flag(monkeypatch):
    """End to end with the real analysis backend (backend/app, run in-process, OCR off).

    Needs the backend's own packages (SciPy etc.), which Inko's .venv doesn't install, so it is
    skipped there and runs where the backend's requirements are installed.
    """
    pytest.importorskip("scipy", reason="needs the analysis backend's packages (pip install -r backend/requirements.txt)")
    sys.path.insert(0, str(config.PROJECT_ROOT / "backend"))
    import app.main as backend_main
    monkeypatch.setattr(backend_main, "read_handwriting", lambda grayscaleImage: None)
    monkeypatch.setattr(analysis, "analyze", REAL_ANALYZE)
    realClient = httpx.AsyncClient

    def in_process_client(**kwargs):
        return realClient(transport=httpx.ASGITransport(app=backend_main.app), base_url="http://backend")

    monkeypatch.setattr(httpx, "AsyncClient", in_process_client)
    monkeypatch.setattr(config, "ANALYSIS_API_URL", "http://backend")

    withFlag = post("true").json()["analysis"]
    without = post().json()["analysis"]
    assert withFlag["status"] == without["status"] == "complete"
    assert withFlag["featureMeasurements"]["textHeightCanvasRatio"] is not None
    assert "textSize" not in withFlag["missingFeatureIds"]
    assert without["featureMeasurements"]["textHeightCanvasRatio"] is None   # ordinary photo, no edges found

    drawing = post(drawing="true").json()["analysis"]
    assert drawing["status"] == "complete" and drawing["legibilityScore"] is not None
    assert drawing["featureMeasurements"]["textHeightCanvasRatio"] is None   # a screen isn't a page
    assert drawing["missingFeatureIds"] == ["textSize"]
    assert not any("page edges" in warning for warning in drawing["warnings"])
