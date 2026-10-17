import cv2
import numpy as np

from app.image_pipeline import (find_text_lines, find_components, rotate_image, deskew,
                                threshold_ink, remove_small_components,
                                measure_ink_contrast, measure_edge_sharpness, detect_page_corners,
                                estimate_background, normalize_illumination)
from app.scoring_config import DESKEW_STEP_DEG


def make_two_line_mask():
    """Synthetic inkMask: two lines of 40 px tall 'letters', plus an i-dot and a wide joined blob."""
    inkMask = np.zeros((300, 600), np.uint8)
    for xPx in (50, 100, 150, 200):                      # line 1 letters, rows 50-89
        inkMask[50:90, xPx:xPx + 25] = 255
    inkMask[40:46, 260:266] = 255                         # i-dot, 4 px above line 1
    inkMask[50:90, 260:266] = 255                         # i-stem under the dot
    for xPx in (50, 100, 150):                           # line 2 letters, rows 180-219
        inkMask[180:220, xPx:xPx + 25] = 255
    inkMask[180:220, 250:350] = 255                       # 100 px wide joined blob on line 2
    return inkMask


def test_find_text_lines_finds_two_lines_top_to_bottom():
    textLines = find_text_lines(make_two_line_mask())
    assert [line.lineId for line in textLines] == ["line-1", "line-2"]
    assert textLines[0].topPx == 50 and textLines[0].bottomPx == 89    # i-dot rows too faint to count
    assert textLines[1].topPx == 180 and textLines[1].bottomPx == 219


def test_find_text_lines_empty_mask():
    assert find_text_lines(np.zeros((100, 100), np.uint8)) == []


def test_find_components_assigns_sorts_and_classifies():
    inkMask = make_two_line_mask()
    textLines = find_components(inkMask, find_text_lines(inkMask))
    line1, line2 = textLines

    assert [c.xPx for c in line1.components] == [50, 100, 150, 200, 260, 260]
    assert all(c.lineId == "line-1" for c in line1.components)
    assert sorted(c.kind for c in line1.components) == ["letter"] * 5 + ["mark"]   # i-dot is a mark
    assert [c.kind for c in line2.components] == ["letter", "letter", "letter", "cluster"]

    componentIds = [c.componentId for line in textLines for c in line.components]
    assert componentIds == [f"component-{n}" for n in range(1, 11)]


def test_find_components_ignores_blobs_far_from_every_line():
    inkMask = make_two_line_mask()
    inkMask[130:136, 400:406] = 255                       # speck midway between the two lines
    textLines = find_components(inkMask, find_text_lines(inkMask))
    assert sum(len(line.components) for line in textLines) == 10


def test_find_components_contour_is_in_image_coordinates():
    inkMask = make_two_line_mask()
    component = find_components(inkMask, find_text_lines(inkMask))[0].components[0]
    xPx, yPx, widthPx, heightPx = cv2.boundingRect(component.contour)
    assert (xPx, yPx, widthPx, heightPx) == (50, 50, 25, 40)


def make_text_page():
    """White grayscale page with two lines of dark text."""
    page = np.full((600, 1000), 255, np.uint8)
    cv2.putText(page, "The quick brown fox", (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 3)
    cv2.putText(page, "jumps over the lazy dog.", (60, 400), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 3)
    return page


def test_rotate_image_enlarges_canvas_to_fit():
    rotated = rotate_image(np.zeros((100, 200), np.uint8), 90)
    assert rotated.shape == (200, 100)


def test_deskew_undoes_a_known_tilt():
    tiltedPage = rotate_image(make_text_page(), 6, borderValue=255)
    _, deskewAngleDeg = deskew(tiltedPage)
    assert abs(deskewAngleDeg - (-6)) <= DESKEW_STEP_DEG


def test_deskew_leaves_straight_and_blank_pages_alone():
    assert deskew(make_text_page())[1] == 0
    assert deskew(np.full((300, 300), 255, np.uint8))[1] == 0


def contrast_and_sharpness(grayscalePage):
    inkMask = remove_small_components(threshold_ink(grayscalePage))
    inkContrast = measure_ink_contrast(grayscalePage, inkMask)
    return inkContrast, measure_edge_sharpness(grayscalePage, inkMask, inkContrast)


def test_ink_contrast_is_paper_minus_ink():
    page = np.full((600, 1000), 230, np.uint8)
    cv2.putText(page, "The quick brown fox", (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 2, 80, 3)
    assert contrast_and_sharpness(page)[0] == 150


def test_sharpness_is_about_half_for_a_sharp_edge_and_drops_with_blur():
    sharpness = [contrast_and_sharpness(make_text_page() if sigma == 0 else
                                        cv2.GaussianBlur(make_text_page(), (0, 0), sigma))[1]
                 for sigma in (0, 1, 2, 4)]
    assert 0.45 <= sharpness[0] <= 0.55
    assert sharpness == sorted(sharpness, reverse=True)          # more blur, less sharp


def test_faint_but_sharp_writing_is_not_called_blurry():
    page = np.full((600, 1000), 235, np.uint8)
    cv2.putText(page, "The quick brown fox", (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 2, 190, 3)
    inkContrast, sharpness = contrast_and_sharpness(page)
    assert inkContrast < 60 and sharpness > 0.45


def test_contrast_and_sharpness_are_null_without_ink():
    blank = np.full((300, 300), 255, np.uint8)
    noInk = np.zeros((300, 300), np.uint8)
    assert measure_ink_contrast(blank, noInk) is None
    assert measure_edge_sharpness(blank, noInk, None) is None


KEYSTONED_CORNERS = [[260, 180], [1240, 220], [1280, 1620], [220, 1600]]


def photo_of_page_on_desk(deskLevel, corners, seed=0):
    """A 1500 x 1800 'photo': an A4 page with writing, warped onto a noisy desk."""
    rng = np.random.default_rng(seed)
    photo = np.clip(np.full((1800, 1500, 3), deskLevel, np.float32) + rng.normal(0, 6, (1800, 1500, 3)),
                    0, 255).astype(np.uint8)
    page = np.full((1414, 1000, 3), 240, np.uint8)
    cv2.putText(page, "The quick brown fox", (80, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    pageCorners = np.float32([[0, 0], [999, 0], [999, 1413], [0, 1413]])
    transform = cv2.getPerspectiveTransform(pageCorners, np.float32(corners))
    return cv2.warpPerspective(page, transform, (1500, 1800), dst=photo, borderMode=cv2.BORDER_TRANSPARENT)


def max_corner_error_px(found, expected):
    return float(np.abs(np.float32(found) - np.float32(expected)).max())


def test_detects_a_keystoned_page_on_dark_and_light_desks():
    for deskLevel in (90, 200):        # 90: brightness mask finds it; 200: edge mask is needed
        found = detect_page_corners(photo_of_page_on_desk(deskLevel, KEYSTONED_CORNERS), 210, 297)
        assert found is not None and max_corner_error_px(found, KEYSTONED_CORNERS) <= 6, deskLevel


def test_detects_a_rotated_page_and_returns_corners_in_order():
    corners = [[400, 150], [1350, 280], [1150, 1650], [180, 1520]]      # about 8 degrees clockwise
    found = detect_page_corners(photo_of_page_on_desk(150, corners), 210, 297)
    assert found is not None and max_corner_error_px(found, corners) <= 6


def test_detects_a_smaller_page():
    corners = [[400, 400], [1100, 400], [1100, 1390], [400, 1390]]      # about 26% of the photo
    assert detect_page_corners(photo_of_page_on_desk(90, corners), 210, 297) is not None


def test_no_page_found_when_it_fills_the_frame_or_is_missing():
    fullFramePage = np.full((1414, 1000, 3), 255, np.uint8)
    cv2.putText(fullFramePage, "The quick brown fox", (80, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    assert detect_page_corners(fullFramePage, 210, 297) is None
    noise = (np.random.default_rng(1).random((1800, 1500, 3)) * 255).astype(np.uint8)
    assert detect_page_corners(noise, 210, 297) is None


def test_page_with_the_wrong_shape_is_rejected():
    # A portrait page, but the user said landscape (297 x 210): don't stretch it to fit
    assert detect_page_corners(photo_of_page_on_desk(90, KEYSTONED_CORNERS), 297, 210) is None


def lit_page(lighting):
    """The text page (paper 245) multiplied by a lighting pattern of the same shape (1 = full light)."""
    page = np.where(make_text_page() < 128, 0, 245).astype(np.float32)
    return np.clip(page * lighting, 0, 255).astype(np.uint8)


def ink_mask_match(image, reference):
    """Overlap (intersection over union) between the ink masks of two images."""
    a = remove_small_components(threshold_ink(image)) > 0
    b = remove_small_components(threshold_ink(reference)) > 0
    return (a & b).sum() / (a | b).sum()


def lighting_patterns():
    heightPx, widthPx = make_text_page().shape
    _, columnPx = np.mgrid[0:heightPx, 0:widthPx]
    return {"gradient": 1 - 0.65 * columnPx / widthPx,               # light fading across the page
            "hard shadow": np.where(columnPx > widthPx * 0.55, 0.45, 1.0)}   # e.g. a phone's shadow


def test_background_estimate_ignores_the_ink():
    evenPage = lit_page(1.0)
    backgroundEstimate = estimate_background(evenPage)
    assert backgroundEstimate.min() >= 240                          # ink removed: paper level everywhere


def test_normalized_paper_is_white_under_any_lighting():
    for name, lighting in lighting_patterns().items():
        normalizedImage = normalize_illumination(lit_page(lighting))
        inkMask = remove_small_components(threshold_ink(normalizedImage))
        paper = normalizedImage[cv2.dilate(inkMask, np.ones((5, 5), np.uint8)) == 0]
        assert np.percentile(paper, 5) >= 245, name


def test_ink_mask_under_uneven_lighting_matches_even_lighting():
    evenPage = lit_page(1.0)
    for name, lighting in lighting_patterns().items():
        assert ink_mask_match(normalize_illumination(lit_page(lighting)), evenPage) > 0.98, name


def test_hard_shadow_edge_is_not_turned_into_ink():
    hardShadow = lit_page(lighting_patterns()["hard shadow"])
    # Without correction the shadow edge corrupts the mask; with it, the mask matches even lighting
    assert ink_mask_match(normalize_illumination(hardShadow), lit_page(1.0)) > \
        ink_mask_match(hardShadow, lit_page(1.0))
