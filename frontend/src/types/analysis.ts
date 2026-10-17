// Types for POST /api/analyze.
// Must match backend/app/schemas.py field-for-field; see shared/analysis-contract.md.
// null means "could not be estimated"; 0 is a real measurement.

export const SCHEMA_VERSION = "1.4"; // 1.2 added OCR; 1.3 removed aspectRatioCv/solidityCv; 1.4 made OCR display-only

export type FeatureId =
  | "textSize"
  | "xHeight"
  | "baselineConsistency"
  | "shapeConsistency"
  | "strokeContrast"
  | "strokeWeight"
  | "letterSpacing"
  | "spacingConsistency";

export type CheckId =
  | "fileType"
  | "fileSize"
  | "decode"
  | "imageSize"
  | "blur"
  | "contrast"
  | "pageBounds"
  | "inkAmount"
  | "segmentation";

export type ErrorCode =
  | "INVALID_FILE_TYPE"
  | "FILE_TOO_LARGE"
  | "IMAGE_DECODE_FAILED"
  | "IMAGE_TOO_SMALL"
  | "BLUR_TOO_HIGH"
  | "CONTRAST_TOO_LOW"
  | "PAGE_NOT_FOUND"
  | "NOT_ENOUGH_WRITING"
  | "SEGMENTATION_UNCERTAIN";

export type AnalysisStatus = "complete" | "needs_better_photo";

// ---------- request ----------

/** One [x, y] point in originalImage pixels. */
export type PointPx = [number, number];

/** Form fields of POST /api/analyze (multipart/form-data). */
export interface AnalyzeRequest {
  imageFile: File;
  pageWidthMm: number;
  pageHeightMm: number;
  /** Page corners: top-left, top-right, bottom-right, bottom-left. Sent as a JSON string. */
  cornerPointsPx?: [PointPx, PointPx, PointPx, PointPx];
}

// ---------- response parts ----------

export interface AnalysisError {
  code: ErrorCode;
  message: string;
}

export interface QualityCheck {
  checkId: CheckId;
  passed: boolean;
  message: string | null;
}

/** The eight raw measurements. */
export interface FeatureMeasurements {
  textSizeMm: number | null;
  xHeightMm: number | null;
  baselineVariationMm: number | null;
  slantStdDeg: number | null;
  strokeContrastRatio: number | null;
  strokeWidthMedianMm: number | null;
  relativeLetterSpacing: number | null;
  letterSpacingCv: number | null;
}

/** featureId -> 0-1 normalizedScore, or null when missing. Every key is always sent. */
export type FeatureScores = Record<FeatureId, number | null>;

/** Weights actually used, renormalized over available features; missing features are left out. */
export type FeatureWeights = Partial<Record<FeatureId, number>>;

export interface OverlayLine {
  lineId: string;
  kind: "baseline" | "xHeight";
  x1Px: number;
  y1Px: number;
  x2Px: number;
  y2Px: number;
}

export interface OverlayComponent {
  componentId: string;
  lineId: string;
  xPx: number;
  yPx: number;
  widthPx: number;
  heightPx: number;
  issueFeatureIds: FeatureId[];
}

export interface OverlayGap {
  gapId: string;
  lineId: string;
  kind: "letter" | "word";
  xPx: number;
  yPx: number;
  widthPx: number;
  heightPx: number;
  issueFeatureIds: FeatureId[];
}

/** Everything drawn over rectifiedImage. All coordinates are rectifiedImage pixels. */
export interface OverlayData {
  coordinateSpace: "rectifiedImagePx";
  imageWidthPx: number;
  imageHeightPx: number;
  lines: OverlayLine[];
  components: OverlayComponent[];
  gaps: OverlayGap[];
}

export interface AdviceItem {
  featureId: FeatureId;
  title: string;
  message: string;
  exercise: string;
}

// ---------- full response ----------

export interface AnalysisResponse {
  schemaVersion: "1.4";
  status: AnalysisStatus;
  error: AnalysisError | null;
  /** Final 0-100 score, or null. */
  legibilityScore: number | null;
  scoreLabel: string | null;
  /** Data URL (PNG or JPEG) of the rectified page that overlayData refers to. */
  rectifiedImage: string | null;
  /** What the OCR model read, for display only (never part of the score); null if OCR is unavailable. */
  recognizedText: string | null;
  featureMeasurements: FeatureMeasurements | null;
  featureScores: FeatureScores | null;
  featureWeights: FeatureWeights | null;
  missingFeatureIds: FeatureId[];
  warnings: string[];
  qualityChecks: QualityCheck[];
  overlayData: OverlayData | null;
  /** At most three tips, weakest feature first. */
  advice: AdviceItem[];
}
