"""Create a demo account with a few weeks of improving scans, so the Progress page
has something to show during a demo.

Start the analysis backend first (cd backend && uvicorn app.main:app), then:

    .venv/bin/python scripts/seed_demo.py

Then sign in as  demo / inko-demo  . Running it again resets the demo account.

Every saved scan uses the backend's real analysis of web/img/example.jpg (image, overlays,
tips), with the scores replaced by the made-up JOURNEY below. Demo data only.
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import analysis, auth, config, db, imaging  # noqa: E402
from server.errors import InkoError  # noqa: E402

USERNAME, PASSWORD, NAME = "demo", "inko-demo", "Demo Student"
# Feature scores (0-1) climb as practice pays off; textSize stays unmeasured, as for the example photo.
JOURNEY = [
    {"xHeight": 0.62, "baselineConsistency": 0.48, "shapeConsistency": 0.35, "strokeContrast": 0.70,
     "strokeWeight": 0.80, "letterSpacing": 0.55, "spacingConsistency": 0.30},
    {"xHeight": 0.68, "baselineConsistency": 0.55, "shapeConsistency": 0.38, "strokeContrast": 0.72,
     "strokeWeight": 0.84, "letterSpacing": 0.63, "spacingConsistency": 0.34},
    {"xHeight": 0.75, "baselineConsistency": 0.63, "shapeConsistency": 0.40, "strokeContrast": 0.76,
     "strokeWeight": 0.88, "letterSpacing": 0.72, "spacingConsistency": 0.39},
    {"xHeight": 0.83, "baselineConsistency": 0.74, "shapeConsistency": 0.41, "strokeContrast": 0.80,
     "strokeWeight": 0.92, "letterSpacing": 0.81, "spacingConsistency": 0.43},
    {"xHeight": 0.91, "baselineConsistency": 0.86, "shapeConsistency": 0.42, "strokeContrast": 0.83,
     "strokeWeight": 0.96, "letterSpacing": 0.90, "spacingConsistency": 0.47},
    {"xHeight": 1.0, "baselineConsistency": 1.0, "shapeConsistency": 0.42, "strokeContrast": 0.86,
     "strokeWeight": 1.0, "letterSpacing": 1.0, "spacingConsistency": 0.50},
]


def score_label(score: int) -> str:
    bands = analysis.scoring_model()["scoreBands"]
    return next(band["label"] for band in bands if score >= band["minScore"])


def main() -> None:
    photo = imaging.prepare((config.WEB_DIR / "img" / "example.jpg").read_bytes())
    try:
        base = asyncio.run(analysis.analyze(photo.jpeg))
    except InkoError:
        sys.exit(f"Can't analyze the example photo. Is the analysis backend running at {config.ANALYSIS_API_URL}?\n"
                 "Start it with: cd backend && uvicorn app.main:app")
    page_jpeg = imaging.data_url_bytes(base["rectifiedImage"])
    thumb = imaging.thumbnail_jpeg(page_jpeg)
    width, height = base["overlayData"]["imageWidthPx"], base["overlayData"]["imageHeightPx"]

    db.init()
    with db.connect() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (USERNAME,))
        user_id = conn.execute(
            "INSERT INTO users (name, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (NAME, USERNAME, auth.hash_password(PASSWORD), datetime.now(timezone.utc).isoformat()),
        ).lastrowid
        start = datetime.now(timezone.utc) - timedelta(days=21)
        for i, feature_scores in enumerate(JOURNEY):
            when = (start + timedelta(days=i * 4, hours=i)).isoformat(timespec="seconds")
            rid = uuid.uuid4().hex
            scores = {**dict.fromkeys(base["featureScores"]), **feature_scores}
            overall = round(100 * sum(feature_scores.values()) / len(feature_scores))
            result = {
                "result_id": rid, "created_at": when,
                "photo_check": {"tilted": False, "shadows": False, "jev_used": False},
                "analysis": {**base, "rectifiedImage": None, "featureScores": scores,
                             "legibilityScore": overall, "scoreLabel": score_label(overall)},
                "overall_score": overall,
                "scores": {k: None if v is None else round(v * 100) for k, v in scores.items()},
            }
            conn.execute(
                "INSERT INTO results (id, user_id, created_at, overall, data, width, height, preview, thumb) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, user_id, when, overall, json.dumps(result), width, height, page_jpeg, thumb),
            )
    print(f"Demo account ready: sign in as {USERNAME} / {PASSWORD}")


if __name__ == "__main__":
    main()
