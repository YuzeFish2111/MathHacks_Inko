"""Drawings and the bundled example have no page edges: the whole image IS the page.

Inko sends them with whole_page, which becomes full-image cornerPointsPx for the analysis backend.
Without it the backend can't tell "page fills the photo" from "no page found", so it leaves
textHeightCanvasRatio (the letter-size measurement) out.
"""
import json
import sys

import httpx
from fastapi.testclient import TestClient

from server import analysis, config
from server.main import app

client = TestClient(app)
EXAMPLE = (config.WEB_DIR / "img" / "example.jpg").read_bytes()
REAL_ANALYZE = analysis.analyze          # captured before the autouse fixture swaps in a fake


def post(whole_page=None):
    data = {"whole_page": whole_page} if whole_page is not None else None
    return client.post("/analyze", data=data, files={"file": ("e.jpg", EXAMPLE, "image/jpeg")})


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
    """End to end with the real analysis backend (backend/app, run in-process, OCR off)."""
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
