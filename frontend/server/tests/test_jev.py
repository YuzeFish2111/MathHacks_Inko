"""Jev is optional: these tests fake its answers to check how Inko combines them."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server import config, imaging, jev_checks
from server.main import app

from .helpers import encode, handwriting

client = TestClient(app)
EXAMPLE = (config.WEB_DIR / "img" / "example.jpg").read_bytes()


def fake_jev(monkeypatch, photo=None):
    async def photo_check(image):
        return photo

    monkeypatch.setattr(jev_checks, "enabled", lambda: True)
    monkeypatch.setattr(jev_checks, "photo_check", photo_check)


def post(data):
    return client.post("/analyze", files={"file": ("a.jpg", data, "image/jpeg")})


def test_jev_can_flag_a_tilted_photo_and_shadows(monkeypatch):
    fake_jev(monkeypatch, photo={"tilted": 0.93, "has_handwriting": 0.99, "shadows": 0.88})
    body = post(EXAMPLE).json()
    assert body["photo_check"] == {"tilted": True, "shadows": True, "jev_used": True}


def test_unsure_jev_does_not_flag(monkeypatch):
    fake_jev(monkeypatch, photo={"tilted": 0.55, "has_handwriting": 0.97, "shadows": 0.4})
    body = post(EXAMPLE).json()
    assert body["photo_check"] == {"tilted": False, "shadows": False, "jev_used": True}


def test_jev_no_handwriting(monkeypatch):
    fake_jev(monkeypatch, photo={"tilted": 0.1, "has_handwriting": 0.01, "shadows": 0.1})
    assert post(encode(handwriting(), "JPEG")).status_code == 422


def test_jev_failure_is_skipped(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(jev_checks, "enabled", lambda: True)
    monkeypatch.setattr(jev_checks, "_ask", boom)
    res = post(EXAMPLE)
    assert res.status_code == 200
    assert res.json()["photo_check"]["jev_used"] is False


def test_images_sent_to_jev_meet_size_limits():
    tiny = imaging.prepare(encode(handwriting(300, 200), "PNG"))
    photo = Image.open(io.BytesIO(jev_checks._photo_for_jev(tiny)))
    assert min(photo.size) >= 280 and max(photo.size) <= 1568


@pytest.mark.skipif(not config.TYPESAFE_API_KEY, reason="needs TYPESAFE_API_KEY")
def test_live_jev_photo_check():
    import asyncio
    out = asyncio.run(jev_checks.photo_check(imaging.prepare(EXAMPLE)))
    assert out and out["has_handwriting"] > 0.5
