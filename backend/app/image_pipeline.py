from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from .scoring_config import (TARGET_IMAGE_WIDTH_PX, BLUR_KERNEL_PX, THRESHOLD_BLOCK_SIZE_PX,
                             THRESHOLD_OFFSET_C, MIN_COMPONENT_AREA_PX,
                             LINE_MIN_INK_FRACTION, LINE_MERGE_GAP_PX, LINE_MIN_HEIGHT_PX,
                             NEAR_LINE_MAX_GAP_RATIO, MARK_MAX_HEIGHT_RATIO, CLUSTER_MIN_WIDTH_RATIO,
                             DESKEW_MAX_ANGLE_DEG, DESKEW_STEP_DEG)


@dataclass
class LetterComponent:
    """One connected ink blob in rectifiedImage pixels. A candidate only; not guaranteed to be a letter."""
    componentId: str
    lineId: str
    xPx: int                 # left edge of the bounding box
    yPx: int                 # top edge of the bounding box
    widthPx: int
    heightPx: int
    areaPx: int              # number of ink pixels
    contour: np.ndarray      # outer outline from cv2.findContours; used for solidity and slant
    kind: str = "letter"     # "letter" | "mark" (dot, punctuation) | "cluster" (joined letters)


@dataclass
class TextLine:
    """One detected writing line; textLines are ordered top-to-bottom."""
    lineId: str
    topPx: int
    bottomPx: int
    components: list[LetterComponent] = field(default_factory=list)    # sorted left to right


def load_image(path: str) -> np.ndarray:
    """Read an image file from disk as a BGR array (originalImage)."""
    originalImage = cv2.imread(path, cv2.IMREAD_COLOR)
    if originalImage is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return originalImage


def decode_image(imageBytes: bytes) -> np.ndarray:
    """Decode uploaded file bytes as a BGR array (originalImage); used by POST /api/analyze."""
    buffer = np.frombuffer(imageBytes, dtype=np.uint8)
    originalImage = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if originalImage is None:
        raise ValueError("Could not decode image")
    return originalImage


def rectify_page(originalImage: np.ndarray, cornerPointsPx: list[tuple[float, float]],
                 pageWidthMm: float, pageHeightMm: float,
                 targetWidthPx: int = TARGET_IMAGE_WIDTH_PX) -> np.ndarray:
    """Perspective-correct the page so it fills a flat rectangle (rectifiedImage).

    cornerPointsPx are the page corners in originalImage pixels, ordered top-left, top-right,
    bottom-right, bottom-left. The output is targetWidthPx wide with the paper's real
    proportions, so scaleMmPerPxX/Y = pageWidthMm / width and pageHeightMm / height.
    Raises ValueError if the corners fall outside the photo or enclose no area.
    """
    imageHeightPx, imageWidthPx = originalImage.shape[:2]
    sourceCorners = np.array(cornerPointsPx, dtype=np.float32)
    if sourceCorners.shape != (4, 2):
        raise ValueError("cornerPointsPx must be four [x, y] points")
    if (sourceCorners < 0).any() or (sourceCorners[:, 0] > imageWidthPx).any() \
            or (sourceCorners[:, 1] > imageHeightPx).any():
        raise ValueError("cornerPointsPx fall outside the photo")
    if cv2.contourArea(sourceCorners) < 1:
        raise ValueError("cornerPointsPx enclose no area")

    targetHeightPx = max(1, round(targetWidthPx * pageHeightMm / pageWidthMm))
    targetCorners = np.array([[0, 0], [targetWidthPx - 1, 0],
                              [targetWidthPx - 1, targetHeightPx - 1], [0, targetHeightPx - 1]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(sourceCorners, targetCorners)
    return cv2.warpPerspective(originalImage, transform, (targetWidthPx, targetHeightPx),
                               flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)


def to_grayscale(originalImage: np.ndarray) -> np.ndarray:
    """Convert a BGR image to grayscale (grayscaleImage)."""
    return cv2.cvtColor(originalImage, cv2.COLOR_BGR2GRAY)


def resize_to_width(image: np.ndarray, targetWidthPx: int = TARGET_IMAGE_WIDTH_PX) -> np.ndarray:
    """Resize to a fixed width, keeping the aspect ratio. Must run before thresholding."""
    heightPx, widthPx = image.shape[:2]
    resizeFactor = targetWidthPx / widthPx
    targetHeightPx = max(1, round(heightPx * resizeFactor))
    # INTER_AREA is best for shrinking, INTER_LINEAR for enlarging
    interpolation = cv2.INTER_AREA if resizeFactor < 1 else cv2.INTER_LINEAR
    return cv2.resize(image, (targetWidthPx, targetHeightPx), interpolation=interpolation)


def threshold_ink(grayscaleImage: np.ndarray) -> np.ndarray:
    """Blur slightly, then adaptive-threshold into an ink mask (ink = 255, paper = 0)."""
    blurredImage = cv2.GaussianBlur(grayscaleImage, (BLUR_KERNEL_PX, BLUR_KERNEL_PX), 0)
    return cv2.adaptiveThreshold(
        blurredImage,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,    # inverted so dark ink becomes the 255 foreground
        THRESHOLD_BLOCK_SIZE_PX,
        THRESHOLD_OFFSET_C,
    )


def remove_small_components(inkMask: np.ndarray, minAreaPx: int = MIN_COMPONENT_AREA_PX) -> np.ndarray:
    """Drop connected ink components smaller than minAreaPx (isolated noise)."""
    _, labels, componentStats, _ = cv2.connectedComponentsWithStats(inkMask, connectivity=8)
    keep = componentStats[:, cv2.CC_STAT_AREA] >= minAreaPx
    keep[0] = False    # label 0 is the paper background
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def measure_ink_contrast(grayscaleImage: np.ndarray, inkMask: np.ndarray) -> Optional[float]:
    """Paper brightness minus ink darkness, 0-255 (median of each).

    Paper pixels are taken a few pixels away from any ink, so stroke edges don't count as paper.
    None if there is no ink or no paper to compare.
    """
    isInk = inkMask > 0
    isPaper = cv2.dilate(inkMask, np.ones((5, 5), np.uint8)) == 0
    if not isInk.any() or not isPaper.any():
        return None
    return float(np.median(grayscaleImage[isPaper]) - np.median(grayscaleImage[isInk]))


def measure_edge_sharpness(grayscaleImage: np.ndarray, inkMask: np.ndarray,
                           inkContrast: Optional[float]) -> Optional[float]:
    """How steep the ink edges are, relative to the ink contrast (about 0.5 = perfectly sharp).

    Takes the 90th percentile brightness gradient (per pixel) on the boundary of the ink mask,
    divided by inkContrast. Blur spreads each edge over more pixels, lowering the ratio; dividing
    by contrast means faint-but-sharp writing is not mistaken for blur.
    """
    if not inkContrast or inkContrast <= 0:
        return None
    imageFloat = grayscaleImage.astype(np.float32)
    # Sobel / 8 = brightness change per pixel (central difference, smoothed across 3 rows)
    gradientX = cv2.Sobel(imageFloat, cv2.CV_32F, 1, 0, ksize=3) / 8
    gradientY = cv2.Sobel(imageFloat, cv2.CV_32F, 0, 1, ksize=3) / 8
    gradientMagnitude = np.hypot(gradientX, gradientY)

    isEdge = cv2.morphologyEx(inkMask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    if not isEdge.any():
        return None
    return float(np.percentile(gradientMagnitude[isEdge], 90) / inkContrast)


def rotate_image(image: np.ndarray, angleDeg: float, borderMode: int = cv2.BORDER_CONSTANT,
                 borderValue: int = 0) -> np.ndarray:
    """Rotate counter-clockwise by angleDeg, enlarging the canvas so no corner is cut off.

    Rotation does not change mm-per-pixel, but it does change the image size, so compute
    scaleMmPerPxX/Y from the page size BEFORE rotating.
    """
    heightPx, widthPx = image.shape[:2]
    center = (widthPx / 2, heightPx / 2)
    rotationMatrix = cv2.getRotationMatrix2D(center, angleDeg, 1.0)

    # Size of the box that fits the whole rotated image
    cos = abs(rotationMatrix[0, 0])
    sin = abs(rotationMatrix[0, 1])
    # The small tolerance stops floating-point noise (cos 90 = 6e-17, not 0) adding an extra pixel
    newWidthPx = int(np.ceil(heightPx * sin + widthPx * cos - 1e-6))
    newHeightPx = int(np.ceil(heightPx * cos + widthPx * sin - 1e-6))

    # Shift so the rotated image is centred in the bigger canvas
    rotationMatrix[0, 2] += newWidthPx / 2 - center[0]
    rotationMatrix[1, 2] += newHeightPx / 2 - center[1]

    return cv2.warpAffine(image, rotationMatrix, (newWidthPx, newHeightPx), flags=cv2.INTER_LINEAR,
                          borderMode=borderMode, borderValue=borderValue)


def estimate_deskew_angle_deg(inkMask: np.ndarray) -> float:
    """Find the rotation (deskewAngleDeg) that makes text rows most horizontal.

    Tries each angle in +/- DESKEW_MAX_ANGLE_DEG and keeps the one where ink-per-row varies most:
    level lines give sharp peaks (text rows) and valleys (gaps between lines).
    Angles are tried smallest-first, so a tie (e.g. a blank page) keeps 0.
    """
    stepCount = int(round(DESKEW_MAX_ANGLE_DEG / DESKEW_STEP_DEG))
    candidateAnglesDeg = sorted((DESKEW_STEP_DEG * i for i in range(-stepCount, stepCount + 1)), key=abs)

    bestAngleDeg = 0.0
    bestScore = -1.0
    for angleDeg in candidateAnglesDeg:
        rowInkCounts = (rotate_image(inkMask, angleDeg) > 127).sum(axis=1)
        score = float(np.var(rowInkCounts))
        if score > bestScore:
            bestScore = score
            bestAngleDeg = angleDeg
    return bestAngleDeg


def deskew(grayscaleImage: np.ndarray) -> tuple[np.ndarray, float]:
    """Straighten the grayscale image. Returns (deskewed grayscale image, deskewAngleDeg)."""
    deskewAngleDeg = estimate_deskew_angle_deg(threshold_ink(grayscaleImage))
    if deskewAngleDeg == 0:
        return grayscaleImage, 0.0
    # Replicate edge pixels so the new corners look like paper, not a bright border
    # the adaptive threshold would mistake for an edge of ink
    return rotate_image(grayscaleImage, deskewAngleDeg, borderMode=cv2.BORDER_REPLICATE), deskewAngleDeg


def compute_ink_mask(originalImage: np.ndarray) -> tuple[np.ndarray, float]:
    """Full chain: grayscale -> resize -> deskew -> threshold -> denoise.

    Returns (inkMask, deskewAngleDeg); inkMask has ink = 255, paper = 0.
    """
    grayscaleImage, deskewAngleDeg = deskew(resize_to_width(to_grayscale(originalImage)))
    return remove_small_components(threshold_ink(grayscaleImage)), deskewAngleDeg


def find_text_lines(inkMask: np.ndarray) -> list[TextLine]:
    """Find writing lines from the horizontal projection (ink pixels per row), top-to-bottom.

    Returned lines have no components yet; find_components fills them in.
    """
    rowInkCounts = (inkMask > 0).sum(axis=1)
    if rowInkCounts.max() == 0:
        return []

    # Rows with enough ink count as text; group consecutive text rows into bands [top, bottom]
    isTextRow = rowInkCounts >= max(1, LINE_MIN_INK_FRACTION * rowInkCounts.max())
    bands = []
    for rowIndex in np.flatnonzero(isTextRow):
        if bands and rowIndex - bands[-1][1] <= LINE_MERGE_GAP_PX:
            bands[-1][1] = rowIndex          # close enough: extend the current band
        else:
            bands.append([rowIndex, rowIndex])

    tallBands = [(top, bottom) for top, bottom in bands if bottom - top + 1 >= LINE_MIN_HEIGHT_PX]
    return [TextLine(lineId=f"line-{lineNumber}", topPx=int(top), bottomPx=int(bottom))
            for lineNumber, (top, bottom) in enumerate(tallBands, start=1)]


def find_components(inkMask: np.ndarray, textLines: list[TextLine]) -> list[TextLine]:
    """Assign each connected ink blob to the line it overlaps most, and label it letter/mark/cluster.

    Fills textLines[i].components (sorted left to right) and returns textLines.
    A blob that overlaps no line (e.g. an i-dot whose rows were too faint to count as text)
    joins the nearest line if it is close enough; otherwise it is ignored.
    """
    if not textLines:
        return textLines
    count, labels, componentStats, _ = cv2.connectedComponentsWithStats(inkMask, connectivity=8)

    for label in range(1, count):    # label 0 is the paper background
        xPx, yPx, widthPx, heightPx, areaPx = (int(v) for v in componentStats[label])

        # Vertical overlap with each line; negative values are the gap to that line
        overlaps = [min(yPx + heightPx - 1, line.bottomPx) - max(yPx, line.topPx) + 1
                    for line in textLines]
        line = textLines[int(np.argmax(overlaps))]    # most overlap, or else the nearest line
        if max(overlaps) <= 0:
            gapPx = 1 - max(overlaps)
            if gapPx > NEAR_LINE_MAX_GAP_RATIO * (line.bottomPx - line.topPx + 1):
                continue

        # Outline of this blob only, shifted back to full-image coordinates
        blobMask = (labels[yPx:yPx + heightPx, xPx:xPx + widthPx] == label).astype(np.uint8)
        contours, _ = cv2.findContours(blobMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = max(contours, key=cv2.contourArea) + np.array([xPx, yPx], dtype=np.int32)    # keep int32 for OpenCV

        line.components.append(LetterComponent(
            componentId="", lineId=line.lineId, xPx=xPx, yPx=yPx,
            widthPx=widthPx, heightPx=heightPx, areaPx=areaPx, contour=contour))

    # Classify relative to each line's typical height, then number components in reading order
    componentNumber = 0
    for line in textLines:
        line.components.sort(key=lambda component: component.xPx)
        if not line.components:
            continue
        medianHeightPx = float(np.median([component.heightPx for component in line.components]))
        for component in line.components:
            if component.heightPx < MARK_MAX_HEIGHT_RATIO * medianHeightPx:
                component.kind = "mark"
            elif component.widthPx > CLUSTER_MIN_WIDTH_RATIO * medianHeightPx:
                component.kind = "cluster"
            componentNumber += 1
            component.componentId = f"component-{componentNumber}"

    return textLines
