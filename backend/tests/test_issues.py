import cv2
import numpy as np

from app.image_pipeline import find_text_lines, find_components
from app.issues import find_component_issues, find_gap_issues
from app.measurements import find_gaps, measure_x_height_px
from app.scoring_config import FEATURE_IDS

GOOD_SCORES = {featureId: 1.0 for featureId in FEATURE_IDS}
LETTER_COUNT = 10


def draw_line(gapsPx=None, offsetsPx=None, leaningLetter=None, descenders=()):
    """A line of hollow 20 x 40 px 'letters' (x-height 40 px).

    gapsPx: gap after each letter (default 10 px = 0.25 x-height, inside the ideal range).
    offsetsPx: {letterIndex: pixels the whole letter moves down} to break the baseline.
    leaningLetter: index of a letter drawn as a slanted stroke instead of a box.
    descenders: indexes of letters with a tail 14 px (0.35 x-height) below the baseline, like g or y.
    """
    gapsPx = gapsPx or [10] * (LETTER_COUNT - 1)
    offsetsPx = offsetsPx or {}
    inkMask = np.zeros((240, 700), np.uint8)
    xPx = 30
    for letterIndex in range(LETTER_COUNT):
        topPx = 100 + offsetsPx.get(letterIndex, 0)
        if letterIndex == leaningLetter:
            cv2.line(inkMask, (xPx + 2, topPx + 38), (xPx + 28, topPx + 2), 255, 5)    # leans ~36 degrees
        else:
            inkMask[topPx:topPx + 40, xPx:xPx + 20] = 255
            inkMask[topPx + 5:topPx + 35, xPx + 5:xPx + 15] = 0
            if letterIndex in descenders:
                inkMask[topPx + 40:topPx + 54, xPx + 15:xPx + 20] = 255                 # tail on the right side
        xPx += 20 + (gapsPx[letterIndex] if letterIndex < len(gapsPx) else 0)
    return inkMask


def issues_for(inkMask, featureScores=GOOD_SCORES):
    textLines = find_components(inkMask, find_text_lines(inkMask))
    xHeightPx = measure_x_height_px(inkMask, textLines)
    components = [component for line in textLines for component in line.components]
    componentIssues = find_component_issues(textLines, xHeightPx, featureScores)
    gaps = find_gaps(textLines)
    return ([componentIssues[component.componentId] for component in components],
            find_gap_issues(gaps, xHeightPx), gaps)


def test_even_writing_has_no_marks():
    componentIssues, gapIssues, _ = issues_for(draw_line())
    assert all(issueIds == [] for issueIds in componentIssues + gapIssues)


def test_letter_floating_above_the_baseline_is_marked():
    componentIssues, _, _ = issues_for(draw_line(offsetsPx={3: -15}))      # 15 px = 0.375 x-height up
    assert componentIssues[3] == ["baselineConsistency"]
    assert all(issueIds == [] for index, issueIds in enumerate(componentIssues) if index != 3)


def test_letter_sunk_below_the_baseline_is_marked():
    componentIssues, _, _ = issues_for(draw_line(offsetsPx={3: 15}))       # whole letter 0.375 x-height down
    assert componentIssues[3] == ["baselineConsistency"]


def test_descenders_are_not_marked_as_off_the_baseline():
    componentIssues, _, _ = issues_for(draw_line(descenders=(2, 6)))       # tails drop, tops stay level
    assert all("baselineConsistency" not in issueIds for issueIds in componentIssues)


def test_leaning_letter_is_marked():
    gapsPx = [10] * (LETTER_COUNT - 1)
    gapsPx[4] = 20                      # room for the leaning stroke so it doesn't touch the next letter
    componentIssues, _, _ = issues_for(draw_line(gapsPx=gapsPx, leaningLetter=4))
    assert "shapeConsistency" in componentIssues[4]
    assert all("shapeConsistency" not in issueIds for index, issueIds in enumerate(componentIssues) if index != 4)


def test_uneven_gap_is_marked_spacing_consistency_only():
    gapsPx = [10] * (LETTER_COUNT - 1)
    gapsPx[5] = 22                      # 0.55 x-height: still ideal, but 0.3 x-height wider than typical
    _, gapIssues, _ = issues_for(draw_line(gapsPx=gapsPx))
    assert gapIssues[5] == ["spacingConsistency"]
    assert all(issueIds == [] for index, issueIds in enumerate(gapIssues) if index != 5)


def test_gaps_that_are_too_tight_are_marked_letter_spacing():
    _, gapIssues, _ = issues_for(draw_line(gapsPx=[2] * (LETTER_COUNT - 1)))   # 0.05 x-height
    assert all(issueIds == ["letterSpacing"] for issueIds in gapIssues)


def test_word_gaps_are_never_marked():
    gapsPx = [10] * (LETTER_COUNT - 1)
    gapsPx[4] = 60                      # a space between words
    _, gapIssues, gaps = issues_for(draw_line(gapsPx=gapsPx))
    assert gaps[4]["kind"] == "word" and gapIssues[4] == []


def test_joined_letters_are_marked_letter_spacing():
    inkMask = draw_line()
    # Fill the gaps after letters 0-2 so four letters join (110 px wide; clusters must exceed 2 x 40 px)
    for gapStartPx in (50, 80, 110):
        inkMask[100:140, gapStartPx:gapStartPx + 10] = 255
    textLines = find_components(inkMask, find_text_lines(inkMask))
    cluster = next(c for line in textLines for c in line.components if c.kind == "cluster")
    componentIssues = find_component_issues(textLines, measure_x_height_px(inkMask, textLines), GOOD_SCORES)
    assert "letterSpacing" in componentIssues[cluster.componentId]


def test_weak_whole_page_feature_marks_every_letter():
    componentIssues, gapIssues, _ = issues_for(draw_line(), dict(GOOD_SCORES, textSize=0.4, strokeWeight=0.95))
    assert all(issueIds == ["textSize"] for issueIds in componentIssues)    # strokeWeight 0.95 is good enough
    assert all(issueIds == [] for issueIds in gapIssues)                   # size problems aren't gap problems


def test_unknown_x_height_gives_no_distance_based_marks():
    textLines = find_components(draw_line(offsetsPx={3: -15}), find_text_lines(draw_line(offsetsPx={3: -15})))
    componentIssues = find_component_issues(textLines, None, GOOD_SCORES)
    assert all("baselineConsistency" not in issueIds for issueIds in componentIssues.values())
    assert find_gap_issues(find_gaps(textLines), None) == [[] for _ in find_gaps(textLines)]
