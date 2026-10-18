# Backend: MathHacks Handwriting Legibility API

A Python service that takes a photo of handwriting and returns an **experimental legibility estimate**:
a 0-100 score, eight interpretable feature scores, overlay coordinates for the browser to draw, and up
to three practice tips. Built with FastAPI, OpenCV, NumPy and SciPy.

The score isn't validated against human ratings yet (see [Validation](#10-validation-not-yet-run)), so
present it as an estimate.

Contract version: **2.1**. Tests: **105**, all passing (on synthetic images).

**Contents**
1. [Quick start](#1-quick-start)
2. [Folder layout](#2-folder-layout)
3. [The API](#3-the-api)
4. [How a request flows](#4-how-a-request-flows)
5. [Module reference](#5-module-reference)
6. [Configuration](#6-configuration-scoring_configpy)
7. [The scoring model](#7-the-scoring-model)
8. [Conventions](#8-conventions)
9. [Testing](#9-testing)
10. [Validation](#10-validation-not-yet-run)
11. [Common tasks](#11-common-tasks)
12. [Troubleshooting](#12-troubleshooting)
13. [Known limitations](#13-known-limitations)

---

## 1. Quick start

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- http://127.0.0.1:8000/api/health should return `{"status":"ok","schemaVersion":"2.1"}`
- http://127.0.0.1:8000/docs gives interactive docs: upload a photo and see the real response.

Run the tests (from `backend/`):

```bash
python3 -m pytest
```

**Requirements:** Python 3.10 or newer (developed on 3.14). Packages in `requirements.txt`:

| Package | Used for |
|---|---|
| `numpy`, `scipy` | arrays, statistics (Theil-Sen fit) |
| `opencv-python-headless` | all image processing |
| `fastapi`, `python-multipart`, `uvicorn` | the web API and file uploads |
| `pydantic` | response validation (the contract) |
| `easyocr` | text recognition for `recognizedText` (display only; optional at runtime) |
| `pillow`, `pillow-heif` | opening iPhone HEIC photos in the standalone OCR command |
| `matplotlib` | the developer preview script only |
| `pytest`, `httpx` | tests |

`easyocr` pulls in PyTorch (a large download). The API works without it: `recognizedText` is then `null`.

---

## 2. Folder layout

```
backend/
├── requirements.txt
├── app/                      the API (one request flows main -> pipeline -> measurements -> scoring)
│   ├── main.py               FastAPI app, endpoints, quality checks, overlay building
│   ├── image_pipeline.py     page detection, cropping, lighting, deskew, ink mask, lines, letters
│   ├── measurements.py       the 9 raw measurements, height groups
│   ├── scoring.py            curves -> feature scores -> legibilityScore -> label
│   ├── scoring_config.py     every tunable number (thresholds, curves, weights, bands)
│   ├── advice.py             up to 3 tips, weakest feature first
│   ├── issues.py             issueFeatureIds: which overlay boxes show a problem
│   ├── schemas.py            Pydantic models = the response contract
│   ├── accuracy_evaluation.py  EasyOCR text recognition (display only)
│   └── __init__.py           marks app/ as a package (empty on purpose)
├── scripts/
│   └── preview_ink_mask.py   shows a photo next to its ink mask (needs matplotlib)
└── tests/                    105 tests; conftest.py keeps the real OCR model out of tests
```

The shared contract lives outside this folder: `shared/analysis-contract.md` (names, units, error codes)
and `shared/fixtures/*.json` (example responses). `frontend/src/types/analysis.ts` mirrors `schemas.py`.

---

## 3. The API

### `GET /api/health`
Returns `{"status": "ok", "schemaVersion": "2.1"}`.

### `POST /api/analyze` (multipart/form-data)

| Field | Required | Type | Notes |
|---|---|---|---|
| `imageFile` | yes | file | JPEG, PNG or WebP, at most 15 MB, shorter side at least 600 px |
| `pageWidthMm` | no | positive finite number | canvas width for physical size warnings only |
| `pageHeightMm` | no | positive finite number | canvas height for physical size warnings only |
| `cornerPointsPx` | no | JSON string | `[[x,y],[x,y],[x,y],[x,y]]` in the uploaded photo's pixels, order top-left, top-right, bottom-right, bottom-left. If omitted, the page is found automatically |

Example:

```bash
curl -F imageFile=@photo.jpg -F pageWidthMm=210 -F pageHeightMm=297 http://127.0.0.1:8000/api/analyze
```

### Three kinds of outcome

| Outcome | HTTP | When | What the client should do |
|---|---|---|---|
| `status: "complete"` | 200 | the photo was analysed | show the results |
| `status: "needs_better_photo"` | 200 | the photo can't be scored reliably | show `error.message` and ask for a new photo |
| validation error | 422 | a form field is missing or invalid (e.g. negative paper size, malformed corners) | this is a client bug, not the user's photo |

### Response fields

| Field | Type | Meaning |
|---|---|---|
| `schemaVersion` | `"2.1"` | contract version |
| `status` | `"complete"` / `"needs_better_photo"` | |
| `error` | `{code, message}` or null | set only for `needs_better_photo` |
| `legibilityScore` | integer 0-100 or null | the final estimate |
| `scoreLabel` | string or null | "Very legible", "Readable", "Some difficulty", "Hard to read" |
| `rectifiedImage` | JPEG data URL or null | the straightened, lighting-corrected page all overlays refer to |
| `recognizedText` | string or null | what the OCR model read; **display only, never scored** |
| `featureMeasurements` | object or null | the 9 raw measurements (each may be null) |
| `featureScores` | object or null | the 8 feature scores, 0-1 (each may be null) |
| `featureWeights` | object or null | weights actually used (only for available features; they sum to 1) |
| `missingFeatureIds` | list | features that couldn't be measured |
| `warnings` | list of strings | non-fatal notes (see below) |
| `qualityChecks` | list of `{checkId, passed, message}` | every check that ran, in order |
| `overlayData` | object or null | lines, letter boxes and gap boxes (see below) |
| `advice` | list (at most 3) of `{featureId, title, message, exercise}` | |

`overlayData`: `coordinateSpace` (always `"rectifiedImagePx"`), `imageWidthPx`, `imageHeightPx`, and:
- `lines`: `{lineId, kind: "baseline" | "xHeight", x1Px, y1Px, x2Px, y2Px}`
- `components`: `{componentId, lineId, xPx, yPx, widthPx, heightPx, issueFeatureIds}` (one per letter candidate)
- `gaps`: `{gapId, lineId, kind: "letter" | "word", xPx, yPx, widthPx, heightPx, issueFeatureIds}`

Warnings the API can add:
- the page edges weren't found, so the whole photo was used (mm sizes may be inaccurate);
- some features couldn't be measured and were left out of the score;
- text recognition isn't available, so `recognizedText` can't be shown.

### Quality checks and error codes (in the order they run)

| # | `checkId` | Fails when | `error.code` |
|---|---|---|---|
| 1 | `fileType` | not JPEG / PNG / WebP (a missing or generic type is passed on to `decode`) | `INVALID_FILE_TYPE` |
| 2 | `fileSize` | over 15 MB | `FILE_TOO_LARGE` |
| 3 | `decode` | the bytes aren't a readable image | `IMAGE_DECODE_FAILED` |
| 4 | `imageSize` | shorter side under 600 px | `IMAGE_TOO_SMALL` |
| 5 | `pageBounds` | corners were given (or detected) but fall outside the photo or enclose no area | `PAGE_NOT_FOUND` |
| 6 | `inkAmount` | less than 0.05% of pixels are ink, or no text line is found | `NOT_ENOUGH_WRITING` |
| 7 | `contrast` | paper minus ink brightness below 30 (out of 255) | `CONTRAST_TOO_LOW` |
| 8 | `blur` | edge sharpness below 0.2 | `BLUR_TOO_HIGH` |
| 9 | `segmentation` | fewer than 10 clean letters | `SEGMENTATION_UNCERTAIN` |

`pageBounds` only appears when corners were used. Contrast and blur run *after* the ink check so a blank
page reports "not enough writing" rather than "too faint".

---

## 4. How a request flows

`analyze()` in `main.py` is the table of contents. Each step either passes a quality check or raises
`PhotoProblem`, which becomes a `needs_better_photo` response.

```
parse_request_fields          form fields -> AnalyzeRequestFields (HTTP 422 if invalid)
read_and_check_upload         checks 1-4 -> originalImage (BGR array)
prepare_page
  detect_page_corners         (only if no cornerPointsPx were sent)
  crop_page                   crop to the page corners, 1000 px wide, no warping       [check 5]
    or resize_to_width        fallback: whole photo as the page, plus a warning
  scale = paper mm / page px  computed BEFORE rotation (rotation keeps mm per pixel)
  normalize_illumination      remove shadows and lighting gradients
  deskew                      straighten up to +/- 15 degrees
segment_writing
  threshold_ink + remove_small_components -> inkMask
  find_text_lines                                                                     [check 6]
  measure_ink_contrast, measure_edge_sharpness                                        [checks 7, 8]
  find_components             letters / marks / clusters                              [check 9]
compute_feature_measurements  the 9 raw measurements
score_measurements            feature scores, weights, legibilityScore, label
read_handwriting              OCR in a worker thread -> recognizedText (display only)
build_overlay_data            lines, boxes, issueFeatureIds
generate_advice               up to 3 tips
-> AnalysisResponse           validated by FastAPI against schemas.py before it's sent
```

---

## 5. Module reference

### `main.py`: the web layer

| Section | Contents |
|---|---|
| 1. App setup | `FastAPI` app; CORS allows the Vite dev server (`localhost:5173`) |
| 2. Response helpers | `PhotoProblem` (code, checkId, message); `needs_better_photo_response()`; `passed(checkId)`; `to_jpeg_data_url()` (quality 85) |
| 3. Request parsing | `parse_request_fields()`: parses the corner JSON and validates with `AnalyzeRequestFields`; HTTP 422 on failure |
| 4. Upload checks | `read_and_check_upload()`: checks 1-4; reads at most 15 MB + 1 byte to detect oversize |
| 5. Page geometry | `prepare_page()`: user corners, else detected corners, else the whole photo; returns the deskewed page and mm-per-pixel scales |
| 6. Ink / contrast / blur / segmentation | `segment_writing()`: checks 6-9; returns `(inkMask, textLines)` |
| 7. Overlays | `build_overlay_data()`: baselines from `fit_baseline`, x-height lines, component and gap boxes with issue marks |
| 8. Endpoints | `health()`, `analyze()` |

OCR runs with `run_in_threadpool` so a 1-2 second recognition doesn't block other requests.

### `image_pipeline.py`: computer vision

Data classes:
- `LetterComponent`: `componentId`, `lineId`, box (`xPx`, `yPx`, `widthPx`, `heightPx`), `areaPx`, `contour`,
  `kind` (`"letter"` | `"mark"` | `"cluster"`). A *candidate*; not guaranteed to be one letter.
- `TextLine`: `lineId`, `topPx`, `bottomPx`, `components` (sorted left to right).

| Function | What it does | Method |
|---|---|---|
| `load_image(path)` / `decode_image(bytes)` | read a file / an upload as BGR | OpenCV; applies the photo's orientation tag |
| `detect_page_corners(image)` | find the page's 4 corners, or None | works on a copy shrunk to 800 px; tries a brightness mask (Otsu threshold + closing) then an edge mask (Canny + dilation); convex hull; Douglas-Peucker to 4 corners; accepts if 20-97% of the photo, and at least 15 brighter than the surroundings |
| `_order_corners` | order TL, TR, BR, BL | TL = min(x+y), BR = max(x+y), TR = min(y-x), BL = max(y-x) |
| `crop_page(image, corners)` | cut the page out | crops to the rectangle around the 4 corners and resizes to 1000 px wide keeping proportions; no perspective warp (it distorted letters), so strong camera angles stay foreshortened; desk outside the outline is painted paper-coloured; ValueError if corners are outside the photo or enclose no area |
| `to_grayscale`, `resize_to_width` | | `INTER_AREA` when shrinking, `INTER_LINEAR` when enlarging |
| `estimate_background` | `backgroundEstimate`: bare-paper brightness everywhere | closing with a 31 px ellipse (removes ink), then a 5 px median blur (keeps hard shadow edges) |
| `normalize_illumination` | `normalizedImage` | image / background x 255 (lighting model I = R x L) |
| `threshold_ink` | `inkMask` (ink 255) | 3 px Gaussian blur, then adaptive Gaussian threshold: 31 px block, offset C = 10 |
| `remove_small_components` | drop specks under 10 px | 8-connected components; `keep[labels]` lookup |
| `measure_ink_contrast` | paper minus ink brightness | medians; paper sampled at least 2 px from ink |
| `measure_edge_sharpness` | blur measure (~0.5 = sharp) | 90th percentile of Sobel gradient / 8 on the stroke-edge band, divided by contrast (~0.4/sigma for Gaussian blur) |
| `rotate_image` | rotate, enlarging the canvas | 2x3 affine matrix |
| `estimate_deskew_angle_deg` | best angle in +/- 15 degrees, 0.5 degree steps | maximises the variance of ink per row; smallest angle wins ties |
| `deskew` | rotate the page | edges replicated so new corners look like paper |
| `compute_ink_mask` | convenience chain for scripts | grayscale -> resize -> lighting -> deskew -> threshold -> clean |
| `find_text_lines` | lines, top to bottom | rows with at least 5% of the busiest row's ink; bands within 6 px merged; bands under 8 px dropped |
| `find_components` | fill lines with labelled blobs | each blob joins the line it overlaps most (or the nearest within half a line height); mark if < 0.4x the line's median height; cluster if wider than 2x it |

### `measurements.py`: the 8 measurements

All measured in pixels and converted to mm at the end. Too few letters (< 5) or gaps (< 4) gives `null`.
Only `kind == "letter"` components are used for size and shape.

| Measurement | Unit | Method |
|---|---|---|
| `textHeightCanvasRatio` | ratio | median letter height / canvas height before deskew; null when the page edges weren't found |
| `xHeightAscenderRatio` | ratio | median x-height-letter height / median ascender height (height groups, below) |
| `baselineVariationRatio` | ratio | robust spread (1.4826 x MAD) of non-descender letters around the fitted baseline / lowercase body height |
| `slantStdDeg` | degrees | `letter_slant_deg` = atan(mu11 / mu02) from image moments; standard deviation over letters |
| `letterHeightCv` | ratio | each letter's height / its height group's median, pooled over x-height letters and ascenders; standard deviation |
| `strokeContrastRatio` | ratio | 90th / 10th percentile of stroke widths |
| `strokeWidthRatio` | ratio | median stroke width / lowercase body height |
| `relativeLetterSpacing` | x x-height | median letter gap / x-height |
| `letterSpacingCv` | ratio | coefficient of variation (std / mean) of letter gaps |

**Height groups (`classify_height_groups`).** Letters are only compared with letters of the same height.
Per line, the letters' own heights are sorted and split at the natural break (the biggest jump, at
least 15%, with at least 20% of the letters below it): letters below the break are x-height letters,
and their median height is the line's small-letter reference. Above the break, a letter whose top
rises at least 1.20 x that reference above the baseline is an ascender (otherwise excluded). A tail
more than 0.25 below the baseline with the top still at least 0.75 high is a descender (a letter whose
top AND bottom are low has sunk, so it isn't excused as a descender). This works however many tall
letters a sentence has; with no clear break, letters with tops up to 1.12 x the median are x-height letters.
`xHeightAscenderRatio`, `letterHeightCv` and `baselineVariationRatio` use these groups.

`find_gaps()` lists every gap between neighbouring non-mark components and labels it `"word"` if wider
than 2.5x the line's median gap, else `"letter"`. It feeds both the spacing measurements and the overlays.
`compute_feature_measurements(inkMask, textLines, scaleX, scaleY)` returns all 8; mm values are `null`
when the scale is unknown.

### `scoring.py`: the model

| Function | What it does |
|---|---|
| `sweet_spot_score(value, a, b, c, d)` | trapezoid: 0 outside (a, d), rises a->b, 1 on [b, c], falls c->d |
| `decreasing_score(value, v0, v1)` | 1 at or below v0, linear to 0 at v1 |
| `score_measurement(name, value)` | picks the curve configured for that measurement |
| `compute_feature_scores(measurements)` | all 8 features; each is the mean of its available sources (currently one each) |
| `compute_legibility_score(featureScores)` | weighted mean over available features, rescaled; returns score, weights used, missing list |
| `score_label(score)` | first band whose minimum is reached |
| `score_measurements(measurements)` | everything above, under the contract's field names |

`None`, NaN and infinity count as missing.

### `issues.py`: problem marks on the overlays

`find_component_issues(textLines, xHeightPx, featureScores)` and `find_gap_issues(gaps, xHeightPx)`:

| Mark | On | Rule (distances in x-heights) |
|---|---|---|
| `baselineConsistency` | letter | bottom more than 0.25 above the fitted baseline (floating), or bottom AND top both more than 0.25 low (sunken; a descender's top stays level, so g/p/y aren't marked) |
| `shapeConsistency` | letter | slant differs from the median letter's by more than 25 degrees |
| `spacingConsistency` | gap | differs from the median letter gap by more than 0.25 |
| `letterSpacing` | gap | outside the ideal range 0.15-0.6 |
| `letterSpacing` | cluster | letters joined with no gap |
| `textSize`, `xHeight`, `strokeContrast`, `strokeWeight` | every letter | that page-wide feature scored 0.9 or below |

Word gaps are never marked. Marks are listed in `FEATURE_IDS` order.

### `advice.py`: tips

`generate_advice(featureScores, featureMeasurements)` picks features scoring 0.9 or below, weakest first
(ties keep `FEATURE_IDS` order), at most 3. `build_advice_item()` chooses the direction (sweet-spot
measurements below the ideal range are `"low"`, otherwise `"high"`) and fills a template from
`ADVICE_TEMPLATES` with the measured value (and the ideal range for sweet-spot measurements).
`DISPLAY_FORMATS` sets how each value is printed (e.g. CVs as percentages).

### `issues` vs `advice`
Advice explains *what* to change; issue marks show *where* on the image.

### `schemas.py`: the contract

Pydantic models: `AnalyzeRequestFields`, `AnalysisResponse` and its parts (`AnalysisError`, `QualityCheck`,
`FeatureMeasurements`, `FeatureScores`, `OverlayLine`, `OverlayComponent`, `OverlayGap`, `OverlayData`,
`AdviceItem`).
- `Literal[...]` types restrict IDs and codes to the contract's lists.
- `extra="forbid"` rejects unknown fields, so a misspelling fails instead of being dropped.
- Ranges: feature scores 0-1, `legibilityScore` 0-100 (integer), at most 3 advice items.
- A validator rejects contradictions: `complete` with an error, or `needs_better_photo` without one or with a score.

FastAPI validates every response against `AnalysisResponse` before sending it.

### `accuracy_evaluation.py`: OCR (display only)

| Name | What it does |
|---|---|
| `load_reader()` | creates an `easyocr.Reader` (CPU) |
| `get_reader()` | the shared reader, loaded on first use; a failed load is remembered (no retry until restart); None if disabled |
| `read_handwriting(gray)` | returns `OcrResult(confidencePct, recognizedText, detections)` or None; one recognition at a time (lock) |
| `measure_handwriting_legibility(gray, reader)` | the teammate's function: joins detected text; character-weighted mean confidence |
| `load_photo(path)`, `main(path)` | standalone command: `python -m app.accuracy_evaluation <image>` (supports HEIC) |

The API only uses `recognizedText`. OCR confidence is **not** scored: it isn't a calibrated probability,
and a model can guess the famous pangram even from messy writing.

### `scripts/preview_ink_mask.py`
`python -m scripts.preview_ink_mask <image>` prints mask statistics and plots the original,
thresholded and cleaned images side by side. It skips page detection and lighting correction.

---

## 6. Configuration (`scoring_config.py`)

Every tunable number lives here; nothing is hard-coded elsewhere. Pixel values assume the page is
1000 px wide (`TARGET_IMAGE_WIDTH_PX`). Values are first guesses unless noted; tune them on real photos.

| Group | Settings |
|---|---|
| Features | `FEATURE_IDS` (8), `FEATURE_SOURCES` (feature -> measurement), `FEATURE_WEIGHTS` (1/8 each) |
| Curves | `SWEET_SPOT_CURVES`, `DECREASING_CURVES` (values in section 7) |
| Labels | `SCORE_BANDS`: 85 / 70 / 50 / 0 |
| Advice | `MAX_ADVICE_ITEMS` = 3, `ADVICE_MAX_FEATURE_SCORE` = 0.9 |
| Issue marks | `ISSUE_MAX_FEATURE_SCORE` = 0.9, `ISSUE_BASELINE_OFFSET_RATIO` = 0.25, `ISSUE_SLANT_DEVIATION_DEG` = 25, `ISSUE_GAP_DEVIATION_RATIO` = 0.25 |
| OCR | `OCR_ENABLED` = True, `OCR_LANGUAGES` = ("en",) |
| Upload / photo checks | `ALLOWED_IMAGE_TYPES`, `MAX_UPLOAD_BYTES` = 15 MB, `MIN_IMAGE_SIDE_PX` = 600, `MIN_INK_FRACTION` = 0.0005, `MIN_INK_CONTRAST` = 30, `MIN_EDGE_SHARPNESS` = 0.2, `MIN_LETTERS_FOR_ANALYSIS` = 10, `RECTIFIED_JPEG_QUALITY` = 85 |
| Page detection | `PAGE_DETECT_MAX_SIDE_PX` = 800, `PAGE_MIN_AREA_FRACTION` = 0.2, `PAGE_MAX_AREA_FRACTION` = 0.97, `PAGE_MIN_BRIGHTNESS_GAIN` = 15 |
| Image pipeline | `TARGET_IMAGE_WIDTH_PX` = 1000, `BACKGROUND_KERNEL_PX` = 31, `BACKGROUND_SMOOTHING_PX` = 5, `BLUR_KERNEL_PX` = 3, `THRESHOLD_BLOCK_SIZE_PX` = 31, `THRESHOLD_OFFSET_C` = 10, `MIN_COMPONENT_AREA_PX` = 10 |
| Segmentation | `LINE_MIN_INK_FRACTION` = 0.05, `LINE_MERGE_GAP_PX` = 6, `LINE_MIN_HEIGHT_PX` = 8, `NEAR_LINE_MAX_GAP_RATIO` = 0.5, `MARK_MAX_HEIGHT_RATIO` = 0.4, `CLUSTER_MIN_WIDTH_RATIO` = 2.0 |
| Deskew | `DESKEW_MAX_ANGLE_DEG` = 15, `DESKEW_STEP_DEG` = 0.5 |
| Measurements | `MIN_COMPONENTS_FOR_STATS` = 5, `MIN_GAPS_FOR_STATS` = 4, `MIN_LETTERS_FOR_BASELINE` = 3, `X_HEIGHT_ROW_FRACTION` = 0.5, `WORD_GAP_MIN_RATIO` = 2.5 |

Odd-only values: `BLUR_KERNEL_PX`, `THRESHOLD_BLOCK_SIZE_PX`, `BACKGROUND_SMOOTHING_PX` (OpenCV requires it).

---

## 7. The scoring model

**Features and curves**

| Feature | Measurement | Curve | Parameters | Full score when |
|---|---|---|---|---|
| `textSize` | `textHeightCanvasRatio` | sweet-spot | (0.005, 0.010, 0.025, 0.050) | 1-2.5% of canvas height |
| `xHeight` | `xHeightAscenderRatio` | sweet-spot | (0.30, 0.45, 0.75, 0.95) | small letters 45-75% of tall letters' height |
| `baselineConsistency` | `baselineVariationRatio` | decreasing | (0.10, 0.80) | at most 10% of lowercase body height |
| `shapeConsistency` | mean of `slantStdDeg` and `letterHeightCv` | decreasing | (2.0, 20.0) and (0.05, 0.35) | slant spread at most 2 degrees; same-group heights within 5% |
| `strokeContrast` | `strokeContrastRatio` | decreasing | (1.2, 4.0) | ratio at most 1.2 |
| `strokeWeight` | `strokeWidthRatio` | sweet-spot | (0.02, 0.06, 0.18, 0.35) | 6-18% of lowercase body height |
| `letterSpacing` | `relativeLetterSpacing` | sweet-spot | (0.0, 0.15, 0.6, 1.2) | 0.15-0.6 x-height |
| `spacingConsistency` | `letterSpacingCv` | decreasing | (0.15, 1.0) | CV at most 0.15 |

**Combining**

```
legibilityScore = round_half_up( 100 x  sum(w_k x f_k) / sum(w_k) )   over available features only
```

Equal weights (1/8). A missing feature is neither 0 nor perfect: its weight is shared among the others
and it's listed in `missingFeatureIds`. Rounding half up (not Python's half-to-even) keeps the label
consistent with the displayed number. Labels: 85+ "Very legible", 70+ "Readable", 50+ "Some
difficulty", otherwise "Hard to read".

**Design principles:** robust statistics (medians, Theil-Sen, MAD) so a few odd letters don't skew
results; unitless ratios to x-height so rules work at any writing size; `null` for unknown, never 0.

**Contract history:** 1.2 added OCR; 1.3 removed `aspectRatioCv` and `solidityCv` (they mixed up letter
identity with inconsistency, so `shapeConsistency` is now slant only); 1.4 made OCR display-only.

---

## 8. Conventions

- **Names:** shared fields use the canonical camelCase names from the contract, with units in the name
  (`Mm`, `Px`, `Deg`, `Pct`, `Cv`, `Ratio`). Python helpers use snake_case; constants UPPER_SNAKE_CASE.
- **Images:** NumPy arrays; colour is **BGR**; index as `image[y, x]`; y points down.
- **Ink mask polarity:** 255 = ink, 0 = paper.
- **Coordinates:** all overlay coordinates are pixels in `rectifiedImage`.
- **Missing values:** `None` / `null` means not measurable; 0 is a real measurement.
- **One source of numbers:** every threshold in `scoring_config.py`.
- **Contract changes** go in `shared/analysis-contract.md`, `schemas.py`, `frontend/src/types/analysis.ts`
  and the fixtures together, with a `schemaVersion` bump for breaking changes.

---

## 9. Testing

```bash
python3 -m pytest                      # all 105
python3 -m pytest tests/test_api.py    # one file
python3 -m pytest -k deskew            # tests whose name contains "deskew"
```

| File | Tests | Covers |
|---|---|---|
| `test_api.py` | 24 | full requests: complete results, page found automatically or via corners, every error code, check order, HTTP 422, OCR never changing the score |
| `test_image_pipeline.py` | 22 | lines, components, i-dots, deskew, rotation, page detection, lighting correction, contrast, sharpness |
| `test_scoring.py` | 12 | curves, missing values, weight rescaling, bands, rounding, every measurement has one curve |
| `test_issues.py` | 11 | floating and sunken letters, descenders left alone, leaning letters, gaps, clusters, page-wide marks |
| `test_measurements.py` | 16 | each measurement on drawn shapes with known answers; height groups (descenders vs sunken letters, within-group evenness) |
| `test_advice.py` | 9 | template coverage and placeholders, direction, weakest-first, at most three |
| `test_schemas.py` | 6 | fixtures validate; unknown fields rejected; Python and TypeScript field names match |
| `test_ocr.py` | 5 | confidence weighting, no text, model load failure, OCR disabled |

`tests/conftest.py` replaces `read_handwriting` with a stub that returns None for every test, so the
real model never loads; tests that need OCR results install a fake with `monkeypatch`.

Test images are drawn in code (rectangles, rendered text), so expected values are exact, e.g. 40 px
letters on a 200 px tall canvas must give `textHeightCanvasRatio = 0.2`. Note: `cv2.rectangle` draws edges 2 px thicker than
asked, so tests draw pixel-exact shapes with NumPy slicing instead.

---

## 10. Validation (not yet run)

The weights and curve values are placeholders until compared with blind human ratings. The full method
(consent, rating protocol, rater agreement with ICC, non-negative ridge regression toward equal weights
with leave-one-out selection, bootstrap intervals, Spearman correlation on a held-out test set) is in
`validation/WEIGHT_FITTING_GUIDE.md`, which includes the fitting code.

---

## 11. Common tasks

**Tune a threshold:** change it in `scoring_config.py`, run the tests, and check real photos at `/docs`.
Tests that encode the old value will fail and need their expected numbers updated deliberately.

**Add a measurement:**
1. Write `measure_<name>_px()` in `measurements.py` and add it to `compute_feature_measurements()`.
2. Give it a curve in `scoring_config.py` and map it in `FEATURE_SOURCES` (new feature or extra source).
3. Add advice templates and a `DISPLAY_FORMATS` entry in `advice.py`.
4. Update the contract: `schemas.py`, `frontend/src/types/analysis.ts`, both fixtures,
   `shared/analysis-contract.md`, and bump `SCHEMA_VERSION`.
5. Add tests. `test_scoring.py`, `test_advice.py` and `test_schemas.py` fail until every step is done.

**Add a quality check:** raise `PhotoProblem(code, checkId, message)` at the right point in `main.py`,
append `passed(checkId)` when it passes, and add the new code and ID to the contract's lists.

**Change the weights:** follow the validation guide, then set `FEATURE_WEIGHTS` (every featureId,
summing to 1) and update the one test that assumes equal weights.

**Turn OCR off:** `OCR_ENABLED = False`; `recognizedText` becomes null. Scores don't change.

**Look at what the pipeline sees:** `python -m scripts.preview_ink_mask <image>`, or save intermediate
images from a Python shell (`cv2.imwrite`) after each `image_pipeline` function.

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `recognizedText` always null; warning "Text recognition isn't available" | EasyOCR missing, or its model download failed (on Macs, usually `CERTIFICATE_VERIFY_FAILED`) | run Applications > Python 3.x > *Install Certificates.command*, then restart the server (a failed load is remembered until restart). Scores are unaffected |
| `import cv2` errors after installing | `easyocr` installed `opencv-python` next to `opencv-python-headless` | `pip uninstall opencv-python` |
| `Could not open requirements file` | wrong folder | run `pip install -r requirements.txt` from `backend/`, or use `backend/requirements.txt` from the root |
| Browser blocked by CORS | frontend not on `localhost:5173` | use the Vite proxy described in `frontend/README.md`, or add the origin in `main.py` |
| Letters measured far too big (e.g. 30 mm) | page edges not visible, so the whole photo was used as the page | photograph the whole page on a darker surface, or send `cornerPointsPx` |
| Sideways photo gives nonsense | deskew only handles +/- 15 degrees | rotate in the browser (rotate button) before uploading |
| Every photo `SEGMENTATION_UNCERTAIN` | joined (cursive) writing, so few separate letters | write in print; or review `CLUSTER_MIN_WIDTH_RATIO` |

---

## 13. Known limitations

- **Tested on synthetic images only.** Thresholds and curves need tuning on real photos taken per `instructions.txt`.
- **Not validated** against human ratings; present the score as an experimental estimate.
- **Cursive** produces clusters instead of letters, so many measurements become null.
- **Joined pairs** like "th" can count as one letter (not wide enough to be a cluster).
- **Lines that touch** (a descender reaching the next line's ascender) merge into one line.
- **Rotation** beyond +/- 15 degrees isn't detected automatically (the frontend rotate button covers it).
- **Lopsided letters** (h, r, b, d) read up to about 17 degrees of slant even when upright, adding noise to `slantStdDeg`.
- **Stroke contrast** reads a little high because stroke ends look thin.
- **No endpoint** returns detected corners for a preview screen yet.

Physical dimensions are optional and never change image geometry, measurements or scores.
With known page bounds, median letter heights below 2 mm or above 10 mm produce warnings only.
These broad defaults target ordinary handwriting, not headings; they are configurable product heuristics.
Use a full-page photo; strong perspective makes the estimated proportions approximate.
