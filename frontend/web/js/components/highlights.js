import { PAGE_WIDE_FEATURES } from "../features.js";

const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/** Overlay drawn over analysis.rectifiedImage. Coordinates are rectifiedImage pixels
 *  (overlayData.imageWidthPx × imageHeightPx); the SVG viewBox uses the same space, so the
 *  marks line up at any display size without listening for resizes.
 *
 *  Layers (independent toggles): "lines" (baseline solid, x-height dashed), "letters" (boxes
 *  around letters), "gaps" (boxes between letters; word gaps are skipped).
 *  select(featureId) marks the boxes whose issueFeatureIds include it with a thick dashed
 *  outline and a "!" marker; page-wide features tint every letter instead. */
export function createHighlights(analysis) {
  const overlay = analysis.overlayData;
  const W = overlay.imageWidthPx, H = overlay.imageHeightPx;
  const layer = el("svg", { class: "overlay", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  const groups = {
    letters: el("g", { class: "ov-letters" }),
    gaps: el("g", { class: "ov-gaps" }),
    lines: el("g", { class: "ov-lines" }),
    marks: el("g", { class: "ov-marks" }),
  };
  layer.append(groups.letters, groups.gaps, groups.lines, groups.marks);

  for (const line of overlay.lines) {
    groups.lines.append(el("line", {
      class: line.kind === "baseline" ? "ov-baseline" : "ov-xheight",
      x1: line.x1Px, y1: line.y1Px, x2: line.x2Px, y2: line.y2Px,
    }));
  }
  const boxes = [];
  const addBox = (group, cls, item) => {
    const rect = el("rect", { class: cls, x: item.xPx, y: item.yPx, width: Math.max(1, item.widthPx), height: Math.max(1, item.heightPx) });
    groups[group].append(rect);
    boxes.push({ rect, item, group });
  };
  overlay.components.forEach((c) => addBox("letters", "ov-letter", c));
  overlay.gaps.filter((g) => g.kind === "letter").forEach((g) => addBox("gaps", "ov-gap", g));

  const markSize = Math.max(14, Math.round(W / 55));

  return {
    layer,
    /** How many boxes show a problem with featureId, optionally only in one layer ("letters" or "gaps"). */
    count(featureId, group = null) {
      return boxes.filter((b) => (!group || b.group === group) && b.item.issueFeatureIds.includes(featureId)).length;
    },
    setVisible(name, visible) {
      groups[name].classList.toggle("hidden", !visible);
    },
    select(featureId) {
      groups.marks.replaceChildren();
      layer.classList.toggle("page-tint", PAGE_WIDE_FEATURES.has(featureId) && this.count(featureId) > 0);
      for (const { rect, item } of boxes) {
        const hit = !!featureId && !PAGE_WIDE_FEATURES.has(featureId) && item.issueFeatureIds.includes(featureId);
        rect.classList.toggle("issue", hit);
        if (!hit) continue;
        const cx = item.xPx + item.widthPx / 2;
        const cy = Math.max(markSize * 0.7, item.yPx - markSize * 0.75);
        groups.marks.append(
          el("circle", { class: "ov-mark", cx, cy, r: markSize * 0.6 }),
          Object.assign(el("text", { class: "ov-mark-text", x: cx, y: cy, "font-size": markSize, "text-anchor": "middle", "dominant-baseline": "central" }), { textContent: "!" }),
        );
      }
    },
  };
}
