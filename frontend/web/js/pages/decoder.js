import { api } from "../api.js";
import { MSG } from "../messages.js";
import { h, icon, isPhoneLayout, isTouch, openDialog, sleep, toast } from "../ui.js";
import { rememberScores, state } from "../store.js";
import { openAuth } from "../components/account.js";
import { createMiggle } from "../components/miggle.js";
import { createPickers, exampleFile, prepareImage } from "../components/upload.js";
import { factorLabel, scoreCard } from "../components/results.js";
import { loadScoringModel, PAGE_WIDE_FEATURES } from "../features.js";
import { buildMessages } from "../components/feedback.js";
import { createHighlights } from "../components/highlights.js";
import { createDrawPad } from "../components/drawpad.js";

const MIN_LOADING_MS = 1800;   // long enough to read the loading line
const TIPS_KEY = "inko-tips-seen";

let uploadPanel, miggle, pickers, drawPad;
let busy = false;
let visible = false;
let mode = "photo";   // "photo" or "draw"

export function mount(el) {
  miggle = createMiggle();
  uploadPanel = h("div", { class: "panel upload-panel dashed" });
  el.append(h("div", { class: "card decoder" }, uploadPanel, miggle.panel));
  const fromPhoto = (file) => { mode = "photo"; handleFile(file); };
  pickers = createPickers(fromPhoto);
  drawPad = createDrawPad({ onSubmit: handleFile });
  setupDragAndDrop(uploadPanel, fromPhoto);
  document.addEventListener("keydown", (e) => {
    if (visible && mode === "draw" && drawPad.el.isConnected && (e.metaKey || e.ctrlKey) && e.key === "z") {
      e.preventDefault();
      drawPad.undo();
    }
  });
  window.addEventListener("paste", onPaste);
  renderEmpty();
  intro();
}

export function show(params) {
  visible = true;
  if (params.get("example") === "1") {
    history.replaceState(null, "", "#/decoder");
    runExample();
  }
  const saved = params.get("r");
  if (saved) {
    history.replaceState(null, "", "#/decoder");
    openSaved(saved);
  }
}

export function hide() {
  visible = false;
}

// ---------- Picking a photo ----------

function withTips(open) {
  let seen = false;
  try { seen = sessionStorage.getItem(TIPS_KEY) === "1"; } catch (e) { /* ignore */ }
  if (seen) return open();
  const go = h("button", { class: "btn btn-big", type: "button", autofocus: true }, "Got it");
  const { close } = openDialog({
    title: "Quick tips",
    body: h("div", {}, h("p", { class: "tip-card", style: "margin-top:14px" }, MSG.tips), h("div", { class: "row", style: "margin-top:20px" }, go)),
  });
  go.addEventListener("click", () => {
    try { sessionStorage.setItem(TIPS_KEY, "1"); } catch (e) { /* ignore */ }
    open();      // must run inside the click so phones allow the picker to open
    close();
  });
}

const chooseFile = () => withTips(() => pickers.chooseFile());
const openCamera = () => withTips(() => pickers.openCamera());

async function runExample() {
  if (busy) return;
  try {
    mode = "photo";
    handleFile(await exampleFile());
  } catch (e) {
    showError(e);
  }
}

function setupDragAndDrop(zone, onFile) {
  let depth = 0;
  zone.addEventListener("dragenter", (e) => { e.preventDefault(); depth += 1; zone.classList.add("dragging"); });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  zone.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) zone.classList.remove("dragging"); });
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    zone.classList.remove("dragging");
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) onFile(file);
  });
  // A photo dropped next to the box should not make the browser open it instead.
  window.addEventListener("dragover", (e) => { if (visible) e.preventDefault(); });
  window.addEventListener("drop", (e) => { if (visible) e.preventDefault(); });
}

function onPaste(e) {
  if (!visible || busy) return;
  const item = [...(e.clipboardData?.items || [])].find((i) => i.kind === "file" && i.type.startsWith("image/"));
  if (item) { mode = "photo"; handleFile(item.getAsFile()); }
}

// ---------- Analysis flow ----------

async function openSaved(id) {
  if (busy) return;
  busy = true;
  renderLoading(null);
  miggle.clear();
  try {
    await showResult(await api.historyItem(id));
  } catch (e) {
    showError(e);
  } finally {
    busy = false;
  }
}

async function handleFile(file) {
  if (busy || !file) return;
  busy = true;
  let prepared;
  try {
    prepared = await prepareImage(file);
  } catch (e) {
    busy = false;
    return showError(e);
  }
  renderLoading(prepared.previewUrl);
  miggle.clear();
  const dots = miggle.typing();
  const started = Date.now();
  try {
    const result = await api.analyze(prepared.blob, prepared.name);
    await sleep(Math.max(0, MIN_LOADING_MS - (Date.now() - started)));
    dots.remove();
    await renderResult(result);
  } catch (e) {
    dots.remove();
    showError(e);
  } finally {
    busy = false;
    if (prepared.previewUrl) setTimeout(() => URL.revokeObjectURL(prepared.previewUrl), 5000);
  }
}

function showError(err) {
  const message = (err && err.message) || MSG.analysis_failed;
  renderEmpty(message);
  miggle.clear();
  miggle.say(message, { cls: "warning" });
  miggle.say("Want to try again? Pick another photo, or tap Try an example to see how it works.");
}

// ---------- Rendering ----------

function intro() {
  miggle.clear();
  miggle.sequence([
    { content: "Hey, I’m Miggle! I’m here to help your handwriting shine." },
    { content: h("span", {},
        h("span", { class: "desktop-text" }, "Drop an image on the left, and I’ll read it and show you how to make it clearer."),
        h("span", { class: "phone-text" }, "Drop an image above, and I’ll read it and show you how to make it clearer.")) },
    { content: "Feedback on how to improve your writing will also be provided!" },
  ], { pause: 260 });
}

function uploadButtons() {
  return h("div", { class: "upload-actions" },
    h("button", { class: "btn btn-big", type: "button", onclick: chooseFile },
      h("span", { class: "no-touch" }, "Select a file"), h("span", { class: "only-touch" }, "Select a file or photo")),
    h("button", { class: "btn btn-accent only-touch", type: "button", onclick: openCamera }, icon("camera"), "Take a photo"),
    h("button", { class: "btn btn-soft example-btn", type: "button", onclick: runExample }, icon("sparkle"), "Try an example"),
  );
}

function modeSwitch() {
  const make = (value, ic, label) => {
    const b = h("button", { type: "button", "aria-pressed": String(mode === value) }, icon(ic), label);
    b.addEventListener("click", () => { mode = value; renderEmpty(); });
    return b;
  };
  return h("div", { class: "mode-switch", role: "group", "aria-label": "How to add your handwriting" },
    make("photo", "image", "Photo"), make("draw", "pen", "Write on screen"));
}

function writeOnScreen() {
  mode = "draw";
  renderEmpty();
}

function renderEmpty(error) {
  const errorNote = error ? h("p", { class: "form-error", role: "alert", style: "text-align:center" }, error) : null;
  if (mode === "draw") {
    uploadPanel.replaceChildren(modeSwitch(), errorNote || "", drawPad.el);
    return;
  }
  uploadPanel.replaceChildren(
    modeSwitch(),
    h("div", { class: "upload-empty" },
      h("button", { class: "plus-circle", type: "button", "aria-label": "Choose a photo", onclick: chooseFile }, icon("plus")),
      h("div", { class: "drag-text no-touch" }, "Drag an image here"),
      h("div", { class: "or-upload no-touch" }, "OR UPLOAD"),
      h("div", { class: "drag-text only-touch" }, "Add your handwriting"),
      errorNote,
      uploadButtons(),
      h("p", { class: "upload-tip" }, MSG.tips),
    ),
  );
}

function renderLoading(previewUrl) {
  const frame = previewUrl
    ? h("div", { class: "photo-frame busy" }, h("img", { src: previewUrl, alt: "Your handwriting photo" }), h("div", { class: "scan-line" }))
    : h("div", { class: "photo-frame busy photo-placeholder" }, "Getting your photo ready", h("div", { class: "scan-line" }));
  uploadPanel.replaceChildren(h("div", { class: "photo-stage" }, frame, h("p", { class: "loading-note", role: "status" }, MSG.loading)));
}

function renderResult(result) {
  if (result.analysis.status === "needs_better_photo") return renderRetake(result);
  if (result.photo_check && result.photo_check.tilted) return renderTilted(result);
  return showResult(result);
}

// Plain-language names for the backend's qualityChecks (checkId values from the contract).
const CHECK_LABELS = {
  fileType: "Photo file type", fileSize: "File size", decode: "Opens as an image", imageSize: "Big enough",
  pageBounds: "Page edges", inkAmount: "Enough writing", contrast: "Dark ink on light paper",
  blur: "Sharp, not blurry", segmentation: "Letters clearly separate",
};

function retakeActions() {
  return h("div", { class: "stage-actions" },
    h("button", { class: "btn", type: "button", onclick: () => { mode = "photo"; (isTouch() ? openCamera : chooseFile)(); } },
      icon("camera"), "Take another photo"),
    h("button", { class: "btn btn-soft", type: "button", onclick: () => { mode = "photo"; chooseFile(); } }, icon("image"), "Choose a file"),
    h("button", { class: "btn btn-soft", type: "button", onclick: writeOnScreen }, icon("pen"), "Write on screen"));
}

/** status "needs_better_photo": the backend's message, what it checked, and a way to retry. */
function renderRetake(result) {
  const a = result.analysis;
  const checks = h("ul", { class: "check-list", "aria-label": "Photo checks" },
    a.qualityChecks.map((check) => h("li", { class: check.passed ? "passed" : "failed" },
      h("span", { class: "check-mark", "aria-hidden": "true" }, check.passed ? "✓" : "✗"),
      h("span", {}, h("b", {}, CHECK_LABELS[check.checkId] || check.checkId), check.passed ? ": passed" : ": needs a fix"))));
  uploadPanel.replaceChildren(
    h("div", { class: "photo-stage" },
      h("div", { class: "tilt-card retake-card", role: "alert" }, h("p", {}, a.error.message)),
      checks,
      retakeActions(),
      h("p", { class: "upload-tip" }, MSG.tips)));
  miggle.clear();
  miggle.sequence([
    { content: a.error.message, opts: { cls: "warning" } },
    { content: "No score this time, because a score from this photo wouldn’t be fair to you. Try again with the tips under the photo checks." },
  ]);
}

/** Tilted photo: ask for a retake first, but let people continue if they want. */
function renderTilted(result) {
  const retake = h("button", { class: "btn", type: "button" }, icon("camera"), "Retake photo");
  retake.addEventListener("click", () => (isTouch() ? openCamera() : chooseFile()));
  const anyway = h("button", { class: "link-btn", type: "button" }, "Use this photo anyway");
  anyway.addEventListener("click", () => { showResult(result); onUseAnyway(result); });
  uploadPanel.replaceChildren(
    h("div", { class: "photo-stage" },
      h("div", { class: "photo-frame tilt-preview" }, h("img", { src: result.analysis.rectifiedImage, alt: "Your tilted photo" })),
      h("div", { class: "tilt-card", role: "alert" }, h("p", {}, MSG.angle_warning), h("div", { class: "row" }, retake, anyway)),
    ),
  );
  miggle.clear();
  miggle.sequence([
    { content: MSG.angle_warning, opts: { cls: "warning" } },
    { content: "Hold your phone flat, right above the page, like you\u2019re taking a photo of a pizza from the top." },
  ]);
}

function overlayCaption(highlights, featureId) {
  if (!featureId) return "Tap a feature or a tip to see where it shows up on your page.";
  const label = factorLabel(featureId);
  if (PAGE_WIDE_FEATURES.has(featureId)) {
    return highlights.count(featureId)
      ? `${label} applies to your whole page, so every letter is tinted.`
      : `${label} looks fine across your page, so nothing is marked.`;
  }
  const n = highlights.count(featureId);
  return n
    ? `${label}: ${n} ${n === 1 ? "spot is" : "spots are"} marked with “!” and a thick dashed outline.`
    : `${label}: nothing to mark on your page.`;
}

async function showResult(result) {
  const model = await loadScoringModel();
  rememberScores(result);
  const a = result.analysis;
  const refs = {};
  const highlights = createHighlights(a);
  const caption = h("p", { class: "overlay-caption", role: "status" }, overlayCaption(highlights, null));
  const frame = h("div", { class: "photo-frame" },
    h("img", { src: a.rectifiedImage, alt: "Your page, straightened, with letters, gaps and writing lines marked",
      width: a.overlayData.imageWidthPx, height: a.overlayData.imageHeightPx }),
    highlights.layer);

  // Three independent layers, as the plan asks: Size (letter boxes), Spacing (gaps), lines.
  const layerBoxes = {};
  const setLayer = (name, on) => { highlights.setVisible(name, on); layerBoxes[name].checked = on; };
  const toggle = (name, label, swatch, on) => {
    const input = h("input", { type: "checkbox" });
    input.checked = on;
    input.addEventListener("change", () => highlights.setVisible(name, input.checked));
    layerBoxes[name] = input;
    highlights.setVisible(name, on);
    return h("label", { class: "layer-toggle" }, input, h("i", { class: `swatch ${swatch}`, "aria-hidden": "true" }), label);
  };
  const toggles = h("fieldset", { class: "layer-toggles" },
    h("legend", { class: "visually-hidden" }, "Show on the photo"),
    toggle("letters", "Size (letter boxes)", "sw-letter", true),
    toggle("gaps", "Spacing (gaps)", "sw-gap", false),
    toggle("lines", "Baseline (solid) / x-height (dashed)", "sw-lines", true));

  let selected = null;
  const pick = (id, from) => {
    selected = selected === id && from === "meter" ? null : id;   // tap a feature again to clear it
    highlights.select(selected);
    if (selected && highlights.count(selected, "letters")) setLayer("letters", true);
    if (selected && highlights.count(selected, "gaps")) setLayer("gaps", true);
    if (selected && PAGE_WIDE_FEATURES.has(selected)) setLayer("letters", true);
    Object.entries(refs).forEach(([key, el]) => el.classList.toggle("active", !!selected && (key === selected || key === `tip-${selected}`)));
    caption.textContent = overlayCaption(highlights, selected);
    if (isPhoneLayout()) frame.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  uploadPanel.replaceChildren(
    h("div", { class: "photo-stage" },
      frame,
      caption,
      h("div", { class: "photo-tools" }, toggles),
      h("div", { class: "stage-actions" },
        h("button", { class: "btn btn-small", type: "button", onclick: () => { mode = "photo"; chooseFile(); } }, icon("image"), "New photo"),
        h("button", { class: "btn btn-small btn-soft", type: "button", onclick: writeOnScreen }, icon("pen"), mode === "draw" ? "Write again" : "Write on screen"),
        h("button", { class: "btn btn-small btn-accent only-touch", type: "button", onclick: openCamera }, icon("camera"), "Camera"),
        h("button", { class: "btn btn-small btn-soft", type: "button", onclick: runExample }, icon("sparkle"), "Example"),
      ),
    ),
  );

  const items = [
    { content: scoreCard(result, { model, onPick: (id) => pick(id, "meter"), refs }), opts: { wide: true, cls: "flush" } },
    ...buildMessages(result, { onPick: (id) => pick(id, "tip"), refs, highlights }),
  ];
  if (!state.user) {
    items.push({ content: h("div", {}, "Sign in to save this scan and track your progress over time!",
      h("div", { class: "bubble-actions" }, h("button", { class: "btn btn-small btn-accent", type: "button", onclick: () => openAuth("signup") }, "Sign in to save"))) });
  }
  miggle.clear();
  miggle.sequence(items);
  if (result.saved && result.created_at && Date.now() - Date.parse(result.created_at) < 60000) toast("Saved to your progress.");
}

/** "Use this photo anyway" on a tilted photo: keep it in Progress too. */
async function onUseAnyway(result) {
  if (!state.user || result.saved) return;
  try {
    await api.saveResult(result.result_id);
    result.saved = true;
    toast("Saved to your progress.");
  } catch (e) { /* not saved, still shown */ }
}
