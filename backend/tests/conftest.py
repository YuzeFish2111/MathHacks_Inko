"""Shared test setup: never load the real EasyOCR model in tests (slow, needs internet).

By default the API behaves as if OCR is unavailable. Tests that need OCR results replace
app.main.read_handwriting with a fake (see test_api.py).
"""
import pytest

import app.main


@pytest.fixture(autouse=True)
def ocr_unavailable_by_default(monkeypatch):
    monkeypatch.setattr(app.main, "read_handwriting", lambda grayscaleImage: None)
