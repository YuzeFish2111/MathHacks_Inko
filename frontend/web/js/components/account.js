import { api } from "../api.js";
import { icons } from "../icons.js";
import { emit, forgetScores, on, setUser, state } from "../store.js";
import { avatarEl, confirmDialog, h, icon, openDialog, toast } from "../ui.js";
import { addSettingsSection, openSettings } from "./settings.js";
import { prepareImage } from "./upload.js";

const firstName = (user) => (user && user.name ? user.name.trim().split(/\s+/)[0] : "");

export async function initAccount() {
  const desktop = document.getElementById("account-desktop");
  const mobile = document.getElementById("account-mobile");
  const onClick = () => (state.user ? openSettings() : openAuth("signin"));
  desktop.addEventListener("click", onClick);
  mobile.addEventListener("click", onClick);
  on("user", renderButtons);
  renderButtons(null);
  addSettingsSection(accountSection);
  addSettingsSection(historySection);
  try {
    const { user } = await api.me();
    setUser(user);
  } catch (e) {
    /* server unreachable: stay a guest */
  }
}

function renderButtons(user) {
  const desktop = document.getElementById("account-desktop");
  const mobile = document.getElementById("account-mobile");
  if (user) {
    desktop.replaceChildren(avatarEl(user), firstName(user) || user.username);
    desktop.setAttribute("aria-label", `Account: ${user.name}`);
    mobile.replaceChildren(avatarEl(user));
    mobile.setAttribute("aria-label", `Account: ${user.name}`);
  } else {
    desktop.replaceChildren("Sign In");
    desktop.removeAttribute("aria-label");
    mobile.innerHTML = icons.person;
    mobile.setAttribute("aria-label", "Sign in");
  }
}

/** Sign in (username + password) or create an account (name, username, password). */
export function openAuth(mode = "signin") {
  const error = h("p", { class: "form-error", role: "alert" });
  const name = field("Name", "text", "name", { autocomplete: "name", maxlength: 60 });
  const username = field("Username", "text", "username", { autocomplete: "username", autocapitalize: "none", spellcheck: "false", maxlength: 30 });
  const password = field("Password", "password", "password", { minlength: 6 });
  const submit = h("button", { class: "btn btn-big", type: "submit", style: "width:100%;margin-top:18px" });
  const switchText = h("span");
  const switchBtn = h("button", { class: "link-btn", type: "button" });
  const form = h("form", { novalidate: true }, name.wrap, username.wrap, password.wrap, error, submit,
    h("p", { style: "margin-top:14px;text-align:center" }, switchText, " ", switchBtn));
  const tabs = [["signin", "Sign In"], ["signup", "Create Account"]].map(([value, label]) =>
    h("button", { type: "button", "aria-pressed": "false", onclick: () => setMode(value) }, label));

  function setMode(next) {
    mode = next;
    const signup = mode === "signup";
    tabs.forEach((t, i) => t.setAttribute("aria-pressed", String((i === 1) === signup)));
    name.wrap.hidden = !signup;
    password.input.autocomplete = signup ? "new-password" : "current-password";
    password.hint.textContent = signup ? "At least 6 characters." : "";
    submit.textContent = signup ? "Create Account" : "Sign In";
    switchText.textContent = signup ? "Already have an account?" : "New to Inko?";
    switchBtn.textContent = signup ? "Sign in" : "Create an account";
    error.textContent = "";
    if (form.isConnected) (signup ? name.input : username.input).focus();
  }
  switchBtn.addEventListener("click", () => setMode(mode === "signup" ? "signin" : "signup"));

  const { close } = openDialog({
    title: "Welcome to Inko",
    body: h("div", {},
      h("p", { class: "muted", style: "margin:6px 0 14px" }, "Sign in to track your progress and add your name and photo."),
      h("div", { class: "segmented", role: "group", "aria-label": "Sign in or create an account" }, tabs),
      form),
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    error.textContent = "";
    const signup = mode === "signup";
    if (signup && !name.input.value.trim()) return (error.textContent = "Please enter your name.");
    if (!username.input.value.trim() || !password.input.value) return (error.textContent = "Please enter your username and password.");
    submit.disabled = true;
    try {
      const { user } = signup
        ? await api.signUp(name.input.value, username.input.value, password.input.value)
        : await api.signIn(username.input.value, password.input.value);
      setUser(user);
      close();
      toast(signup ? `Welcome, ${firstName(user)}!` : `Welcome back, ${firstName(user)}!`);
      await saveLastScan();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  setMode(mode);
}

function field(label, type, id, attrs = {}) {
  const input = h("input", { type, id: `auth-${id}`, name: id, ...attrs });
  const hint = h("span", { class: "hint" });
  const wrap = h("div", { class: "field" }, h("label", { for: `auth-${id}` }, label), input, hint);
  return { input, hint, wrap };
}

/** A guest who signs in right after a scan keeps that scan. */
async function saveLastScan() {
  const result = state.lastResult;
  if (result && result.result_id && !result.saved) {
    try {
      await api.saveResult(result.result_id);
      result.saved = true;
      toast("Saved your last scan to your progress.");
    } catch (e) { /* expired: nothing to save */ }
  }
  emit("history-changed");
}

function accountSection(ctx) {
  const user = state.user;
  if (!user) {
    return h("div", { class: "setting-group" },
      h("h3", {}, "Account"),
      h("p", {}, "You’re using Inko as a guest. Sign in to track your progress and add your name and profile picture."),
      h("div", { class: "btn-pair", style: "margin-top:12px" },
        h("button", { class: "btn btn-small", type: "button", onclick: () => { ctx.close(); openAuth("signin"); } }, "Sign In"),
        h("button", { class: "btn btn-small btn-soft", type: "button", onclick: () => { ctx.close(); openAuth("signup"); } }, "Create Account")));
  }
  const picker = h("input", { type: "file", accept: "image/*,.heic,.heif", class: "visually-hidden", tabindex: "-1" });
  const photo = h("div", { class: "account-photo" }, avatarEl(user, "avatar avatar-lg"));
  const change = h("button", { class: "btn btn-small btn-soft", type: "button", onclick: () => picker.click() }, icon("camera"), user.avatar_url ? "Change picture" : "Add profile picture");
  picker.addEventListener("change", async () => {
    const file = picker.files && picker.files[0];
    picker.value = "";
    if (!file) return;
    change.disabled = true;
    try {
      const prepared = await prepareImage(file);
      const { user: updated } = await api.uploadAvatar(prepared.blob);
      setUser(updated);
      photo.replaceChildren(avatarEl(updated, "avatar avatar-lg"));
      toast("Looking good! Profile picture updated.");
    } catch (err) {
      toast(err.message, { error: true });
    } finally {
      change.disabled = false;
    }
  });
  const signOut = h("button", { class: "btn btn-small btn-ghost", type: "button" }, icon("logout"), "Sign out");
  signOut.addEventListener("click", async () => {
    try { await api.signOut(); } catch (e) { /* still sign out locally */ }
    setUser(null);
    forgetScores();
    ctx.close();
    toast("Signed out. See you soon!");
    emit("history-changed");
  });
  return h("div", { class: "setting-group" },
    h("h3", {}, "Account"),
    h("div", { class: "account-row" }, photo, h("div", {}, h("div", { class: "account-name" }, user.name), h("div", { class: "muted" }, `@${user.username}`))),
    h("div", { class: "btn-pair", style: "margin-top:12px" }, change, signOut),
    picker);
}

function historySection(ctx) {
  const btn = h("button", { class: "btn btn-small btn-danger", type: "button" }, icon("trash"), "Clear history");
  btn.addEventListener("click", async () => {
    const signedIn = !!state.user;
    ctx.close();
    const ok = await confirmDialog({
      title: "Clear history?",
      text: signedIn ? "This deletes all your saved scans and progress. It can’t be undone." : "This clears the last scan saved on this device.",
      confirmText: "Clear history",
      danger: true,
    });
    if (!ok) return;
    try {
      if (signedIn) await api.clearHistory();
      forgetScores();
      toast("History cleared.");
      emit("history-changed");
    } catch (err) {
      toast(err.message, { error: true });
    }
  });
  return h("div", { class: "setting-group" },
    h("h3", {}, "History"),
    h("p", { class: "muted", style: "font-size:14px;margin-bottom:10px" }, state.user ? "Your saved scans power the Progress page." : "Guests keep only their latest scan, on this device."),
    btn);
}
