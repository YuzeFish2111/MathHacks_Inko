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
from starlette.concurrency import run_in_threadpool

from .accuracy_evaluation import read_handwriting
from .advice import generate_advice
from .issues import find_component_issues, find_gap_issues
from .image_pipeline import (decode_image, detect_page_corners, crop_page, to_grayscale, resize_to_width,
                             normalize_illumination, deskew,
                             threshold_ink, remove_small_components, find_text_lines, find_components,
                             measure_ink_contrast, measure_edge_sharpness)
from .measurements import compute_feature_measurements, find_gaps, fit_baseline, measure_x_height_px
from .schemas import SCHEMA_VERSION, AnalysisResponse, AnalyzeRequestFields
from .scoring import score_measurements
from .scoring_config import (ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES, MIN_IMAGE_SIDE_PX, MIN_INK_FRACTION,
                             MIN_INK_CONTRAST, MIN_EDGE_SHARPNESS, MIN_LETTERS_FOR_ANALYSIS,
                             RECTIFIED_JPEG_QUALITY, MIN_TEXT_HEIGHT_MM, MAX_TEXT_HEIGHT_MM)

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
        "recognizedText": None,
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

def parse_request_fields(pageWidthMm: Optional[float], pageHeightMm: Optional[float],
                         cornerPointsPx: Optional[str], isDrawing: bool = False) -> AnalyzeRequestFields:
    """Validate the form fields. Bad fields are a bug in the caller, so they get HTTP 422, not needs_better_photo."""
    try:
        corners = json.loads(cornerPointsPx) if cornerPointsPx else None
        return AnalyzeRequestFields(pageWidthMm=pageWidthMm, pageHeightMm=pageHeightMm, cornerPointsPx=corners,
                                    isDrawing=isDrawing)
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


# ---------- 5. Page geometry: crop to the page (no reshaping) and straighten the writing ----------

def prepare_page(originalImage: np.ndarray, fields: AnalyzeRequestFields,
                 qualityChecks: list[dict], warnings: list[str]):
    """Return deskewed page, pre-deskew height/width, and whether page bounds were found.

    A drawing is used whole, with no page detection and no page bounds: a screen is not a sheet of paper,
    so letter size can't be judged against it.
    """
    if fields.isDrawing:
        grayscaleImage = resize_to_width(to_grayscale(originalImage))
        pageHeightPx, pageWidthPx = grayscaleImage.shape
        deskewedImage, _ = deskew(normalize_illumination(grayscaleImage))
        return deskewedImage, pageHeightPx, pageWidthPx, False

    cornerPointsPx = fields.cornerPointsPx
    if cornerPointsPx is None:
        cornerPointsPx = detect_page_corners(originalImage)

    if cornerPointsPx is not None:
        try:
            pageImage = crop_page(originalImage, cornerPointsPx)
        except ValueError:
            raise PhotoProblem("PAGE_NOT_FOUND", "pageBounds",
                               "The page corners don't fit the photo. Adjust the corners and try again.")
        qualityChecks.append(passed("pageBounds"))
        grayscaleImage = to_grayscale(pageImage)
    else:
        grayscaleImage = resize_to_width(to_grayscale(originalImage))
        warnings.append("The page edges weren't found, so the whole photo was treated as the page. "
                        "Canvas ratios may be inaccurate; adjust the corners. Physical size warnings were skipped.")

    pageHeightPx, pageWidthPx = grayscaleImage.shape

    # Correct uneven lighting before deskew, so shadows don't affect the angle search or the thresholds
    deskewedImage, _ = deskew(normalize_illumination(grayscaleImage))
    return deskewedImage, pageHeightPx, pageWidthPx, cornerPointsPx is not None


def append_text_size_warning(measurements: dict, fields: AnalyzeRequestFields,
                             canvasHeightPx: int, canvasWidthPx: int,
                             boundsKnown: bool, warnings: list[str]) -> None:
    """Optional approximate physical-size warnings, independent of feature scoring."""
    ratio = measurements["textHeightCanvasRatio"]
    if not boundsKnown or ratio is None:
        return
    # Prefer vertical calibration; width alone assumes square rectified pixels.
    heightMm = fields.pageHeightMm
    if heightMm is None and fields.pageWidthMm is not None:
        heightMm = fields.pageWidthMm * canvasHeightPx / canvasWidthPx
    if heightMm is None:
        return
    textHeightMm = ratio * heightMm
    if textHeightMm < MIN_TEXT_HEIGHT_MM:
        warnings.append(f"Your letters are approximately {textHeightMm:.1f} mm tall. "
                        f"Below {MIN_TEXT_HEIGHT_MM:g} mm, ordinary handwriting may be difficult to read.")
    elif textHeightMm > MAX_TEXT_HEIGHT_MM:
        warnings.append(f"Your letters are approximately {textHeightMm:.1f} mm tall. "
                        f"Above {MAX_TEXT_HEIGHT_MM:g} mm is unusually large for ordinary handwriting.")


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
        raise PhotoProblem("SEGMENTATION_UNCERTAIN", "segmentation", segmentation_message(textLines, letterCount))
    qualityChecks.append(passed("segmentation"))
    return inkMask, textLines


def segmentation_message(textLines, letterCount: int) -> str:
    """Why there are too few separate letters: joined letters, or simply too little writing.

    A cluster (joined letters) holds about (its width / a typical letter's width) letters. If counting
    those would reach MIN_LETTERS_FOR_ANALYSIS, the letters are there but touching; otherwise the
    writing is just too short (e.g. two big words on the drawing pad), however well it is spaced.
    """
    components = [component for line in textLines for component in line.components]
    letterWidthsPx = [c.widthPx for c in components if c.kind == "letter"] or \
                     [c.heightPx for c in components if c.kind != "mark"]
    typicalWidthPx = float(np.median(letterWidthsPx)) if letterWidthsPx else 0.0
    lettersInClusters = sum(max(2, round(c.widthPx / typicalWidthPx)) if typicalWidthPx > 0 else 2
                            for c in components if c.kind == "cluster")
    found = f"{letterCount} separate letter{'' if letterCount == 1 else 's'}"
    if letterCount + lettersInClusters >= MIN_LETTERS_FOR_ANALYSIS:
        return (f"Some letters are joined together, so we found only {found}. "
                "Try printing with small gaps between letters.")
    return (f"We found only {found}, and we need at least {MIN_LETTERS_FOR_ANALYSIS} to compare them. "
            "Write a little more, such as a full sentence.")


# ---------- 7. Overlays: what the browser draws on top of rectifiedImage ----------

def build_overlay_data(inkMask: np.ndarray, textLines, featureScores: dict) -> dict:
    """Baseline and x-height lines, component boxes and gap boxes, all in rectifiedImage pixels.

    Each box's issueFeatureIds lists the features it shows a problem with (see issues.py).
    """
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

    componentIssues = find_component_issues(textLines, xHeightPx, featureScores)
    components = [{"componentId": component.componentId, "lineId": line.lineId,
                   "xPx": component.xPx, "yPx": component.yPx,
                   "widthPx": component.widthPx, "heightPx": component.heightPx,
                   "issueFeatureIds": componentIssues[component.componentId]}
                  for line in textLines for component in line.components]

    gapList = find_gaps(textLines)
    gaps = [dict(gap, gapId=f"gap-{gapNumber}", issueFeatureIds=gapIssueIds)
            for gapNumber, (gap, gapIssueIds) in enumerate(zip(gapList, find_gap_issues(gapList, xHeightPx)), start=1)]

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
    pageWidthMm: Optional[float] = Form(None),
    pageHeightMm: Optional[float] = Form(None),
    cornerPointsPx: Optional[str] = Form(None),
    isDrawing: bool = Form(False),
) -> dict:
    """Photo in, legibility estimate out. Every step either passes a quality check or stops with a retry message.

    `async` lets the server keep handling other requests while this one waits for the upload to arrive.
    Flow: check the upload -> find and flatten the page -> ink, contrast, blur and segmentation checks
    -> 10 measurements -> 8 feature scores -> final score, overlays and tips.
    """
    fields = parse_request_fields(pageWidthMm, pageHeightMm, cornerPointsPx, isDrawing)
    qualityChecks: list[dict] = []
    warnings: list[str] = []

    try:
        originalImage = await read_and_check_upload(imageFile, qualityChecks)
        pageImage, canvasHeightPx, canvasWidthPx, boundsKnown = prepare_page(originalImage, fields, qualityChecks, warnings)
        inkMask, textLines = segment_writing(pageImage, qualityChecks)
    except PhotoProblem as problem:
        return needs_better_photo_response(problem, qualityChecks)

    # Without page edges the photo's own height isn't a page reference, so the canvas ratio is skipped
    featureMeasurements = compute_feature_measurements(inkMask, textLines,
                                                       canvasHeightPx if boundsKnown else None)
    append_text_size_warning(featureMeasurements, fields, canvasHeightPx, canvasWidthPx, boundsKnown, warnings)
    scoring = score_measurements(featureMeasurements)
    missingFeatureIds = scoring["missingFeatureIds"]
    if fields.isDrawing:
        warnings.append("Letter size isn't measured for on-screen writing: a screen isn't a page, so there's "
                        "nothing to compare the letter size with. The score uses the other features.")
        missingFeatureIds = [featureId for featureId in missingFeatureIds if featureId != "textSize"]
    if missingFeatureIds:
        warnings.append("Some features could not be measured and were left out of the score: "
                        + ", ".join(missingFeatureIds) + ".")

    # OCR is display only ("what a computer read"); it never affects the score. It takes a second or two
    # of CPU, so it runs in a worker thread instead of blocking the server for other requests.
    ocrResult = await run_in_threadpool(read_handwriting, pageImage)
    if ocrResult is None:
        warnings.append("Text recognition isn't available on this server, so \"what a computer read\" "
                        "can't be shown.")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "complete",
        "error": None,
        **scoring,
        "rectifiedImage": to_jpeg_data_url(pageImage),
        "recognizedText": ocrResult.recognizedText if ocrResult else None,
        "featureMeasurements": featureMeasurements,
        "warnings": warnings,
        "qualityChecks": qualityChecks,
        "overlayData": build_overlay_data(inkMask, textLines, scoring["featureScores"]),
        "advice": generate_advice(scoring["featureScores"], featureMeasurements),
    }
