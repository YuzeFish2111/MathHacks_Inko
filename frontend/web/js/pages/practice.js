import { api } from "../api.js";
import { lastScores, on, state } from "../store.js";
import { h, icon, openDialog } from "../ui.js";
import { weakestFactor } from "../components/results.js";
import { FEATURES } from "../features.js";
import { WORKSHEETS, WORKSHEET_ORDER } from "../worksheets.js";

let root, visible = false;

export function mount(el) {
  root = h("div", {});
  el.append(root);
  on("result", () => visible && render());
  on("user", () => visible && render());
  on("history-changed", () => visible && render());
  window.addEventListener("afterprint", () => { document.getElementById("print-area").replaceChildren(); });
}

export function show() { visible = true; render(); }
export function hide() { visible = false; }

async function latest() {
  const local = lastScores();
  if (local && local.scores) return local;
  if (!state.user) return null;
  try {
    const { items } = await api.history();
    return items.length ? items[items.length - 1] : null;
  } catch (e) {
    return null;
  }
}

/** Worksheet key -> the lowest score among the features it practices (see FEATURES[...].worksheet). */
function worksheetScores(featureScores) {
  const out = {};
  for (const [featureId, info] of Object.entries(FEATURES)) {
    const score = featureScores[featureId];
    if (!info.worksheet || typeof score !== "number") continue;
    out[info.worksheet] = Math.min(score, out[info.worksheet] ?? 100);
  }
  return out;
}

async function render() {
  const result = await latest();
  const scores = worksheetScores((result && result.scores) || {});
  const weakest = weakestFactor(scores);
  // Weakest worksheet first, then the rest by score; look-alikes (no score) last.
  const order = [...WORKSHEET_ORDER].sort((a, b) => rank(a) - rank(b));
  function rank(key) {
    if (key === weakest) return -2;
    if (key === "lookalikes") return 200;
    return typeof scores[key] === "number" ? scores[key] : 150;
  }
  const title = (key) => WORKSHEETS[key].title;

  const intro = weakest
    ? h("p", { class: "page-sub" }, "Your focus is ", h("b", {}, `${title(weakest)} (${scores[weakest]})`),
        ". Print the worksheet, practice for 10 minutes, then scan it again in the Decoder to see your score move.")
    : h("p", { class: "page-sub" }, "Scan a sample in the Decoder and I’ll put the worksheet you need most at the top. Until then, here’s everything.");

  root.replaceChildren(
    h("div", { class: "card" },
      h("h1", { class: "page-title" }, "Practice"),
      intro,
      weakest ? h("div", { class: "row", style: "margin-top:20px" },
        h("button", { class: "btn btn-big", type: "button", onclick: () => printSheet(weakest) }, icon("printer"), `Print ${title(weakest)} worksheet`)) :
        h("div", { class: "row", style: "margin-top:20px" }, h("a", { class: "btn btn-big", href: "#/decoder" }, "Open the Decoder", icon("arrow")))),
    h("div", { class: "practice-grid" }, order.map((key) => practiceCard(key, scores[key], key === weakest))),
    h("p", { class: "muted", style: "text-align:center;margin-top:18px;font-size:14px" }, "Tip: in the print window you can also choose Save as PDF."),
  );
}

function practiceCard(key, score, focus) {
  const sheet = WORKSHEETS[key];
  const preview = h("button", { class: "sheet-preview", type: "button", "aria-label": `Preview the ${sheet.title} worksheet`, html: sheet.build() });
  preview.addEventListener("click", () => openPreview(key));
  return h("article", { class: `card practice-card${focus ? " is-focus" : ""}` },
    h("div", { class: "practice-head" },
      h("h2", {}, sheet.title),
      typeof score === "number" ? h("span", { class: "score-chip" }, `${score}/100`) : null,
      focus ? h("span", { class: "focus-tag" }, "Your focus") : null),
    h("ul", { class: "practice-tips" }, sheet.tips.map((t) => h("li", {}, t))),
    preview,
    h("div", { class: "btn-pair" },
      h("button", { class: "btn btn-small", type: "button", onclick: () => printSheet(key) }, icon("printer"), "Print worksheet"),
      h("button", { class: "btn btn-small btn-soft", type: "button", onclick: () => openPreview(key) }, icon("eye"), "Preview")));
}

function openPreview(key) {
  const sheet = WORKSHEETS[key];
  const print = h("button", { class: "btn", type: "button" }, icon("printer"), "Print");
  const { close } = openDialog({
    title: `${sheet.title} worksheet`,
    body: h("div", {}, h("div", { class: "sheet-large", html: sheet.build() }), h("div", { class: "row", style: "margin-top:16px" }, print)),
  });
  print.addEventListener("click", () => { close(); printSheet(key); });
}

function printSheet(key) {
  const area = document.getElementById("print-area");
  area.innerHTML = WORKSHEETS[key].build();
  // Let the browser lay out the sheet (and load the font) before the print dialog opens.
  requestAnimationFrame(() => setTimeout(() => window.print(), 60));
}
