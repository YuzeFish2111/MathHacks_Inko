"""FastAPI app and POST /api/analyze. See shared/analysis-contract.md for the request/response shape.

Run from the backend/ folder:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs to try the endpoint in the browser.
"""
import base64
import json
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .advice import generate_advice
from .image_pipeline import (decode_image, detect_page_corners, rectify_page, to_grayscale, resize_to_width, deskew,
                             threshold_ink, remove_small_components, find_text_lines, find_components,
                             measure_ink_contrast, measure_edge_sharpness)
from .measurements import compute_feature_measurements, find_gaps, fit_baseline, measure_x_height_px
from .schemas import SCHEMA_VERSION, AnalysisResponse, AnalyzeRequestFields
from .scoring import score_measurements
from .scoring_config import (ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES, MIN_IMAGE_SIDE_PX, MIN_INK_FRACTION,
                             MIN_INK_CONTRAST, MIN_EDGE_SHARPNESS, MIN_LETTERS_FOR_ANALYSIS,
                             RECTIFIED_JPEG_QUALITY)


# ---------- 1. App setup ----------

app = FastAPI(title="MathHacks Handwriting Legibility API", version=SCHEMA_VERSION)

# The React dev server runs on a different port, so the browser needs permission to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],    # Vite's default dev address
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ---------- 2. Response helpers ----------

class PhotoProblem(Exception):
    """Raised inside the pipeline when the photo can't be scored; becomes a needs_better_photo response."""

    def __init__(self, code: str, checkId: str, message: str):
        super().__init__(message)
        self.code = code
        self.checkId = checkId
        self.message = message


def needs_better_photo_response(problem: PhotoProblem, qualityChecks: list[dict]) -> dict:
    """A needs_better_photo response: the failed check is added, every score field is null."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "needs_better_photo",
        "error": {"code": problem.code, "message": problem.message},
        "legibilityScore": None,
        "scoreLabel": None,
        "rectifiedImage": None,
        "featureMeasurements": None,
        "featureScores": None,
        "featureWeights": None,
        "missingFeatureIds": [],
        "warnings": [],
        "qualityChecks": qualityChecks + [{"checkId": problem.checkId, "passed": False, "message": problem.message}],
        "overlayData": None,
        "advice": [],
    }


def passed(checkId: str) -> dict:
    return {"checkId": checkId, "passed": True, "message": None}


def to_jpeg_data_url(image: np.ndarray) -> str:
    """Encode an image as a data URL the browser can use directly as an <img> src."""
    ok, jpegBytes = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, RECTIFIED_JPEG_QUALITY])
    if not ok:
        raise RuntimeError("Could not encode rectifiedImage")
    return "data:image/jpeg;base64," + base64.b64encode(jpegBytes.tobytes()).decode("ascii")


# ---------- 3. Request parsing ----------

def parse_request_fields(pageWidthMm: float, pageHeightMm: float,
                         cornerPointsPx: Optional[str]) -> AnalyzeRequestFields:
    """Validate the form fields. Bad fields are a bug in the caller, so they get HTTP 422, not needs_better_photo."""
    try:
        corners = json.loads(cornerPointsPx) if cornerPointsPx else None
        return AnalyzeRequestFields(pageWidthMm=pageWidthMm, pageHeightMm=pageHeightMm, cornerPointsPx=corners)
    except (json.JSONDecodeError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=f"Invalid form fields: {error}")


# ---------- 4. Upload checks: fileType, fileSize, decode, imageSize ----------

async def read_and_check_upload(imageFile: UploadFile, qualityChecks: list[dict]) -> np.ndarray:
    """Return originalImage, or raise PhotoProblem. Each check that passes is appended to qualityChecks."""
    # Some browsers send no type or a generic one; let the decode check judge those
    if imageFile.content_type not in ALLOWED_IMAGE_TYPES + ("application/octet-stream", None, ""):
        raise PhotoProblem("INVALID_FILE_TYPE", "fileType", "Please upload a JPEG, PNG or WebP photo.")
    qualityChecks.append(passed("fileType"))

    imageBytes = await imageFile.read(MAX_UPLOAD_BYTES + 1)    # read one byte too many to detect oversize
    if len(imageBytes) > MAX_UPLOAD_BYTES:
        raise PhotoProblem("FILE_TOO_LARGE", "fileSize",
                           f"The photo is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Try a smaller image.")
    qualityChecks.append(passed("fileSize"))

    try:
        originalImage = decode_image(imageBytes)
    except ValueError:
        raise PhotoProblem("IMAGE_DECODE_FAILED", "decode",
                           "The file could not be opened as an image. Try taking the photo again.")
    qualityChecks.append(passed("decode"))

    if min(originalImage.shape[:2]) < MIN_IMAGE_SIDE_PX:
        raise PhotoProblem("IMAGE_TOO_SMALL", "imageSize",
                           f"The photo is too small. Use an image at least {MIN_IMAGE_SIDE_PX} pixels on each side.")
    qualityChecks.append(passed("imageSize"))
    return originalImage


# ---------- 5. Page geometry: straighten the page and work out mm per pixel ----------

def prepare_page(originalImage: np.ndarray, fields: AnalyzeRequestFields,
                 qualityChecks: list[dict], warnings: list[str]):
    """Return (deskewed grayscale page, scaleMmPerPxX, scaleMmPerPxY).

    Corners come from the user (cornerPointsPx) or, if none were sent, from automatic detection.
    With corners: perspective-correct the page, so the scale is exact.
    No corners found: assume the photo shows exactly the page (approximate; adds a warning).
    The scale is computed BEFORE deskew, because rotating enlarges the canvas but keeps mm per pixel.
    """
    cornerPointsPx = fields.cornerPointsPx
    if cornerPointsPx is None:
        cornerPointsPx = detect_page_corners(originalImage, fields.pageWidthMm, fields.pageHeightMm)

    if cornerPointsPx is not None:
        try:
            pageImage = rectify_page(originalImage, cornerPointsPx, fields.pageWidthMm, fields.pageHeightMm)
        except ValueError:
            raise PhotoProblem("PAGE_NOT_FOUND", "pageBounds",
                               "The page corners don't fit the photo. Adjust the corners and try again.")
        qualityChecks.append(passed("pageBounds"))
        grayscaleImage = to_grayscale(pageImage)
    else:
        grayscaleImage = resize_to_width(to_grayscale(originalImage))
        warnings.append("The page edges weren't found, so the whole photo was treated as the page. "
                        "Sizes in mm may be inaccurate; adjust the corners for an exact result.")

    pageHeightPx, pageWidthPx = grayscaleImage.shape
    scaleMmPerPxX = fields.pageWidthMm / pageWidthPx
    scaleMmPerPxY = fields.pageHeightMm / pageHeightPx

    deskewedImage, _ = deskew(grayscaleImage)
    return deskewedImage, scaleMmPerPxX, scaleMmPerPxY


# ---------- 6. Ink, contrast, blur and segmentation checks ----------

def segment_writing(grayscaleImage: np.ndarray, qualityChecks: list[dict]):
    """Return (inkMask, textLines), or raise PhotoProblem if the writing can't be measured reliably.

    Order: inkAmount -> contrast -> blur -> segmentation. Contrast and blur are measured on the ink
    that was found, so they run after inkAmount (a blank page should say "not enough writing").
    They are measured on the straightened page, so the desk around the page doesn't affect them.
    """
    inkMask = remove_small_components(threshold_ink(grayscaleImage))
    textLines = find_text_lines(inkMask)
    if (inkMask > 0).mean() < MIN_INK_FRACTION or not textLines:
        raise PhotoProblem("NOT_ENOUGH_WRITING", "inkAmount",
                           "We couldn't find enough writing. Write the full sentence and fill the frame with the page.")
    qualityChecks.append(passed("inkAmount"))

    inkContrast = measure_ink_contrast(grayscaleImage, inkMask)
    if inkContrast is None or inkContrast < MIN_INK_CONTRAST:
        raise PhotoProblem("CONTRAST_TOO_LOW", "contrast",
                           "The writing is too faint against the paper. Use a darker pen and take the photo "
                           "in brighter, even light.")
    qualityChecks.append(passed("contrast"))

    edgeSharpness = measure_edge_sharpness(grayscaleImage, inkMask, inkContrast)
    if edgeSharpness is None or edgeSharpness < MIN_EDGE_SHARPNESS:
        raise PhotoProblem("BLUR_TOO_HIGH", "blur",
                           "The photo looks blurry. Try holding your phone steady and retaking it.")
    qualityChecks.append(passed("blur"))

    find_components(inkMask, textLines)
    letterCount = sum(component.kind == "letter" for line in textLines for component in line.components)
    if letterCount < MIN_LETTERS_FOR_ANALYSIS:
        raise PhotoProblem("SEGMENTATION_UNCERTAIN", "segmentation",
                           "We couldn't separate the letters clearly. Try printing with small gaps between letters.")
    qualityChecks.append(passed("segmentation"))
    return inkMask, textLines


# ---------- 7. Overlays: what the browser draws on top of rectifiedImage ----------

def build_overlay_data(inkMask: np.ndarray, textLines) -> dict:
    """Baseline and x-height lines, component boxes and gap boxes, all in rectifiedImage pixels."""
    imageHeightPx, imageWidthPx = inkMask.shape
    xHeightPx = measure_x_height_px(inkMask, textLines)

    lines = []
    for line in textLines:
        baseline = fit_baseline(line)
        if baseline is None or not line.components:
            continue
        slope, intercept = baseline
        x1Px = min(component.xPx for component in line.components)
        x2Px = max(component.xPx + component.widthPx for component in line.components)
        y1Px, y2Px = slope * x1Px + intercept, slope * x2Px + intercept
        lines.append({"lineId": line.lineId, "kind": "baseline", "x1Px": x1Px, "y1Px": y1Px, "x2Px": x2Px, "y2Px": y2Px})
        if xHeightPx is not None:
            lines.append({"lineId": line.lineId, "kind": "xHeight",
                          "x1Px": x1Px, "y1Px": y1Px - xHeightPx, "x2Px": x2Px, "y2Px": y2Px - xHeightPx})

    components = [{"componentId": component.componentId, "lineId": line.lineId,
                   "xPx": component.xPx, "yPx": component.yPx,
                   "widthPx": component.widthPx, "heightPx": component.heightPx, "issueFeatureIds": []}
                  for line in textLines for component in line.components]

    gaps = [dict(gap, gapId=f"gap-{gapNumber}", issueFeatureIds=[])
            for gapNumber, gap in enumerate(find_gaps(textLines), start=1)]

    return {"coordinateSpace": "rectifiedImagePx", "imageWidthPx": imageWidthPx, "imageHeightPx": imageHeightPx,
            "lines": lines, "components": components, "gaps": gaps}


# ---------- 8. Endpoints ----------

@app.get("/api/health")
def health() -> dict:
    """Quick check that the server is running."""
    return {"status": "ok", "schemaVersion": SCHEMA_VERSION}


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(
    imageFile: UploadFile = File(...),
    pageWidthMm: float = Form(...),
    pageHeightMm: float = Form(...),
    cornerPointsPx: Optional[str] = Form(None),
) -> dict:
    """Photo in, legibility estimate out. Every step either passes a quality check or stops with a retry message."""
    fields = parse_request_fields(pageWidthMm, pageHeightMm, cornerPointsPx)
    qualityChecks: list[dict] = []
    warnings: list[str] = []

    try:
        originalImage = await read_and_check_upload(imageFile, qualityChecks)
        pageImage, scaleMmPerPxX, scaleMmPerPxY = prepare_page(originalImage, fields, qualityChecks, warnings)
        inkMask, textLines = segment_writing(pageImage, qualityChecks)
    except PhotoProblem as problem:
        return needs_better_photo_response(problem, qualityChecks)

    featureMeasurements = compute_feature_measurements(inkMask, textLines, scaleMmPerPxX, scaleMmPerPxY)
    scoring = score_measurements(featureMeasurements)
    if scoring["missingFeatureIds"]:
        warnings.append("Some features could not be measured and were left out of the score: "
                        + ", ".join(scoring["missingFeatureIds"]) + ".")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "complete",
        "error": None,
        **scoring,    # legibilityScore, scoreLabel, featureScores, featureWeights, missingFeatureIds
        "rectifiedImage": to_jpeg_data_url(pageImage),
        "featureMeasurements": featureMeasurements,
        "warnings": warnings,
        "qualityChecks": qualityChecks,
        "overlayData": build_overlay_data(inkMask, textLines),
        "advice": generate_advice(scoring["featureScores"], featureMeasurements),
    }
