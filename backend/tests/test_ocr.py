import numpy as np

import app.accuracy_evaluation as ocr


class FakeReader:
    """Stands in for easyocr.Reader: returns fixed (boundingBox, text, confidence) detections."""

    def __init__(self, detections):
        self.detections = detections

    def readtext(self, image, detail=1, paragraph=False):
        return self.detections


BOX = [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_confidence_is_weighted_by_character_count():
    reader = FakeReader([(BOX, "The quick", 0.9), (BOX, "fox", 0.3), (BOX, "   ", 0.1)])
    text, meanConfidence, scorePct, _ = ocr.measure_handwriting_legibility(np.zeros((5, 5), np.uint8), reader)
    assert text == "The quick\nfox"                    # blank detections are skipped
    assert abs(meanConfidence - (8 * 0.9 + 3 * 0.3) / 11) < 1e-9    # 8 letters at 0.9, 3 at 0.3
    assert abs(scorePct - 100 * meanConfidence) < 1e-9


def test_no_text_gives_null_not_zero():
    _, meanConfidence, scorePct, _ = ocr.measure_handwriting_legibility(np.zeros((5, 5), np.uint8), FakeReader([]))
    assert meanConfidence is None and scorePct is None


def test_read_handwriting_returns_percent_and_detections(monkeypatch):
    monkeypatch.setattr(ocr, "get_reader", lambda: FakeReader([(BOX, "hello", 0.8)]))
    result = ocr.read_handwriting(np.zeros((5, 5), np.uint8))
    assert abs(result.confidencePct - 80.0) < 1e-9 and result.recognizedText == "hello"
    assert result.detections == [(BOX, "hello", 0.8)]


def test_model_that_fails_to_load_is_reported_once_and_returns_none(monkeypatch):
    loadAttempts = []

    def failing_load():
        loadAttempts.append(1)
        raise OSError("model download blocked")

    monkeypatch.setattr(ocr, "load_reader", failing_load)
    monkeypatch.setattr(ocr, "_reader", None)
    monkeypatch.setattr(ocr, "_readerLoadFailed", False)
    assert ocr.read_handwriting(np.zeros((5, 5), np.uint8)) is None
    assert ocr.read_handwriting(np.zeros((5, 5), np.uint8)) is None
    assert len(loadAttempts) == 1                       # not retried on every request


def test_disabled_ocr_never_loads_the_model(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_ENABLED", False)
    monkeypatch.setattr(ocr, "load_reader", lambda: (_ for _ in ()).throw(AssertionError("should not load")))
    assert ocr.get_reader() is None
