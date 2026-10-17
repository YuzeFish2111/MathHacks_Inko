import cv2
import numpy as np

from app.image_pipeline import (find_text_lines, find_components, rotate_image, deskew,
                                threshold_ink, remove_small_components,
                                measure_ink_contrast, measure_edge_sharpness)
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
