"""Quick OpenCV check next to the analysis: was the photo taken at an angle? Deliberately
conservative so a good photo is never flagged by a false alarm. (Whether there is enough
writing is the analysis backend's call: its NOT_ENOUGH_WRITING answer.)
"""
import cv2
import numpy as np


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]])


def _corner_angles(c: np.ndarray) -> list[float]:
    angles = []
    for i in range(4):
        a, b, n = c[i - 1], c[i], c[(i + 1) % 4]
        v1, v2 = a - b, n - b
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6))
        angles.append(float(np.degrees(np.arccos(np.clip(cos, -1, 1)))))
    return angles


def detect_tilt(gray: np.ndarray) -> dict:
    """Find the sheet of paper. If its outline is a trapezoid instead of a rectangle,
    the camera was not straight above the page and letters will look stretched.

    In-plane rotation keeps a rectangle a rectangle, so a page that is merely turned
    on the table is not flagged.
    """
    scale = 800.0 / max(gray.shape[:2])
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    h, w = small.shape[:2]
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    _, paper = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = {"paper_found": False, "tilted": False, "side_ratio": None}
    if not contours:
        return result
    biggest = max(contours, key=cv2.contourArea)
    frac = cv2.contourArea(biggest) / float(h * w)
    if frac < 0.12 or frac > 0.96:
        return result  # no clear page, or the page fills the frame (cannot judge)
    hull = cv2.convexHull(biggest)
    quad = None
    for eps in (0.02, 0.03, 0.045):
        approx = cv2.approxPolyDP(hull, eps * cv2.arcLength(hull, True), True)
        if len(approx) == 4:
            quad = approx
            break
    if quad is None:
        return result
    corners = _order_corners(quad)
    margin = 0.012 * max(h, w)
    on_edge = sum(
        1 for x, y in corners if x < margin or y < margin or x > w - margin or y > h - margin
    )
    if on_edge:
        return result  # page is cut off by the frame, so the outline is not its real shape
    tl, tr, br, bl = corners
    top, bottom = np.linalg.norm(tr - tl), np.linalg.norm(br - bl)
    left, right = np.linalg.norm(bl - tl), np.linalg.norm(br - tr)
    ratio = float(min(min(top, bottom) / max(top, bottom), min(left, right) / max(left, right)))
    worst_angle = max(abs(a - 90) for a in _corner_angles(corners))
    result.update(
        paper_found=True,
        side_ratio=round(ratio, 3),
        tilted=bool(ratio < 0.86 or worst_angle > 15),
    )
    return result
