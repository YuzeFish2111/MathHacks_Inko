import { icons } from "../icons.js";
import { h, icon, toast } from "../ui.js";
import { addSettingsSection } from "./settings.js";

const HINT_KEY = "inko-install-hint-dismissed";
let deferredPrompt = null;
let banner = null;

const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
// iPadOS reports itself as a Mac, so also check for a touch screen.
const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

function dismissed() {
  try { return localStorage.getItem(HINT_KEY) === "1"; } catch (e) { return false; }
}

function hideBanner(remember) {
  if (banner) banner.remove();
  banner = null;
  if (remember) { try { localStorage.setItem(HINT_KEY, "1"); } catch (e) { /* ignore */ } }
}

async function promptInstall() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  deferredPrompt = null;
  hideBanner(outcome === "accepted");
}

function showBanner(content) {
  if (banner || dismissed() || isStandalone()) return;
  const close = h("button", { class: "install-close", type: "button", "aria-label": "Dismiss", html: icons.close });
  close.addEventListener("click", () => hideBanner(true));
  banner = h("div", { class: "install-banner", role: "note" }, h("img", { src: "icons/icon-192.png", alt: "", width: 40, height: 40 }), content, close);
  document.body.append(banner);
}

function iosHint() {
  return h("p", {}, "Install Inko: tap ", h("span", { class: "inline-icon", html: icons.share, "aria-label": "Share" }), " Share, then ", h("b", {}, "Add to Home Screen"), ".");
}

export function initInstall() {
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* offline support is a bonus */ });
  }
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();  // show our own button instead of the browser's mini bar
    deferredPrompt = e;
    showBanner(h("div", { class: "install-text" }, h("b", {}, "Get the Inko app"), h("span", {}, "Install it for quick access, even offline."),
      h("button", { class: "btn btn-small", type: "button", onclick: promptInstall }, icon("install"), "Install")));
  });
  window.addEventListener("appinstalled", () => { hideBanner(true); toast("Inko is installed. Find it on your home screen!"); });
  // iPhone and iPad never show an install popup, so give a small hint instead.
  if (isIOS() && !isStandalone()) setTimeout(() => showBanner(h("div", { class: "install-text" }, iosHint())), 1500);

  addSettingsSection(() => {
    let body;
    if (isStandalone()) body = h("p", {}, "You’re using the installed Inko app.");
    else if (deferredPrompt) body = h("button", { class: "btn btn-small", type: "button", onclick: promptInstall }, icon("install"), "Install Inko");
    else if (isIOS()) body = iosHint();
    else if (!window.isSecureContext) body = h("p", { class: "muted", style: "font-size:14px" }, "Installing needs a secure (https) link. You can still use Inko right here in the browser.");
    else body = h("p", { class: "muted", style: "font-size:14px" }, "Use your browser’s menu and choose Install app (Chrome and Edge) or Add to Dock (Safari on Mac).");
    return h("div", { class: "setting-group" }, h("h3", {}, "App"), body);
  });
}
