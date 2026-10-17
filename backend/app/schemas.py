"""Pydantic request/response models for POST /api/analyze.

Must match frontend/src/types/analysis.ts field-for-field; see shared/analysis-contract.md.
Field names are the canonical camelCase names. Unknown fields are rejected (extra="forbid")
so any drift from the contract fails loudly instead of being silently ignored.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.1"

FeatureId = Literal["textSize", "xHeight", "baselineConsistency", "shapeConsistency",
                    "strokeContrast", "strokeWeight", "letterSpacing", "spacingConsistency"]
CheckId = Literal["fileType", "fileSize", "decode", "imageSize", "blur", "contrast",
                  "pageBounds", "inkAmount", "segmentation"]
ErrorCode = Literal["INVALID_FILE_TYPE", "FILE_TOO_LARGE", "IMAGE_DECODE_FAILED", "IMAGE_TOO_SMALL",
                    "BLUR_TOO_HIGH", "CONTRAST_TOO_LOW", "PAGE_NOT_FOUND", "NOT_ENOUGH_WRITING",
                    "SEGMENTATION_UNCERTAIN"]
AnalysisStatus = Literal["complete", "needs_better_photo"]


class ContractModel(BaseModel):
    """Base for every contract model: reject fields that are not in the contract."""
    model_config = ConfigDict(extra="forbid")


# ---------- request ----------

class AnalyzeRequestFields(ContractModel):
    """The non-file form fields of POST /api/analyze (imageFile arrives separately as an upload)."""
    pageWidthMm: float = Field(gt=0)
    pageHeightMm: float = Field(gt=0)
    # Four [x, y] page corners in originalImage pixels: top-left, top-right, bottom-right, bottom-left.
    # Sent as a JSON string in the form; parse it before building this model.
    cornerPointsPx: Optional[list[tuple[float, float]]] = Field(default=None, min_length=4, max_length=4)


# ---------- response parts ----------

class AnalysisError(ContractModel):
    code: ErrorCode
    message: str


class QualityCheck(ContractModel):
    checkId: CheckId
    passed: bool
    message: Optional[str]


class FeatureMeasurements(ContractModel):
    """The ten raw measurements. None (null) means it could not be estimated; 0 is a real value."""
    textSizeMm: Optional[float]
    xHeightMm: Optional[float]
    baselineVariationMm: Optional[float]
    aspectRatioCv: Optional[float]
    solidityCv: Optional[float]
    slantStdDeg: Optional[float]
    strokeContrastRatio: Optional[float]
    strokeWidthMedianMm: Optional[float]
    relativeLetterSpacing: Optional[float]
    letterSpacingCv: Optional[float]


class FeatureScores(ContractModel):
    """featureId -> 0-1 normalizedScore, or None when the feature is missing. All eight keys are always sent."""
    textSize: Optional[float] = Field(ge=0, le=1)
    xHeight: Optional[float] = Field(ge=0, le=1)
    baselineConsistency: Optional[float] = Field(ge=0, le=1)
    shapeConsistency: Optional[float] = Field(ge=0, le=1)
    strokeContrast: Optional[float] = Field(ge=0, le=1)
    strokeWeight: Optional[float] = Field(ge=0, le=1)
    letterSpacing: Optional[float] = Field(ge=0, le=1)
    spacingConsistency: Optional[float] = Field(ge=0, le=1)


class OverlayLine(ContractModel):
    lineId: str
    kind: Literal["baseline", "xHeight"]
    x1Px: float
    y1Px: float
    x2Px: float
    y2Px: float


class OverlayComponent(ContractModel):
    componentId: str
    lineId: str
    xPx: float
    yPx: float
    widthPx: float
    heightPx: float
    issueFeatureIds: list[FeatureId]


class OverlayGap(ContractModel):
    gapId: str
    lineId: str
    kind: Literal["letter", "word"]
    xPx: float
    yPx: float
    widthPx: float
    heightPx: float
    issueFeatureIds: list[FeatureId]


class OverlayData(ContractModel):
    """Everything drawn over rectifiedImage. All coordinates are rectifiedImage pixels."""
    coordinateSpace: Literal["rectifiedImagePx"]
    imageWidthPx: int
    imageHeightPx: int
    lines: list[OverlayLine]
    components: list[OverlayComponent]
    gaps: list[OverlayGap]


class AdviceItem(ContractModel):
    featureId: FeatureId
    title: str
    message: str
    exercise: str


# ---------- full response ----------

class AnalysisResponse(ContractModel):
    schemaVersion: Literal["1.1"]
    status: AnalysisStatus
    error: Optional[AnalysisError]
    legibilityScore: Optional[int] = Field(ge=0, le=100)    # whole number for display; see scoring.py
    scoreLabel: Optional[str]
    rectifiedImage: Optional[str]    # data URL (PNG or JPEG) that overlayData refers to
    featureMeasurements: Optional[FeatureMeasurements]
    featureScores: Optional[FeatureScores]
    # Weights actually used, renormalized over available features; missing features are left out
    featureWeights: Optional[dict[FeatureId, float]]
    missingFeatureIds: list[FeatureId]
    warnings: list[str]
    qualityChecks: list[QualityCheck]
    overlayData: Optional[OverlayData]
    advice: list[AdviceItem] = Field(max_length=3)

    @model_validator(mode="after")
    def check_status_matches_content(self) -> "AnalysisResponse":
        """A complete result has no error; a needs_better_photo result has an error and no score."""
        if self.status == "complete" and self.error is not None:
            raise ValueError('status "complete" must have error = null')
        if self.status == "needs_better_photo":
            if self.error is None:
                raise ValueError('status "needs_better_photo" must include an error')
            if self.legibilityScore is not None:
                raise ValueError('status "needs_better_photo" must have legibilityScore = null')
        return self
