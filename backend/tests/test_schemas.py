import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import schemas
from app.scoring_config import FEATURE_IDS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PROJECT_ROOT / "shared" / "fixtures"
ANALYSIS_TS = PROJECT_ROOT / "frontend" / "src" / "types" / "analysis.ts"


def load_fixture(name):
    return json.loads((FIXTURES_DIR / name).read_text())


def test_fixtures_match_the_schema():
    for name in ("complete-response.json", "needs-better-photo-response.json"):
        schemas.AnalysisResponse.model_validate(load_fixture(name))


def test_unknown_field_is_rejected():
    response = load_fixture("complete-response.json")
    response["score"] = 78                                   # not a contract name
    with pytest.raises(ValidationError):
        schemas.AnalysisResponse.model_validate(response)


def test_status_and_error_must_agree():
    response = load_fixture("needs-better-photo-response.json")
    response["error"] = None
    with pytest.raises(ValidationError):
        schemas.AnalysisResponse.model_validate(response)


def test_null_measurement_is_allowed_but_missing_key_is_not():
    response = load_fixture("complete-response.json")
    response["featureMeasurements"]["slantStdDeg"] = None
    schemas.AnalysisResponse.model_validate(response)

    withoutKey = copy.deepcopy(response)
    del withoutKey["featureMeasurements"]["slantStdDeg"]
    with pytest.raises(ValidationError):
        schemas.AnalysisResponse.model_validate(withoutKey)


def test_feature_ids_match_scoring_config():
    assert schemas.FeatureId.__args__ == FEATURE_IDS


def ts_interface_fields(source, interfaceName):
    """Field names of one `export interface` block in analysis.ts."""
    body = re.search(rf"export interface {interfaceName} \{{(.*?)\n\}}", source, re.S).group(1)
    return re.findall(r"^\s+(\w+)\??:", body, re.M)


def test_typescript_interfaces_match_pydantic_models():
    source = ANALYSIS_TS.read_text()
    pairs = {
        "AnalysisResponse": schemas.AnalysisResponse,
        "AnalysisError": schemas.AnalysisError,
        "QualityCheck": schemas.QualityCheck,
        "FeatureMeasurements": schemas.FeatureMeasurements,
        "OverlayLine": schemas.OverlayLine,
        "OverlayComponent": schemas.OverlayComponent,
        "OverlayGap": schemas.OverlayGap,
        "OverlayData": schemas.OverlayData,
        "AdviceItem": schemas.AdviceItem,
    }
    for interfaceName, model in pairs.items():
        assert ts_interface_fields(source, interfaceName) == list(model.model_fields), interfaceName
