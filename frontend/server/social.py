"""Newest video on the team's YouTube channel, for the Contact page widget.

Read from the channel's public RSS feed (no API key) and cached for 10 minutes. If the
channel has no videos yet, or the network is down, the widget shows a placeholder."""
import os
import time
import urllib.request
import xml.etree.ElementTree as ET

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/social")

CHANNEL_ID = os.environ.get("INKO_YOUTUBE_CHANNEL_ID", "UCpIjtzpQtociTbCJObbLByg")  # @Inko-Labs-Team
_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
_cache: dict = {"t": 0.0, "value": None}


def _fetch_latest() -> dict | None:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    with urllib.request.urlopen(url, timeout=4) as res:
        root = ET.fromstring(res.read())
    entry = root.find("atom:entry", _NS)
    if entry is None:
        return None
    video_id = entry.findtext("yt:videoId", default="", namespaces=_NS)
    if not video_id.replace("-", "").replace("_", "").isalnum():
        return None
    return {"id": video_id, "title": entry.findtext("atom:title", default="", namespaces=_NS)}


@router.get("/youtube")
async def latest_youtube_video():
    if time.time() - _cache["t"] > 600:
        try:
            _cache["value"] = await run_in_threadpool(_fetch_latest)
        except Exception:
            pass  # keep whatever we had; the widget falls back to a placeholder
        _cache["t"] = time.time()
    return {"latest": _cache["value"]}
