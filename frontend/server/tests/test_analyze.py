import io

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server import analysis, config, photo_checks
from server.errors import MESSAGES, InkoError
from server.main import app

from .helpers import encode, fake_backend, fixture, handwriting, page_on_table

client = TestClient(app)
REAL_ANALYZE = analysis.analyze   # kept before the autouse fixture swaps in the fake


def post(data: bytes, name: str = "photo.jpg", mime: str = "image/jpeg"):
    return client.post("/analyze", files={"file": (name, data, mime)})


def sent_size(jpeg: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(jpeg)).size


def test_health_reports_the_analysis_backend():
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["analysis"]["url"] == config.ANALYSIS_API_URL


def test_contract_and_scoring_config_are_read_from_the_backend():
    assert analysis.SCHEMA_VERSION == fixture("complete-response")["schemaVersion"]
    model = client.get("/api/scoring-model").json()
    assert set(model["featureSources"]) == set(fixture("complete-response")["featureScores"])
    assert model["curves"]["letterSpacingCv"]["kind"] == "decreasing"
    assert model["curves"]["relativeLetterSpacing"]["kind"] == "sweetSpot"


def test_complete_result_passes_the_contract_through(backend):
    res = post(encode(handwriting(), "JPEG"))
    assert res.status_code == 200, res.text
    body = res.json()
    expected = fixture("complete-response")
    assert body["analysis"]["legibilityScore"] == expected["legibilityScore"]
    assert body["analysis"]["overlayData"] == expected["overlayData"]
    assert body["overall_score"] == expected["legibilityScore"]
    assert body["scores"]["letterSpacing"] == round(expected["featureScores"]["letterSpacing"] * 100)
    assert body["analysis"]["rectifiedImage"].startswith("data:image/jpeg;base64,")
    assert len(backend) == 1


def test_needs_better_photo_is_returned_not_saved(monkeypatch):
    fake_backend(monkeypatch, fixture("needs-better-photo-response"))
    body = post(encode(handwriting(), "JPEG")).json()
    assert body["analysis"]["status"] == "needs_better_photo"
    assert body["analysis"]["error"]["message"]
    assert "overall_score" not in body and body["saved"] is False


def test_contract_drift_is_caught():
    bad = fixture("complete-response")
    bad["featureScores"]["letterSpacingScore"] = 0.5   # not a contract field
    with pytest.raises(InkoError):
        analysis.validate(bad)


def test_backend_offline_gives_a_clear_message(monkeypatch):
    monkeypatch.setattr(analysis, "analyze", REAL_ANALYZE)
    monkeypatch.setattr(config, "ANALYSIS_API_URL", "http://127.0.0.1:9")   # nothing listens there
    res = post(encode(handwriting(), "JPEG"))
    assert res.status_code == 503
    assert res.json()["error"]["message"] == MESSAGES["analysis_offline"]


@pytest.mark.parametrize("fmt,name,mime", [
    ("PNG", "a.png", "image/png"),
    ("JPEG", "a.jpg", "image/jpeg"),
    ("HEIF", "a.heic", "image/heic"),
    ("WEBP", "a.webp", "image/webp"),
])
def test_every_supported_format_is_sent_as_jpeg(backend, fmt, name, mime):
    res = post(encode(handwriting(), fmt), name, mime)
    assert res.status_code == 200, res.text
    assert backend[-1].startswith(b"\xff\xd8\xff")   # the backend can't open HEIC itself


def test_heic_with_misleading_name_and_type_still_works():
    # Some browsers send HEIC as application/octet-stream or with a .jpg name.
    res = post(encode(handwriting(), "HEIF"), "IMG_0042.JPG", "application/octet-stream")
    assert res.status_code == 200, res.text


def test_exif_rotation_is_applied_before_the_backend_sees_it(backend):
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 degrees clockwise to display"
    res = post(encode(handwriting(1200, 800), "JPEG", exif=exif))
    assert res.status_code == 200, res.text
    assert sent_size(backend[-1]) == (800, 1200)


def test_big_phone_photo_is_resized(backend):
    res = post(encode(handwriting(4032, 3024), "JPEG", quality=90))
    assert res.status_code == 200, res.text
    assert max(sent_size(backend[-1])) == config.MAX_MODEL_SIDE


def test_transparent_png_from_canvas_is_flattened_onto_white(backend):
    rgba = np.zeros((600, 900, 4), np.uint8)
    strokes = handwriting(900, 600)
    ink = strokes[:, :, 0] < 128
    rgba[ink] = (0, 0, 0, 255)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    res = post(buf.getvalue(), "drawing.png", "image/png")
    assert res.status_code == 200, res.text
    corner = Image.open(io.BytesIO(backend[-1])).convert("L").getpixel((2, 2))
    assert corner > 240


def test_wrong_file_type():
    for data in (b"just some text", b"GIF89a" + b"\x00" * 100, b"%PDF-1.7 fake"):
        res = post(data, "notes.txt", "text/plain")
        assert res.status_code == 415
        assert res.json()["error"]["message"] == MESSAGES["wrong_file_type"]


def test_corrupt_image_counts_as_wrong_type():
    res = post(b"\x89PNG\r\n\x1a\n" + b"garbage" * 50, "broken.png", "image/png")
    assert res.status_code == 415


def test_file_too_big():
    res = post(b"\xff\xd8\xff" + b"\x00" * (config.MAX_UPLOAD_BYTES + 1))
    assert res.status_code == 413
    assert res.json()["error"]["message"] == MESSAGES["file_too_big"]


def test_tilt_detection():
    straight = photo_checks.detect_tilt(cv2.cvtColor(page_on_table(False), cv2.COLOR_BGR2GRAY))
    tilted = photo_checks.detect_tilt(cv2.cvtColor(page_on_table(True), cv2.COLOR_BGR2GRAY))
    assert straight["paper_found"] and not straight["tilted"]
    assert tilted["paper_found"] and tilted["tilted"]


def test_tilted_photo_is_flagged_end_to_end():
    res = post(encode(page_on_table(True), "JPEG"))
    assert res.status_code == 200, res.text
    assert res.json()["photo_check"]["tilted"] is True


def test_rotated_but_straight_page_is_not_tilted():
    rotated = cv2.rotate(page_on_table(False), cv2.ROTATE_90_CLOCKWISE)
    assert not photo_checks.detect_tilt(cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY))["tilted"]
