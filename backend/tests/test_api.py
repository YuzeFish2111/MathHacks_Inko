import json

import cv2
import numpy as np
from fastapi.testclient import TestClient

import app.main as mainModule
from app.accuracy_evaluation import OcrResult
from app.main import app
from app.schemas import AnalysisResponse
from app.scoring_config import MAX_UPLOAD_BYTES

client = TestClient(app)
A4 = {"pageWidthMm": "210", "pageHeightMm": "297"}


def make_page_photo(inkLevel=0, paperLevel=255):
    """A4-proportioned page (1000 x 1414 px) with the pangram on two lines."""
    page = np.full((1414, 1000, 3), paperLevel, np.uint8)
    ink = (inkLevel, inkLevel, inkLevel)
    cv2.putText(page, "The quick brown fox", (80, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.6, ink, 3)
    cv2.putText(page, "jumps over the lazy dog.", (80, 520), cv2.FONT_HERSHEY_SIMPLEX, 1.6, ink, 3)
    return page


def png_bytes(image):
    return cv2.imencode(".png", image)[1].tobytes()


def post(imageBytes, contentType="image/png", **fields):
    return client.post("/api/analyze", data={**A4, **fields},
                       files={"imageFile": ("photo.png", imageBytes, contentType)})


def error_code(response):
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_better_photo" and body["legibilityScore"] is None
    return body["error"]["code"]


def test_health():
    assert client.get("/api/health").json() == {"status": "ok", "schemaVersion": "2.1"}


def test_complete_result_without_corners():
    response = post(png_bytes(make_page_photo()))
    assert response.status_code == 200
    body = response.json()
    AnalysisResponse.model_validate(body)

    assert body["status"] == "complete"
    assert 0 <= body["legibilityScore"] <= 100 and body["scoreLabel"]
    assert body["rectifiedImage"].startswith("data:image/jpeg;base64,")
    assert any("whole photo" in warning for warning in body["warnings"])
    assert [check["checkId"] for check in body["qualityChecks"]] == \
        ["fileType", "fileSize", "decode", "imageSize", "inkAmount", "contrast", "blur", "segmentation"]

    overlay = body["overlayData"]
    assert {line["kind"] for line in overlay["lines"]} == {"baseline", "xHeight"}
    assert {gap["kind"] for gap in overlay["gaps"]} == {"letter", "word"}
    for box in overlay["components"] + overlay["gaps"]:
        assert 0 <= box["xPx"] and box["xPx"] + box["widthPx"] <= overlay["imageWidthPx"]
        assert 0 <= box["yPx"] and box["yPx"] + box["heightPx"] <= overlay["imageHeightPx"]


def test_corners_crop_a_page_on_a_background():
    # Put the page on a grey desk, shifted and slightly keystoned like a real photo
    page = make_page_photo()
    photo = np.full((1800, 1500, 3), 120, np.uint8)
    corners = np.float32([[260, 180], [1240, 220], [1280, 1620], [220, 1600]])
    transform = cv2.getPerspectiveTransform(np.float32([[0, 0], [999, 0], [999, 1413], [0, 1413]]), corners)
    photo = cv2.warpPerspective(page, transform, (1500, 1800), dst=photo, borderMode=cv2.BORDER_TRANSPARENT)

    body = post(png_bytes(photo), cornerPointsPx=json.dumps(corners.tolist())).json()
    assert body["status"] == "complete"
    assert {"checkId": "pageBounds", "passed": True, "message": None} in body["qualityChecks"]
    assert not any("whole photo" in warning for warning in body["warnings"])
    # Cropped to 1000 px wide; the page is slightly rotated, so deskew straightens it and enlarges the canvas a little
    assert 1000 <= body["overlayData"]["imageWidthPx"] <= 1100


def test_page_is_found_automatically_without_corners():
    page = make_page_photo(paperLevel=240)
    photo = np.full((1800, 1500, 3), 90, np.uint8)
    corners = np.float32([[260, 180], [1240, 220], [1280, 1620], [220, 1600]])
    transform = cv2.getPerspectiveTransform(np.float32([[0, 0], [999, 0], [999, 1413], [0, 1413]]), corners)
    photo = cv2.warpPerspective(page, transform, (1500, 1800), dst=photo, borderMode=cv2.BORDER_TRANSPARENT)

    body = post(png_bytes(photo)).json()                     # no cornerPointsPx sent
    assert body["status"] == "complete"
    assert {"checkId": "pageBounds", "passed": True, "message": None} in body["qualityChecks"]
    assert not any("whole photo" in warning for warning in body["warnings"])


def test_invalid_file_type():
    assert error_code(post(b"hello", contentType="text/plain")) == "INVALID_FILE_TYPE"


def test_file_that_is_not_an_image():
    assert error_code(post(b"definitely not a png")) == "IMAGE_DECODE_FAILED"


def test_image_too_small():
    assert error_code(post(png_bytes(np.full((300, 300, 3), 255, np.uint8)))) == "IMAGE_TOO_SMALL"


def test_blank_page_is_not_enough_writing():
    assert error_code(post(png_bytes(np.full((1414, 1000, 3), 255, np.uint8)))) == "NOT_ENOUGH_WRITING"


def test_blurry_photo():
    blurry = cv2.GaussianBlur(make_page_photo(), (0, 0), 4)       # about 0.8 mm of blur on A4
    assert error_code(post(png_bytes(blurry))) == "BLUR_TOO_HIGH"


def test_slightly_soft_photo_still_passes():
    soft = cv2.GaussianBlur(make_page_photo(), (0, 0), 1)         # normal phone-camera softness
    assert post(png_bytes(soft)).json()["status"] == "complete"


def test_faint_writing_is_low_contrast():
    assert error_code(post(png_bytes(make_page_photo(inkLevel=215, paperLevel=235)))) == "CONTRAST_TOO_LOW"


def test_light_pencil_still_passes():
    assert post(png_bytes(make_page_photo(inkLevel=150, paperLevel=230))).json()["status"] == "complete"


def test_file_too_large():
    assert error_code(post(b"0" * (MAX_UPLOAD_BYTES + 1))) == "FILE_TOO_LARGE"


def test_too_few_letters_is_segmentation_uncertain():
    page = np.full((1414, 1000, 3), 255, np.uint8)
    cv2.putText(page, "abc", (300, 600), cv2.FONT_HERSHEY_SIMPLEX, 5, (0, 0, 0), 12)   # plenty of ink, 3 letters
    response = post(png_bytes(page))
    assert error_code(response) == "SEGMENTATION_UNCERTAIN"
    # Well spaced but short (e.g. two big words on the drawing pad): ask for more writing, not for gaps
    assert response.json()["error"]["message"].startswith("We found only 3 separate letters")


def test_joined_letters_are_told_to_leave_gaps():
    page = np.full((1414, 1000, 3), 255, np.uint8)
    cv2.putText(page, "abc", (100, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 10)
    for row, text in enumerate(("mmmmmm", "nnnnnn", "uuuuuu")):                       # long joined runs
        cv2.putText(page, text, (100, 750 + 200 * row), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 10)
        cv2.line(page, (100, 755 + 200 * row), (850, 755 + 200 * row), (0, 0, 0), 10)   # joining stroke
    response = post(png_bytes(page))
    assert error_code(response) == "SEGMENTATION_UNCERTAIN"
    assert response.json()["error"]["message"].startswith("Some letters are joined together")


def test_corners_on_the_exact_photo_border_are_accepted():
    # What Inko sends for drawings (whole_page): the photo's own corners, on its very edge
    corners = json.dumps([[0, 0], [1000, 0], [1000, 1414], [0, 1414]])
    body = post(png_bytes(make_page_photo()), cornerPointsPx=corners).json()
    assert body["status"] == "complete"
    assert {"checkId": "pageBounds", "passed": True, "message": None} in body["qualityChecks"]
    assert body["featureMeasurements"]["textHeightCanvasRatio"] is not None


def test_corners_outside_the_photo():
    corners = json.dumps([[0, 0], [5000, 0], [5000, 5000], [0, 5000]])
    assert error_code(post(png_bytes(make_page_photo()), cornerPointsPx=corners)) == "PAGE_NOT_FOUND"


def test_failed_check_is_reported_after_the_checks_that_passed():
    body = post(png_bytes(np.full((300, 300, 3), 255, np.uint8))).json()
    AnalysisResponse.model_validate(body)
    assert [(check["checkId"], check["passed"]) for check in body["qualityChecks"]] == \
        [("fileType", True), ("fileSize", True), ("decode", True), ("imageSize", False)]


def test_bad_form_fields_are_http_422():
    assert post(png_bytes(make_page_photo()), cornerPointsPx="not json").status_code == 422
    assert post(png_bytes(make_page_photo()), cornerPointsPx="[[0, 0]]").status_code == 422
    assert client.post("/api/analyze", data={"pageWidthMm": "-5", "pageHeightMm": "297"},
                       files={"imageFile": ("p.png", png_bytes(make_page_photo()), "image/png")}).status_code == 422
    assert client.post("/api/analyze", data={"pageHeightMm": "nan"},
                       files={"imageFile": ("p.png", png_bytes(make_page_photo()), "image/png")}).status_code == 422


def test_physical_dimensions_only_change_warnings():
    image = png_bytes(make_page_photo())
    corners = json.dumps([[0, 0], [999, 0], [999, 1413], [0, 1413]])
    results = []
    for dimensions in ({}, {"pageHeightMm": "30"}, {"pageHeightMm": "1000"},
                       {"pageWidthMm": "20"}, {"pageWidthMm": "1000"}):
        response = client.post("/api/analyze", data={**dimensions, "cornerPointsPx": corners},
                               files={"imageFile": ("p.png", image, "image/png")})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "complete"
        results.append(body)
    assert not any("mm tall" in w for w in results[0]["warnings"])
    assert any("Below 2 mm" in w for w in results[1]["warnings"])
    assert any("Above 10 mm" in w for w in results[2]["warnings"])
    assert any("Below 2 mm" in w for w in results[3]["warnings"])
    assert any("Above 10 mm" in w for w in results[4]["warnings"])
    for body in results[1:]:
        for key in ("featureMeasurements", "featureScores", "legibilityScore", "rectifiedImage"):
            assert body[key] == results[0][key]


def test_missing_dimensions_are_accepted_without_corners():
    response = client.post("/api/analyze", files={
        "imageFile": ("p.png", png_bytes(make_page_photo()), "image/png")})
    assert response.status_code == 200
    assert response.json()["status"] == "complete"


def test_size_warning_thresholds_and_missing_bounds():
    from app.main import append_text_size_warning
    from app.schemas import AnalyzeRequestFields
    for height, expected in ((1.9, True), (2.0, False), (10.0, False), (10.1, True)):
        warnings = []
        append_text_size_warning({"textHeightCanvasRatio": height / 100},
                                 AnalyzeRequestFields(pageHeightMm=100), 1000, 700, True, warnings)
        assert bool(warnings) == expected
    warnings = []
    append_text_size_warning({"textHeightCanvasRatio": 0.001},
                             AnalyzeRequestFields(pageHeightMm=100), 1000, 700, False, warnings)
    assert warnings == []


def test_prepare_page_keeps_canvas_dimensions_before_deskew(monkeypatch):
    import app.main as main
    from app.schemas import AnalyzeRequestFields
    monkeypatch.setattr(main, "detect_page_corners", lambda image: None)
    monkeypatch.setattr(main, "deskew", lambda image: (np.pad(image, ((10, 10), (20, 20))), 2.0))
    page, height, width, bounds = main.prepare_page(
        make_page_photo(), AnalyzeRequestFields(), [], [])
    assert (height, width) == (1414, 1000)
    assert page.shape == (1434, 1040)
    assert bounds is False


def test_recognized_text_is_shown_but_never_changes_the_score(monkeypatch):
    baseline = post(png_bytes(make_page_photo())).json()        # conftest: OCR unavailable

    fakeResult = OcrResult(confidencePct=5.0, recognizedText="The quick brown fox\njumps over the lazy dog.",
                           detections=[([[0, 0], [400, 0], [400, 600], [0, 600]], "The quick", 0.05)])
    monkeypatch.setattr(mainModule, "read_handwriting", lambda grayscaleImage: fakeResult)
    body = post(png_bytes(make_page_photo())).json()
    AnalysisResponse.model_validate(body)

    assert body["recognizedText"] == "The quick brown fox\njumps over the lazy dog."
    # Even a terrible OCR confidence leaves every score, weight, mark and tip exactly as without OCR
    for field in ("legibilityScore", "scoreLabel", "featureScores", "featureWeights", "missingFeatureIds",
                  "featureMeasurements", "overlayData", "advice"):
        assert body[field] == baseline[field], field
    assert not any("Text recognition" in warning for warning in body["warnings"])


def test_api_still_works_when_ocr_is_unavailable():
    body = post(png_bytes(make_page_photo())).json()          # conftest makes OCR unavailable
    assert body["status"] == "complete" and body["legibilityScore"] is not None
    assert body["recognizedText"] is None
    assert "ocrReadability" not in body["featureScores"] and "ocrConfidencePct" not in body["featureMeasurements"]
    assert sum(1 for warning in body["warnings"] if "Text recognition" in warning) == 1


def test_drawing_scores_everything_except_letter_size():
    drawing = post(png_bytes(make_page_photo()), isDrawing="true").json()
    AnalysisResponse.model_validate(drawing)
    assert drawing["status"] == "complete"
    assert drawing["featureMeasurements"]["textHeightCanvasRatio"] is None and drawing["featureScores"]["textSize"] is None
    assert drawing["missingFeatureIds"] == ["textSize"]
    # A valid score from the other seven features, each weighted 1/7
    assert drawing["legibilityScore"] is not None and drawing["scoreLabel"]
    assert set(drawing["featureWeights"]) == set(drawing["featureScores"]) - {"textSize"}
    assert all(abs(weight - 1 / 7) < 1e-9 for weight in drawing["featureWeights"].values())
    expected = round(100 * sum(drawing["featureScores"][f] / 7 for f in drawing["featureWeights"]) + 1e-9)
    assert abs(drawing["legibilityScore"] - expected) <= 1
    # No page detection, so no page-edge check or "adjust the corners" warning; one clear note instead
    assert "pageBounds" not in [check["checkId"] for check in drawing["qualityChecks"]]
    assert not any("page edges" in warning for warning in drawing["warnings"])
    assert sum("isn't measured for on-screen writing" in warning for warning in drawing["warnings"]) == 1
    assert not any("left out of the score" in warning for warning in drawing["warnings"])
    # The other measurements are exactly what the same image gets as a photo of a page
    asPage = post(png_bytes(make_page_photo()), cornerPointsPx=json.dumps([[0, 0], [1000, 0], [1000, 1414], [0, 1414]])).json()
    assert asPage["featureMeasurements"]["textHeightCanvasRatio"] is not None
    for name, value in drawing["featureMeasurements"].items():
        if name != "textHeightCanvasRatio":
            assert value == asPage["featureMeasurements"][name], name


def test_canvas_ratio_is_null_without_page_edges():
    body = post(png_bytes(make_page_photo())).json()          # page fills the photo: no edges found
    assert body["featureMeasurements"]["textHeightCanvasRatio"] is None
    assert "textSize" in body["missingFeatureIds"]
    assert any("whole photo" in warning for warning in body["warnings"])
