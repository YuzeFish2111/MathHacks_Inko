FEATURE_IDS = ("textSize", "xHeight", "baselineConsistency", "shapeConsistency",
               "strokeContrast", "strokeWeight", "letterSpacing", "spacingConsistency")

# featureId -> source measurement(s); a feature with several sources is the mean of their available scores
FEATURE_SOURCES = {
    "textSize":            ("textSizeMm",),
    "xHeight":             ("xHeightMm",),
    "baselineConsistency": ("baselineVariationMm",),
    "shapeConsistency":    ("aspectRatioCv", "solidityCv", "slantStdDeg"),
    "strokeContrast":      ("strokeContrastRatio",),
    "strokeWeight":        ("strokeWidthMedianMm",),
    "letterSpacing":       ("relativeLetterSpacing",),
    "spacingConsistency":  ("letterSpacingCv",),
}

FEATURE_WEIGHTS = {featureId: 0.125 for featureId in FEATURE_IDS}   # replaced by regression later
# After regression: FEATURE_WEIGHTS = {"textSize": 0.09, "xHeight": 0.21, ...}

SWEET_SPOT_CURVES = {          # (a, b, c, d); placeholder values, not yet calibrated
    "textSizeMm":            (1.5, 3.0, 7.0, 12.0),
    "xHeightMm":             (1.0, 2.0, 4.5, 8.0),
    "strokeWidthMedianMm":   (0.1, 0.3, 0.8, 1.5),
    "relativeLetterSpacing": (0.0, 0.15, 0.6, 1.2),
}
DECREASING_CURVES = {          # (perfect value v0, zero-score value v1)
    "baselineVariationMm": (0.3, 2.5),
    "aspectRatioCv":       (0.1, 0.8),
    "solidityCv":          (0.05, 0.5),
    "slantStdDeg":         (2.0, 20.0),
    "strokeContrastRatio": (1.2, 4.0),
    "letterSpacingCv":     (0.15, 1.0),
}
SCORE_BANDS = ((85, "Very legible"), (70, "Readable"), (50, "Some difficulty"), (0, "Hard to read"))

# Advice (backend/app/advice.py)
MAX_ADVICE_ITEMS = 3            # at most this many tips, weakest feature first
ADVICE_MAX_FEATURE_SCORE = 0.9  # features scoring above this are good enough: no tip

# Upload and photo checks (backend/app/main.py)
ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024   # 15 MB; phone photos are usually 2-6 MB
MIN_IMAGE_SIDE_PX = 600         # shorter side of the uploaded photo must be at least this
MIN_INK_FRACTION = 0.0005       # less than this fraction of ink pixels -> NOT_ENOUGH_WRITING
MIN_INK_CONTRAST = 30           # paper minus ink brightness (0-255) below this -> CONTRAST_TOO_LOW
                                # (black pen ~200+, light pencil ~45, barely visible ~25); not yet tuned on real photos
MIN_EDGE_SHARPNESS = 0.2        # ink-edge steepness / contrast below this -> BLUR_TOO_HIGH
                                # (sharp ~0.5; 2 px blur ~0.25; 3 px blur ~0.18 at 1000 px width); not yet tuned
MIN_LETTERS_FOR_ANALYSIS = 10  # fewer clean letter components -> SEGMENTATION_UNCERTAIN (pangram has 35)
RECTIFIED_JPEG_QUALITY = 85     # quality of the rectifiedImage data URL sent back to the browser

# Automatic page detection (used when no cornerPointsPx are sent)
PAGE_DETECT_MAX_SIDE_PX = 800   # photo is shrunk to this long side for detection (speed); corners are scaled back
PAGE_MIN_AREA_FRACTION = 0.2    # the page must cover at least this fraction of the photo
PAGE_MAX_AREA_FRACTION = 0.97   # a "page" this big is just the photo's own border: the page fills the frame
PAGE_ASPECT_TOLERANCE = 0.35    # detected height/width may differ from the paper's by this fraction (perspective)
PAGE_MIN_BRIGHTNESS_GAIN = 15   # page must be this much brighter (0-255) than its surroundings

# Image pipeline (backend/app/image_pipeline.py)
TARGET_IMAGE_WIDTH_PX = 1000    # resize width, applied BEFORE thresholding
BLUR_KERNEL_PX = 3              # Gaussian blur kernel size; must be odd
THRESHOLD_BLOCK_SIZE_PX = 31    # adaptive threshold neighbourhood; must be odd and > 1
THRESHOLD_OFFSET_C = 10         # subtracted from the local mean; higher = less ink detected
MIN_COMPONENT_AREA_PX = 10       # ink blobs smaller than this are treated as noise

# Line and component segmentation (pixel values assume TARGET_IMAGE_WIDTH_PX)
LINE_MIN_INK_FRACTION = 0.05    # a row is "text" if its ink count is >= this fraction of the busiest row
LINE_MERGE_GAP_PX = 6           # text bands closer than this are merged (e.g. i-dots onto their line)
LINE_MIN_HEIGHT_PX = 8          # merged bands shorter than this are not treated as lines
NEAR_LINE_MAX_GAP_RATIO = 0.5   # blob outside every line joins the nearest one if within this x line height
MARK_MAX_HEIGHT_RATIO = 0.4    # component shorter than this x line's median height -> "mark"
CLUSTER_MIN_WIDTH_RATIO = 2.0   # component wider than this x line's median height -> "cluster"

# Deskew (rotation correction)
DESKEW_MAX_ANGLE_DEG = 15.0     # only angles in [-max, +max] are tried
DESKEW_STEP_DEG = 0.5           # spacing between tried angles

# Measurements (backend/app/measurements.py)
MIN_COMPONENTS_FOR_STATS = 5    # fewer letter components than this -> measurement is null
MIN_GAPS_FOR_STATS = 4          # fewer within-word letter gaps than this -> spacing measurements are null
MIN_LETTERS_FOR_BASELINE = 3    # a line needs this many letters to fit its baseline
X_HEIGHT_ROW_FRACTION = 0.5     # rows with >= this fraction of a line's peak ink form the x-height band
WORD_GAP_MIN_RATIO = 2.5        # gap wider than this x the line's median gap -> word gap, not letter gap