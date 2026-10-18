import { icons } from "./icons.js";

/** Tiny element builder: h("div", {class: "x", onclick: fn}, "text", child). Strings
 *  become text nodes (never HTML), except the `html` attribute for trusted icon markup. */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "html") el.innerHTML = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export const icon = (name, cls = "") => h("span", { class: `icon ${cls}`.trim(), html: icons[name] || "", "aria-hidden": "true" });

export function toast(text, { error = false, ms = 3200 } = {}) {
  const host = document.querySelector(".toast-host");
  const el = h("div", { class: `toast${error ? " error" : ""}`, role: error ? "alert" : "status" }, text);
  host.append(el);
  setTimeout(() => el.remove(), ms);
}

let openDialogs = 0;

/** Modal dialog on desktop, bottom sheet on phones. `anchored` drops it under the top bar. */
export function openDialog({ title, body, anchored = false, onClose, label }) {
  const previous = document.activeElement;
  const closeBtn = h("button", { class: "close-x", type: "button", "aria-label": "Close", html: icons.close });
  const dialog = h("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": label || title },
    closeBtn, title ? h("h2", {}, title) : null, body);
  const backdrop = h("div", { class: `overlay-backdrop${anchored ? " anchored" : ""}` }, dialog);

  function close() {
    if (!backdrop.isConnected) return;
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
    openDialogs -= 1;
    if (!openDialogs) document.body.style.overflow = "";
    onClose && onClose();
    previous && previous.focus && previous.focus({ preventScroll: true });
  }
  function onKey(e) {
    if (e.key === "Escape") close();
    if (e.key === "Tab") {
      const items = dialog.querySelectorAll("button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }
  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("pointerdown", (e) => { if (e.target === backdrop) close(); });
  document.addEventListener("keydown", onKey);
  document.body.append(backdrop);
  openDialogs += 1;
  document.body.style.overflow = "hidden";
  const autofocus = dialog.querySelector("[autofocus]") || dialog.querySelector("input, button:not(.close-x)") || closeBtn;
  setTimeout(() => autofocus.focus({ preventScroll: true }), 30);
  return { close, dialog };
}

export function confirmDialog({ title, text, confirmText = "Yes", danger = false }) {
  return new Promise((resolve) => {
    let answered = false;
    const yes = h("button", { class: `btn ${danger ? "btn-danger" : ""}`, type: "button" }, confirmText);
    const no = h("button", { class: "btn btn-soft", type: "button" }, "Cancel");
    const { close } = openDialog({
      title,
      body: h("div", {}, h("p", { style: "margin-top:10px" }, text), h("div", { class: "row", style: "margin-top:22px" }, yes, no)),
      onClose: () => { if (!answered) resolve(false); },
    });
    yes.addEventListener("click", () => { answered = true; close(); resolve(true); });
    no.addEventListener("click", () => close());
  });
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function initials(name = "") {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase() || "?";
}

export function avatarEl(user, cls = "avatar") {
  if (user && user.avatar_url) return h("span", { class: cls }, h("img", { src: user.avatar_url, alt: "" }));
  return h("span", { class: cls }, initials(user ? user.name : ""));
}

export const isTouch = () => window.matchMedia("(hover: none) and (pointer: coarse)").matches;
export const isPhoneLayout = () => window.matchMedia("(max-width: 899px)").matches;
