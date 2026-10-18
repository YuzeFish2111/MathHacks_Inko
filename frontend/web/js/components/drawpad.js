import { h, icon } from "../ui.js";

// Strokes live in a fixed logical space so they survive resizes and rotate-the-phone.
const LW = 1000, LH = 620;
const SIZES = { thin: 4, medium: 7, thick: 11 };
const EXPORT_SCALE = 1.6;   // exported image is 1600 x 992 px

/** Write-on-screen pad: finger, mouse, or stylus (with pressure). The guide lines are
 *  a CSS background, so they never end up in the exported image. */
export function createDrawPad({ onSubmit }) {
  const canvas = h("canvas", { class: "draw-canvas", "aria-label": "Writing area. Write with your finger, mouse, or stylus." });
  const ctx = canvas.getContext("2d");
  const strokes = [];
  let current = null;
  let size = "medium";
  let penSeen = false;  // once a stylus is used, ignore palm touches

  const sizeButtons = Object.keys(SIZES).map((key) => {
    const b = h("button", { type: "button", "aria-pressed": String(key === size), "aria-label": `${key} pen`, title: `${key} pen` },
      h("span", { class: `pen-dot pen-${key}` }));
    b.addEventListener("click", () => { size = key; sizeButtons.forEach((x) => x.setAttribute("aria-pressed", String(x === b))); });
    return b;
  });
  const undoBtn = h("button", { class: "btn btn-small btn-soft", type: "button" }, icon("undo"), "Undo");
  const clearBtn = h("button", { class: "btn btn-small btn-soft", type: "button" }, icon("trash"), "Clear");
  const submitBtn = h("button", { class: "btn btn-big", type: "button" }, icon("sparkle"), "Analyze my writing");
  const hint = h("p", { class: "draw-hint" }, "Write a sentence or two in your normal handwriting. Bigger is better!");

  const el = h("div", { class: "draw-pad" },
    hint,
    h("div", { class: "draw-surface" }, canvas),
    h("div", { class: "draw-tools" },
      h("div", { class: "segmented pen-sizes", role: "group", "aria-label": "Pen size" }, sizeButtons),
      undoBtn, clearBtn),
    submitBtn,
  );

  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    redraw();
  }

  function drawStroke(c, stroke, scale) {
    const pts = stroke.points;
    c.strokeStyle = "#141414";
    c.lineCap = "round";
    c.lineJoin = "round";
    if (pts.length === 1) {
      c.beginPath();
      c.fillStyle = "#141414";
      c.arc(pts[0].x * scale, pts[0].y * scale, (stroke.width * pts[0].p * scale) / 2, 0, Math.PI * 2);
      c.fill();
      return;
    }
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i];
      const mid0 = i > 1 ? { x: (pts[i - 2].x + a.x) / 2, y: (pts[i - 2].y + a.y) / 2 } : a;
      const mid1 = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      c.beginPath();
      c.lineWidth = stroke.width * ((a.p + b.p) / 2) * scale;
      c.moveTo(mid0.x * scale, mid0.y * scale);
      c.quadraticCurveTo(a.x * scale, a.y * scale, mid1.x * scale, mid1.y * scale);
      c.stroke();
    }
    const last = pts[pts.length - 1], prev = pts[pts.length - 2];
    c.beginPath();
    c.moveTo(((prev.x + last.x) / 2) * scale, ((prev.y + last.y) / 2) * scale);
    c.lineTo(last.x * scale, last.y * scale);
    c.stroke();
  }

  function redraw() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const scale = canvas.width / LW;
    strokes.forEach((s) => drawStroke(ctx, s, scale));
    if (current) drawStroke(ctx, current, scale);
    undoBtn.disabled = clearBtn.disabled = !strokes.length;
  }

  function point(e) {
    const rect = canvas.getBoundingClientRect();
    const pressure = e.pointerType === "pen" && e.pressure > 0 ? 0.55 + e.pressure * 0.9 : 1;
    return { x: ((e.clientX - rect.left) / rect.width) * LW, y: ((e.clientY - rect.top) / rect.height) * LH, p: pressure };
  }

  canvas.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "pen") penSeen = true;
    if (penSeen && e.pointerType === "touch") return;
    if (e.button > 0) return;
    e.preventDefault();
    canvas.setPointerCapture(e.pointerId);
    current = { width: SIZES[size], points: [point(e)], id: e.pointerId };
    redraw();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!current || e.pointerId !== current.id) return;
    e.preventDefault();
    const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    for (const ev of events.length ? events : [e]) current.points.push(point(ev));
    redraw();
  });
  const finish = (e) => {
    if (!current || e.pointerId !== current.id) return;
    strokes.push(current);
    current = null;
    redraw();
  };
  canvas.addEventListener("pointerup", finish);
  canvas.addEventListener("pointercancel", finish);

  undoBtn.addEventListener("click", () => { strokes.pop(); redraw(); });
  clearBtn.addEventListener("click", () => { strokes.length = 0; redraw(); });
  submitBtn.addEventListener("click", async () => {
    if (!strokes.length) {
      hint.textContent = "Write something first, then tap Analyze.";
      hint.classList.add("nudge");
      return;
    }
    onSubmit(await exportBlob());
  });

  function exportBlob() {
    const out = document.createElement("canvas");
    out.width = LW * EXPORT_SCALE;
    out.height = LH * EXPORT_SCALE;
    const c = out.getContext("2d");
    c.fillStyle = "#fff";
    c.fillRect(0, 0, out.width, out.height);
    strokes.forEach((s) => drawStroke(c, s, EXPORT_SCALE));
    return new Promise((resolve) => out.toBlob((blob) => resolve(new File([blob], "drawing.png", { type: "image/png" })), "image/png"));
  }

  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  redraw();

  return {
    el,
    undo: () => { strokes.pop(); redraw(); },
    get hasInk() { return strokes.length > 0; },
  };
}
