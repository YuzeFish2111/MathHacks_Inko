"""Image processing: from a phone photo to a clean ink mask, text lines and letter candidates.

Order used by POST /api/analyze (main.py):
  decode -> find the page (detect_page_corners) -> crop to it (crop_page) -> grayscale
  -> lighting correction (normalize_illumination) -> straighten (deskew) -> ink mask (threshold_ink)
  -> remove specks (remove_small_components) -> lines (find_text_lines) -> letters (find_components)

Conventions:
  - Images are NumPy arrays. OpenCV stores colour as BGR (blue, green, red), not RGB.
  - inkMask: 255 = ink, 0 = paper.
  - Coordinates are pixels in the straightened page (rectifiedImage); x right, y DOWN.
"""
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from .scoring_config import (TARGET_IMAGE_WIDTH_PX, BACKGROUND_KERNEL_PX, BACKGROUND_SMOOTHING_PX,
                             BLUR_KERNEL_PX, THRESHOLD_BLOCK_SIZE_PX,
                             THRESHOLD_OFFSET_C, MIN_COMPONENT_AREA_PX,
                             LINE_MIN_INK_FRACTION, LINE_MERGE_GAP_PX, LINE_MIN_HEIGHT_PX,
                             NEAR_LINE_MAX_GAP_RATIO, MARK_MAX_HEIGHT_RATIO, CLUSTER_MIN_WIDTH_RATIO,
                             DESKEW_MAX_ANGLE_DEG, DESKEW_STEP_DEG,
                             PAGE_DETECT_MAX_SIDE_PX, PAGE_MIN_AREA_FRACTION, PAGE_MAX_AREA_FRACTION,
                             PAGE_MIN_BRIGHTNESS_GAIN)


@dataclass
#defines how a letter component is stored in the code
class LetterComponent:
    """One connected ink blob in rectifiedImage pixels. A candidate only; not guaranteed to be a letter."""
    componentId: str
    lineId: str
    xPx: int                 # left edge of the bounding box
    yPx: int                 # top edge of the bounding box
    widthPx: int
    heightPx: int
    areaPx: int              # number of ink pixels
    contour: np.ndarray      # outer outline from cv2.findContours; used for slant
    kind: str = "letter"     # "letter" | "mark" (dot, punctuation) | "cluster" (joined letters)


@dataclass
#defines how a text line is stored in the code
class TextLine:
    """One detected writing line; textLines are ordered top-to-bottom."""
    lineId: str
    topPx: int
    bottomPx: int
    components: list[LetterComponent] = field(default_factory=list)    # sorted left to right

#allows for heic type images (iphone default) to be decoded 
def decode_heic(imageBytes: bytes) -> np.ndarray:
    from io import BytesIO
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()

    #rotates it according to the orientation tag
    #convert to rgb
    with Image.open(BytesIO(imageBytes)) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)

def load_image(path: str) -> np.ndarray:
    from pathlib import Path

    return decode_image(Path(path).read_bytes())


def decode_image(imageBytes: bytes) -> np.ndarray:
    buffer = np.frombuffer(imageBytes, dtype=np.uint8)
    originalImage = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    # If OpenCV can't decode it (e.g. HEIC), try Pillow with the HEIF plugin

    if originalImage is None:
        try:
            originalImage = decode_heic(imageBytes)
        except Exception as error:
            raise ValueError("Could not decode image") from error

    return originalImage

#crops out the useless stuff outside the image
def crop_page(originalImage: np.ndarray, cornerPointsPx: list[tuple[float, float]],
              targetWidthPx: int = TARGET_IMAGE_WIDTH_PX) -> np.ndarray:
    """Cut the page out of the photo (rectifiedImage) WITHOUT reshaping it.

    cornerPointsPx are the page corners in originalImage pixels, ordered top-left, top-right,
    bottom-right, bottom-left. The photo is cropped to the rectangle around them and resized to
    targetWidthPx wide, keeping its proportions, so letters keep their true shape (an earlier
    perspective warp stretched them when the corners or the page proportions were off). Anything
    outside the corners (desk showing past a slightly rotated page) is painted the paper's colour,
    so the page edge isn't mistaken for ink; deskew later removes small rotations.
    Raises ValueError if the corners fall outside the photo or enclose no area.
    """
    imageHeightPx, imageWidthPx = originalImage.shape[:2]
    corners = np.array(cornerPointsPx, dtype=np.float32)
    if corners.shape != (4, 2):
        raise ValueError("cornerPointsPx must be four [x, y] points")
    if not np.isfinite(corners).all():
        raise ValueError("cornerPointsPx must be finite")
    if (corners < 0).any() or (corners[:, 0] > imageWidthPx).any() or (corners[:, 1] > imageHeightPx).any():
        raise ValueError("cornerPointsPx fall outside the photo")
    if not cv2.isContourConvex(corners) or cv2.contourArea(corners) < 1:
        raise ValueError("cornerPointsPx enclose no area")

    x0, y0 = (int(np.floor(v)) for v in corners.min(axis=0))
    x1 = min(imageWidthPx, int(np.ceil(corners[:, 0].max())))
    y1 = min(imageHeightPx, int(np.ceil(corners[:, 1].max())))
    pageImage = originalImage[y0:y1, x0:x1].copy()

    # Paint everything outside the page outline with the paper's median colour
    insidePage = np.zeros(pageImage.shape[:2], np.uint8)
    cv2.fillConvexPoly(insidePage, np.round(corners - [x0, y0]).astype(np.int32), 255)
    if (insidePage == 0).any():
        paperColour = np.median(pageImage[insidePage > 0], axis=0)
        pageImage[insidePage == 0] = paperColour.astype(pageImage.dtype)
    return resize_to_width(pageImage, targetWidthPx)


def _order_corners(points: np.ndarray) -> Optional[np.ndarray]:
    """Order four points top-left, top-right, bottom-right, bottom-left.

    Top-left has the smallest x + y and bottom-right the largest; top-right has the smallest
    y - x and bottom-left the largest. None if two roles land on the same point (page turned ~45 degrees).
    """
    pointSums = points.sum(axis=1)
    pointDiffs = points[:, 1] - points[:, 0]
    order = [np.argmin(pointSums), np.argmin(pointDiffs), np.argmax(pointSums), np.argmax(pointDiffs)]
    if len(set(int(index) for index in order)) < 4:
        return None
    return points[order].astype(np.float32)


def _quad_from_contour(contour: np.ndarray) -> Optional[np.ndarray]:
    """Simplify an outline to exactly four corners, or None.

    The convex hull removes dents (e.g. a thumb or a text line touching the edge); the polygon is then
    simplified with increasing tolerance (2-5% of its perimeter) until four corners remain.
    """
    hull = cv2.convexHull(contour)
    perimeterPx = cv2.arcLength(hull, True)
    for toleranceRatio in (0.02, 0.03, 0.04, 0.05):
        # Douglas-Peucker simplification: drops points that lie within the tolerance of a straight line
        polygon = cv2.approxPolyDP(hull, toleranceRatio * perimeterPx, True)
        if len(polygon) == 4:
            return polygon.reshape(4, 2).astype(np.float32)
    return None


def _candidate_page_masks(grayscaleImage: np.ndarray):
    """Two ways of outlining the page, tried in order.

    1. Brightness: paper is usually the brightest large area. Otsu picks the paper/background
       threshold; closing fills in the dark writing so the page is one solid blob.
    2. Edges: for a light desk, use Canny edges, thickened so small breaks in the border join up.
    """
    blurredImage = cv2.GaussianBlur(grayscaleImage, (5, 5), 0)

    # Otsu's method picks the brightness cut-off that best splits the pixels into two groups
    # (paper vs. background), so no fixed threshold is needed
    _, brightMask = cv2.threshold(blurredImage, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield cv2.morphologyEx(brightMask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

    medianLevel = float(np.median(blurredImage))
    # Canny edge thresholds set from the image's own median brightness (a common rule of thumb)
    edges = cv2.Canny(blurredImage, 0.66 * medianLevel, 1.33 * medianLevel)
    yield cv2.dilate(edges, np.ones((5, 5), np.uint8))

#checks if a region of the image looks like paper
def _looks_like_page(corners: np.ndarray, grayscaleImage: np.ndarray) -> bool:
    """Size, shape and brightness checks that reject desks, books and blocks of text."""
    imageAreaPx = grayscaleImage.shape[0] * grayscaleImage.shape[1]
    areaFraction = cv2.contourArea(corners) / imageAreaPx
    if not PAGE_MIN_AREA_FRACTION <= areaFraction <= PAGE_MAX_AREA_FRACTION:
        return False

    # Brightness: paper should be brighter than what surrounds it (a block of text is darker, not brighter)
    insideMask = np.zeros(grayscaleImage.shape, np.uint8)
    cv2.fillConvexPoly(insideMask, corners.astype(np.int32), 255)
    inside, outside = grayscaleImage[insideMask > 0], grayscaleImage[insideMask == 0]
    return outside.size > 0 and float(np.median(inside)) - float(np.median(outside)) >= PAGE_MIN_BRIGHTNESS_GAIN


def detect_page_corners(originalImage: np.ndarray) -> Optional[list[tuple[float, float]]]:
    """Find the page's four corners automatically (cornerPointsPx in originalImage pixels), or None.

    None means no convincing page was found, including when the page already fills the whole photo.
    """
    imageHeightPx, imageWidthPx = originalImage.shape[:2]
    shrinkFactor = min(1.0, PAGE_DETECT_MAX_SIDE_PX / max(imageHeightPx, imageWidthPx))
    smallImage = cv2.resize(originalImage, None, fx=shrinkFactor, fy=shrinkFactor, interpolation=cv2.INTER_AREA)
    smallGrayscale = to_grayscale(smallImage)

    #converts rgb to grayscale and resize to target width (1000)
    for pageMask in _candidate_page_masks(smallGrayscale):
        contours, _ = cv2.findContours(pageMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:    # biggest outlines first
            quad = _quad_from_contour(contour)
            corners = _order_corners(quad) if quad is not None else None
            if corners is not None and _looks_like_page(corners, smallGrayscale):
                return [(float(x), float(y)) for x, y in corners / shrinkFactor]
    return None


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

#blur the result
def estimate_background(grayscaleImage: np.ndarray) -> np.ndarray:
    """backgroundEstimate: how bright the bare paper is at every pixel.

    A closing (dilate, then erode) with a window wider than any pen stroke lets the surrounding
    paper grow over the dark ink, so only the lighting pattern is left. A small median blur then
    smooths paper texture; unlike a Gaussian blur it keeps hard shadow edges sharp, so the edge of a
    phone's or hand's shadow doesn't turn into a false line of ink.
    """
    window = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BACKGROUND_KERNEL_PX, BACKGROUND_KERNEL_PX))
    paperOnly = cv2.morphologyEx(grayscaleImage, cv2.MORPH_CLOSE, window)
    return cv2.medianBlur(paperOnly, BACKGROUND_SMOOTHING_PX)

#use the background estimate to normalize the image so that the paper is white and the ink is dark
def normalize_illumination(grayscaleImage: np.ndarray) -> np.ndarray:
    """normalizedImage: divide by backgroundEstimate so paper becomes white everywhere.

    Shadows and bright patches cancel out, and ink keeps its darkness relative to the paper
    around it. The background is kept at least 1 to avoid dividing by zero.
    """
    backgroundEstimate = np.maximum(estimate_background(grayscaleImage).astype(np.float32), 1)
    normalizedImage = grayscaleImage.astype(np.float32) / backgroundEstimate * 255
    return np.clip(normalizedImage, 0, 255).astype(np.uint8)


def threshold_ink(grayscaleImage: np.ndarray) -> np.ndarray:
    """Blur slightly, then adaptive-threshold into an ink mask (ink = 255, paper = 0).

    Adaptive thresholding compares each pixel with the (Gaussian-weighted) average of the
    THRESHOLD_BLOCK_SIZE_PX x THRESHOLD_BLOCK_SIZE_PX square around it: a pixel counts as ink if it is
    more than THRESHOLD_OFFSET_C darker than its neighbourhood. Unlike one global cut-off, this still
    works if some brightness variation is left after lighting correction.
    """
    blurredImage = cv2.GaussianBlur(grayscaleImage, (BLUR_KERNEL_PX, BLUR_KERNEL_PX), 0)
    return cv2.adaptiveThreshold(
        blurredImage,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,    # inverted so dark ink becomes the 255 foreground
        THRESHOLD_BLOCK_SIZE_PX,
        THRESHOLD_OFFSET_C,
    )
#removes small blobs of ink that are likely noise


def remove_small_components(inkMask: np.ndarray, minAreaPx: int = MIN_COMPONENT_AREA_PX) -> np.ndarray:
    """Drop connected ink components smaller than minAreaPx (isolated noise)."""
    # Connected components: every separate blob of touching ink pixels (diagonals count, so
    # connectivity=8) gets its own number in `labels`; componentStats holds each blob's box and area
    # separate groups of touching ink pixels
    _, labels, componentStats, _ = cv2.connectedComponentsWithStats(inkMask, connectivity=8)
    keep = componentStats[:, cv2.CC_STAT_AREA] >= minAreaPx    # one True/False per blob number
    keep[0] = False    # label 0 is the paper background
    #keeps labels of the minimum ink area
    # keep[labels] looks up every pixel's blob number in `keep`: a True/False image in one step, no loop
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
    # 
    imageFloat = grayscaleImage.astype(np.float32)
    # Sobel / 8 = brightness change per pixel (central difference, smoothed across 3 rows)
    gradientX = cv2.Sobel(imageFloat, cv2.CV_32F, 1, 0, ksize=3) / 8
    gradientY = cv2.Sobel(imageFloat, cv2.CV_32F, 0, 1, ksize=3) / 8
    gradientMagnitude = np.hypot(gradientX, gradientY)

    # Morphological gradient (grown mask minus shrunk mask) = a thin band on both sides of every stroke edge
    isEdge = cv2.morphologyEx(inkMask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    if not isEdge.any():
        return None
    return float(np.percentile(gradientMagnitude[isEdge], 90) / inkContrast)


def rotate_image(image: np.ndarray, angleDeg: float, borderMode: int = cv2.BORDER_CONSTANT,
                 borderValue: int = 0) -> np.ndarray:
    """Rotate counter-clockwise by angleDeg, enlarging the canvas so no corner is cut off.

    Rotation expands the image; retain the pre-rotation canvas dimensions for ratios.
    """
    heightPx, widthPx = image.shape[:2]
    center = (widthPx / 2, heightPx / 2)
    # 2x3 affine matrix [[cos, sin, shiftX], [-sin, cos, shiftY]]: rotates about the centre, then shifts
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
        # Projection profile: ink pixels per row. Tilted text smears ink across many rows (flat profile);
        # level text concentrates it in its rows (tall peaks, empty valleys), which gives a high variance
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
    """Full chain: grayscale -> resize -> lighting correction -> deskew -> threshold -> denoise.

    Returns (inkMask, deskewAngleDeg); inkMask has ink = 255, paper = 0.
    """
    normalizedImage = normalize_illumination(resize_to_width(to_grayscale(originalImage)))
    grayscaleImage, deskewAngleDeg = deskew(normalizedImage)
    return remove_small_components(threshold_ink(grayscaleImage)), deskewAngleDeg


def find_text_lines(inkMask: np.ndarray) -> list[TextLine]:
    """Find writing lines from the horizontal projection (ink pixels per row), top-to-bottom.

    Returned lines have no components yet; find_components fills them in.
    """
    rowInkCounts = (inkMask > 0).sum(axis=1)
    if rowInkCounts.max() == 0:
        return []

    # Same projection-profile idea as deskew: rows of writing hold lots of ink, gaps between lines hold none.
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

        # Vertical overlap with each line: (lower of the two bottoms) - (higher of the two tops) + 1.
        # Positive = rows shared with the line; negative = the gap to that line
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
