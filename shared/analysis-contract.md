# Analysis Contract

Canonical API and variable glossary for the MathHacks Handwriting Legibility project.
Copied from the Canonical Naming Contract in the project plan. Use these names verbatim in
prompts, API payloads, shared types, fixtures and UI props.

`frontend/src/types/analysis.ts` and `backend/app/schemas.py` must both match this file
field-for-field. Example responses: `shared/fixtures/`.

## Naming rules

- camelCase for shared data and runtime identifiers, PascalCase for type/class names,
  UPPER_SNAKE_CASE for constants. Private helpers (e.g. snake_case Python functions) may
  follow local conventions but must map to this contract at the boundary.
- Include units in names: `Mm`, `Px`, `Deg`, `Pct`, `Cv`, `Ratio`.
- Do not use ambiguous shared names such as `s`, `scale`, `size`, `score`, `img` or `x` without context.
- `legibilityScore` is the final 0-100 score; `normalizedScore` is a feature's 0-1 value.
- Use `featureId` values from the fixed list; do not invent synonyms.
- `inkMask` always means ink foreground: true/1/255 is handwriting; false/0 is paper.
- Overlay coordinates always refer to the rectified image and use pixel units.
- Use `null` when a metric cannot be estimated. `0` is a real measurement.

## Image pipeline variables

| Name | Meaning |
|---|---|
| `originalImage` | Uploaded source image, unchanged |
| `grayscaleImage` | Grayscale source image |
| `backgroundEstimate` | Estimated paper illumination/background |
| `normalizedImage` | Shading-corrected grayscale image |
| `inkMask` | Binary image; foreground is handwriting ink |
| `rectifiedImage` | The page cropped from the photo (no perspective warp, so letters keep their shape), lighting-corrected and straightened |
| `cornerPointsPx` | Four page corners in originalImage pixels (top-left, top-right, bottom-right, bottom-left) |
| `deskewAngleDeg` | Applied rotation angle in degrees |
| `pageWidthMm`, `pageHeightMm` | User-provided physical paper dimensions |
| `pageWidthPx`, `pageHeightPx` | Rectified page dimensions in pixels |
| `textLines` | Detected writing lines, ordered top-to-bottom |
| `letterComponents` | Candidate connected components; not guaranteed letters |
| `wordGaps` | Gaps classified as between words |
| `letterGaps` | Gaps classified as between adjacent letters |
| `qualityChecks` | Named image/input checks and their outcomes |

## Measurement and score variables

| Name | Meaning |
|---|---|
| `textHeightCanvasRatio` | Median letter height / pre-deskew canvas height |
| `xHeightAscenderRatio` | Median x-height-letter height / median ascender height (only same-group letters compared) |
| `baselineVariationRatio` | Robust baseline variation (descenders excluded) / lowercase-body height |
| `slantStdDeg` | Std. deviation of estimated slant, degrees |
| `letterHeightCv` | Height spread within each height group (x-height letters with x-height letters, ascenders with ascenders), pooled |
| `strokeContrastRatio` | 90th / 10th percentile stroke width |
| `strokeWidthRatio` | Median stroke width / lowercase-body height |
| `relativeLetterSpacing` | Median within-word letter gap / x-height; unitless |
| `letterSpacingCv` | CV of within-word letter gaps |
| `recognizedText` | What the OCR model read, shown to the user for interest only. **Never part of the score.** Null if OCR is unavailable |
| `featureMeasurements` | Object containing the raw measurements above |
| `featureScores` | Map featureId -> 0-1 normalized score or null |
| `featureWeights` | Map featureId -> weight used (renormalized over available features) |
| `missingFeatureIds` | featureIds whose score is null |
| `legibilityScore` | Final weighted estimate, 0-100 or null |
| `humanLegibilityRating` | Mean blind human rating, 1-10; validation only |
| `readingAccuracyPct` | Optional transcription accuracy, 0-100 |

## Fixed feature IDs and their source measurements

| featureId | Source measurement | Curve |
|---|---|---|
| `textSize` | `textHeightCanvasRatio` | sweet-spot |
| `xHeight` | `xHeightAscenderRatio` | sweet-spot |
| `baselineConsistency` | `baselineVariationRatio` | decreasing |
| `shapeConsistency` | mean of `slantStdDeg` and `letterHeightCv` | decreasing |
| `strokeContrast` | `strokeContrastRatio` | decreasing |
| `strokeWeight` | `strokeWidthRatio` | sweet-spot |
| `letterSpacing` | `relativeLetterSpacing` | sweet-spot |
| `spacingConsistency` | `letterSpacingCv` | decreasing |

OCR is display-only: it fills `recognizedText` and never changes any score, weight, mark or tip
(its confidence isn't calibrated, and a model can guess the famous pangram even from messy writing).
If EasyOCR isn't installed or its model can't load, `recognizedText` is null and a warning says so.

## Quality check IDs

`fileType`, `fileSize`, `decode`, `imageSize`, `blur`, `contrast`, `pageBounds`, `inkAmount`, `segmentation`

## Error codes (status `"needs_better_photo"`)

`INVALID_FILE_TYPE`, `FILE_TOO_LARGE`, `IMAGE_DECODE_FAILED`, `IMAGE_TOO_SMALL`,
`BLUR_TOO_HIGH`, `CONTRAST_TOO_LOW`, `PAGE_NOT_FOUND`, `NOT_ENOUGH_WRITING`,
`SEGMENTATION_UNCERTAIN`

## API

### `POST /api/analyze` (multipart/form-data)

| Field | Required | Type |
|---|---|---|
| `imageFile` | required | image file |
| `pageWidthMm` | optional | positive finite number; warning-only |
| `pageHeightMm` | optional | positive finite number; warning-only |
| `cornerPointsPx` | optional | JSON string `[[x,y],[x,y],[x,y],[x,y]]` in originalImage pixels, order top-left, top-right, bottom-right, bottom-left |
| `isDrawing` | optional | boolean, default `false`. The image is an on-screen drawing: it is used whole (no page detection, `cornerPointsPx` ignored), and because a screen is not a page, `textHeightCanvasRatio` is `null` and `textSize` is listed in `missingFeatureIds`. The score uses the other seven features. Added in 2.1 as an optional field, so older callers are unaffected. |

Rotating the photo (the preview screen's "Rotate 90°" button) happens in the browser before upload
(`frontend/src/utils/rotateImage.ts`). The backend only ever sees the uploaded, already-rotated image,
so `cornerPointsPx` and every overlay coordinate refer to that image. No extra field is sent.

### Response
- `schemaVersion`: `"2.1"`.
- `status`: `"complete"` or `"needs_better_photo"`.
- `error`: `null`, or `{ "code": string, "message": string }`.
- `qualityChecks` item: `{ "checkId": string, "passed": boolean, "message": string | null }`.
- Overlay line `kind`: `"baseline"` | `"xHeight"`. Gap `kind`: `"letter"` | `"word"`.
- `advice` item: `featureId`, `title`, `message`, `exercise`.
- `rectifiedImage`: data URL (PNG or JPEG) of the rectified page that overlays refer to.
- All overlay coordinates and dimensions are pixels in `"rectifiedImagePx"`.
- `issueFeatureIds` on a component or gap lists the features that box shows a problem with
  (empty list = no problem). Two kinds of mark:
  - **Element marks**, judged against the writer's own typical letter or gap:
    `baselineConsistency` (letter floats above or has sunk below its line; descenders are not marked),
    `shapeConsistency` (letter leans much more or less than the typical letter),
    `spacingConsistency` (letter gap much wider or narrower than the typical gap),
    `letterSpacing` (letter gap outside the ideal range, or letters joined into a cluster).
  - **Whole-page marks**: `textSize`, `xHeight`, `strokeWeight`, `strokeContrast` are added to every
    letter when that feature scores at or below the threshold. Draw these as a page-level state
    (e.g. tint all letters when that feature is selected), not as individual problem boxes.
  - Word gaps are never marked. Thresholds live in `backend/app/scoring_config.py` (`ISSUE_*`).

Full examples (illustrative values only, not calibrated):

- `shared/fixtures/complete-response.json`
- `shared/fixtures/needs-better-photo-response.json`

## Height groups (2.1)

Letters are only compared with letters of the same height. Each line's letters are split at the natural
break in their own heights (the biggest jump of at least 15%), so this works however many capitals or tall
letters a sentence has: x-height letters are below the break, and their median height is the reference
for the rest. Ascenders are above it with a top >= 1.20 x that reference above the baseline; descenders (tail
> 0.25 below the baseline with the top still >= 0.75, so a sunken letter isn't excused as a descender),
and in-between letters, which are never compared. `xHeightAscenderRatio` compares the two
main groups; `letterHeightCv` measures evenness within each group; `baselineVariationRatio` ignores
descenders. `textHeightCanvasRatio` is null when the page edges weren't found (the photo's own height
isn't a page reference). Thresholds are `X_HEIGHT_GROUP_MAX_RATIO`, `ASCENDER_MIN_RATIO`,
`DESCENDER_MIN_RATIO`, `DESCENDER_TOP_MIN_RATIO` and `MIN_HEIGHT_GROUP_SIZE` in `scoring_config.py`.

## Ratio geometry and physical warnings (2.0)

Physical page dimensions never affect detection, rectification, measurements, or scores.
Canvas ratios use dimensions before deskew expands the image. Keep the full canvas in frame.
Rectification estimates proportions from corner edge lengths; strong perspective remains approximate.
With known page bounds and either physical dimension, median letter heights below 2 mm or above
10 mm trigger a warning only. Height calibration is preferred; width-only calibration assumes
square rectified pixels. Missing bounds or dimensions skip physical warnings. Thresholds and ratio
scoring curves are initial product heuristics requiring validation against handwriting samples.
