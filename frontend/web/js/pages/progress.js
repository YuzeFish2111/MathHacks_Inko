import { api } from "../api.js";
import { MSG } from "../messages.js";
import { on, state } from "../store.js";
import { h, icon } from "../ui.js";
import { openAuth } from "../components/account.js";
import { factorKeys, factorLabel } from "../components/results.js";

const SVG = "http://www.w3.org/2000/svg";
let root, visible = false, items = [], chartHost = null, resizeTimer = null;

export function mount(el) {
  root = h("div", {});
  el.append(root);
  on("user", () => visible && load());
  on("history-changed", () => visible && load());
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => visible && chartHost && drawChart(chartHost), 150);
  });
}

export function show() { visible = true; load(); }
export function hide() { visible = false; }

async function load() {
  if (!state.user) return renderGuest();
  if (!items.length) root.replaceChildren(h("div", { class: "card" }, h("h1", { class: "page-title" }, "Progress"), h("p", { class: "page-sub" }, "Loading your scans…")));
  try {
    items = (await api.history()).items;
  } catch (e) {
    return root.replaceChildren(h("div", { class: "card" }, h("h1", { class: "page-title" }, "Progress"), h("p", { class: "form-error" }, e.message)));
  }
  items.length ? render() : renderEmpty();
}

function renderGuest() {
  items = [];
  root.replaceChildren(h("div", { class: "card guest-card" },
    h("img", { src: "img/logo-mark.png", alt: "", width: 96, height: 96 }),
    h("h1", { class: "page-title" }, MSG.guest_progress),
    h("p", { class: "page-sub" }, "Save every scan to your account and watch your score climb. You can still use the Decoder as a guest anytime."),
    h("div", { class: "btn-pair center stack-phone", style: "margin-top:22px" },
      h("button", { class: "btn btn-big", type: "button", onclick: () => openAuth("signin") }, "Sign In"),
      h("button", { class: "btn btn-big btn-soft", type: "button", onclick: () => openAuth("signup") }, "Create Account"))));
}

function renderEmpty() {
  root.replaceChildren(h("div", { class: "card guest-card" },
    h("img", { src: "img/logo-mark.png", alt: "", width: 96, height: 96 }),
    h("h1", { class: "page-title" }, "No scans yet"),
    h("p", { class: "page-sub" }, `Hi ${state.user.name.split(" ")[0]}! Scan your first handwriting sample and it will show up here.`),
    h("div", { class: "row", style: "justify-content:center;margin-top:22px" },
      h("a", { class: "btn btn-big", href: "#/decoder" }, "Open the Decoder", icon("arrow")))));
}

const fmtDate = (iso, opts = { month: "short", day: "numeric" }) => new Date(iso).toLocaleDateString(undefined, opts);
const fmtFull = (iso) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function delta(now, then) {
  const d = now - then;
  return d === 0 ? "No change" : `${d > 0 ? "+" : "−"}${Math.abs(d)}`;
}

function render() {
  const first = items[0], last = items[items.length - 1];
  const best = Math.max(...items.map((i) => i.overall_score));
  const change = last.overall_score - first.overall_score;
  const tiles = h("div", { class: "stat-row" },
    stat("Latest score", last.overall_score, `on ${fmtDate(last.created_at)}`),
    stat("Best score", best, best === last.overall_score && items.length > 1 ? "That’s your latest!" : "Your personal best"),
    stat("Change since first", items.length > 1 ? delta(last.overall_score, first.overall_score) : "Not yet",
      items.length > 1 ? (change > 0 ? "You’re improving!" : change < 0 ? "Keep practicing, you’ve got this" : "Holding steady") : "Scan again to compare", change > 0 ? "up" : change < 0 ? "down" : ""),
    stat("Samples", items.length, items.length === 1 ? "scan saved" : "scans saved"),
  );

  chartHost = h("div", { class: "chart-host" });
  const chartCard = h("section", { class: "card" },
    h("h2", { class: "section-title" }, "Overall score over time"),
    h("p", { class: "muted", style: "margin:-10px 0 14px" }, "Out of 100, one point per scan. Hover or tap the chart for details."),
    chartHost);

  const keys = factorKeys(last.scores);
  const multiples = h("section", { class: "card" },
    h("h2", { class: "section-title" }, "Each factor"),
    h("div", { class: "multiples" }, keys.map((key) => factorTile(key))));

  const list = h("section", { class: "card" },
    h("h2", { class: "section-title" }, "Past samples"),
    h("ul", { class: "sample-list" }, [...items].reverse().map((item) =>
      h("li", {},
        h("a", { href: `#/decoder?r=${encodeURIComponent(item.id)}`, class: "sample" },
          h("img", { src: item.thumb_url, alt: "", loading: "lazy" }),
          h("div", { class: "sample-main" },
            h("div", { class: "sample-date" }, fmtFull(item.created_at)),
            h("div", { class: "sample-factors" }, factorKeys(item.scores).map((k) => h("span", {}, `${factorLabel(k)} ${item.scores[k]}`)))),
          h("div", { class: "sample-score" }, h("b", {}, String(item.overall_score)), h("small", {}, "/100")),
          h("span", { class: "sample-go", "aria-hidden": "true" }, icon("arrow")))))));

  root.replaceChildren(
    h("div", { class: "card" }, h("h1", { class: "page-title" }, "Progress"),
      h("p", { class: "page-sub" }, `Nice to see you, ${state.user.name.split(" ")[0]}. Here’s how your handwriting is coming along.`), tiles),
    chartCard, multiples, list);
  drawChart(chartHost);
}

function stat(label, value, sub, dir = "") {
  return h("div", { class: "stat" },
    h("div", { class: "stat-label" }, label),
    h("div", { class: `stat-value ${dir}` }, dir === "up" ? icon("progress") : null, String(value)),
    h("div", { class: "stat-sub" }, sub));
}

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

/** Single-series line chart: 2px line, light wash, end dot with a surface ring,
 *  hairline grid, and a crosshair that snaps to the nearest scan. */
function drawChart(host) {
  const width = Math.max(280, host.clientWidth || 600);
  const height = width < 520 ? 220 : 280;
  const pad = { l: 34, r: 44, t: 14, b: 30 };
  const iw = width - pad.l - pad.r, ih = height - pad.t - pad.b;
  const n = items.length;
  const x = (i) => pad.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => pad.t + ih - (v / 100) * ih;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, width, height, class: "line-chart", role: "img",
    "aria-label": `Overall score over ${n} scans, from ${items[0].overall_score} to ${items[n - 1].overall_score}` });
  for (const v of [0, 25, 50, 75, 100]) {
    svg.append(svgEl("line", { x1: pad.l, x2: width - pad.r, y1: y(v), y2: y(v), class: "grid" }));
    const t = svgEl("text", { x: pad.l - 8, y: y(v) + 4, class: "tick", "text-anchor": "end" });
    t.textContent = String(v);
    svg.append(t);
  }
  const labelIdx = n === 1 ? [0] : [0, n - 1];
  const sameDay = fmtDate(items[0].created_at) === fmtDate(items[n - 1].created_at);
  for (const i of labelIdx) {
    const t = svgEl("text", { x: x(i), y: height - 8, class: "tick", "text-anchor": n === 1 ? "middle" : i === 0 ? "start" : "end" });
    t.textContent = sameDay && n > 1
      ? new Date(items[i].created_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
      : fmtDate(items[i].created_at);
    svg.append(t);
  }
  const pts = items.map((it, i) => [x(i), y(it.overall_score)]);
  if (n > 1) {
    const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
    svg.append(svgEl("path", { d: `${line}L${pts[n - 1][0]},${y(0)}L${pts[0][0]},${y(0)}Z`, class: "area" }));
    svg.append(svgEl("path", { d: line, class: "line" }));
  }
  const [ex, ey] = pts[n - 1];
  svg.append(svgEl("circle", { cx: ex, cy: ey, r: 5.5, class: "end-dot" }));
  const endLabel = svgEl("text", { x: ex + 10, y: ey + 5, class: "end-label" });
  endLabel.textContent = String(items[n - 1].overall_score);
  svg.append(endLabel);

  const cross = svgEl("line", { y1: pad.t, y2: pad.t + ih, class: "crosshair", visibility: "hidden" });
  const hoverDot = svgEl("circle", { r: 5, class: "end-dot", visibility: "hidden" });
  svg.append(cross, hoverDot);
  const tip = h("div", { class: "chart-tip", hidden: true });

  const showAt = (i) => {
    const it = items[i];
    cross.setAttribute("x1", pts[i][0]); cross.setAttribute("x2", pts[i][0]);
    cross.setAttribute("visibility", "visible");
    hoverDot.setAttribute("cx", pts[i][0]); hoverDot.setAttribute("cy", pts[i][1]);
    hoverDot.setAttribute("visibility", "visible");
    tip.replaceChildren(
      h("div", { class: "tip-value" }, String(it.overall_score), h("span", {}, " overall")),
      h("div", { class: "tip-date" }, fmtFull(it.created_at)),
      h("div", { class: "tip-factors" }, factorKeys(it.scores).map((k) => h("div", {}, h("b", {}, String(it.scores[k])), ` ${factorLabel(k)}`))));
    tip.hidden = false;
    // Beside the crosshair, on whichever side has room, so the line stays visible.
    const left = (pts[i][0] / width) * host.clientWidth;
    const onRight = left < host.clientWidth / 2;
    tip.style.left = `${onRight ? left + 14 : left - 14}px`;
    tip.style.transform = onRight ? "none" : "translateX(-100%)";
  };
  const hideTip = () => { cross.setAttribute("visibility", "hidden"); hoverDot.setAttribute("visibility", "hidden"); tip.hidden = true; };
  const nearest = (clientX) => {
    const rect = svg.getBoundingClientRect();
    const px = ((clientX - rect.left) / rect.width) * width;
    let best = 0;
    pts.forEach(([qx], i) => { if (Math.abs(qx - px) < Math.abs(pts[best][0] - px)) best = i; });
    return best;
  };
  svg.addEventListener("pointermove", (e) => showAt(nearest(e.clientX)));
  svg.addEventListener("pointerdown", (e) => showAt(nearest(e.clientX)));
  svg.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") hideTip(); });
  // Keyboard: arrow keys step through scans, same readout as hover.
  let focusIdx = n - 1;
  svg.setAttribute("tabindex", "0");
  svg.addEventListener("focus", () => showAt(focusIdx));
  svg.addEventListener("blur", hideTip);
  svg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      focusIdx = Math.max(0, Math.min(n - 1, focusIdx + (e.key === "ArrowRight" ? 1 : -1)));
      showAt(focusIdx);
    }
  });
  host.replaceChildren(svg, tip);
}

function factorTile(key) {
  const values = items.map((i) => i.scores[key]).filter((v) => typeof v === "number");
  const latest = values[values.length - 1];
  const w = 160, hgt = 44;
  const svg = svgEl("svg", { viewBox: `0 0 ${w} ${hgt}`, class: "spark", "aria-hidden": "true", preserveAspectRatio: "none" });
  if (values.length > 1) {
    const pts = values.map((v, i) => [(i / (values.length - 1)) * (w - 8) + 4, hgt - 4 - (v / 100) * (hgt - 8)]);
    svg.append(svgEl("path", { d: pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(""), class: "spark-line" }));
    const [lx, ly] = pts[pts.length - 1];
    svg.append(svgEl("circle", { cx: lx, cy: ly, r: 3.5, class: "spark-dot" }));
  }
  const d = values.length > 1 ? latest - values[0] : null;
  return h("div", { class: "factor-tile" },
    h("div", { class: "stat-label" }, factorLabel(key)),
    h("div", { class: "factor-tile-row" },
      h("div", { class: "stat-value" }, String(latest)),
      h("div", { class: "stat-sub" }, d === null ? "first scan" : `${delta(latest, values[0])} since first`)),
    svg);
}
