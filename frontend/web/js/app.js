import { icons } from "./icons.js";
import { applyTheme } from "./theme.js";
import { h, openDialog } from "./ui.js";
import { openSettings } from "./components/settings.js";
import { initAccount } from "./components/account.js";
import { initInstall } from "./components/install.js";
import * as home from "./pages/home.js";
import * as decoder from "./pages/decoder.js";
import * as practice from "./pages/practice.js";
import * as progress from "./pages/progress.js";
import * as about from "./pages/about.js";
import * as contact from "./pages/contact.js";

const PAGES = { home, decoder, practice, progress, about, contact };
const TITLES = { home: "Inko", decoder: "Decoder", practice: "Practice", progress: "Progress", about: "About Us", contact: "Contact Us" };
const mounted = new Set();
let currentPage = null;

applyTheme();

function fillIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icons[el.dataset.icon] || ""; });
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  const name = PAGES[path] ? path : "home";
  return { name, params: new URLSearchParams(query || "") };
}

function route() {
  // In-page anchors (like the skip link) are not routes.
  if (location.hash && !location.hash.startsWith("#/")) return;
  const { name, params } = parseHash();
  const changed = name !== currentPage;
  document.querySelectorAll(".page").forEach((section) => {
    const match = section.dataset.page === name;
    section.hidden = !match;
    if (match && !mounted.has(name)) {
      PAGES[name].mount(section);
      mounted.add(name);
    }
  });
  if (changed && currentPage && PAGES[currentPage].hide) PAGES[currentPage].hide();
  currentPage = name;
  PAGES[name].show && PAGES[name].show(params);
  document.querySelectorAll("[data-route]").forEach((link) => {
    if (link.dataset.route === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.title = name === "home" ? "Inko" : `${TITLES[name]} | Inko`;
  if (changed) window.scrollTo({ top: 0 });
}

export function navigate(path) {
  if (location.hash === `#/${path}`) route();
  else location.hash = `#/${path}`;
}

function openMore() {
  const link = (href, ic, label) => {
    const a = h("a", { href }, h("span", { class: "icon-tile", html: icons[ic] }), label);
    a.addEventListener("click", () => sheet.close());
    return a;
  };
  const sheet = openDialog({
    title: "More",
    body: h("div", { class: "sheet-links" }, link("#/about", "person", "About Us"), link("#/contact", "mail", "Contact Us")),
  });
}

function boot() {
  fillIcons();
  document.getElementById("settings-btn").innerHTML = icons.gear;
  document.getElementById("settings-btn").addEventListener("click", openSettings);
  document.getElementById("more-btn").addEventListener("click", openMore);
  window.addEventListener("hashchange", route);
  route();
  initAccount();
  initInstall();
}

boot();
