import { h, icon, openDialog } from "../ui.js";
import { THEMES, getTheme, setTheme } from "../theme.js";

const extraSections = [];

/** Other modules add groups here (account, history, install) without settings
 *  needing to know about them. Each builder returns a Node or null. */
export function addSettingsSection(builder) {
  extraSections.push(builder);
}

export function openSettings() {
  const current = getTheme();
  const buttons = THEMES.map((theme) => {
    const b = h("button", { type: "button", class: "theme-option", "aria-pressed": String(theme.id === current) },
      h("span", { class: "theme-swatch", style: `background:linear-gradient(135deg, ${theme.swatch[0]} 50%, ${theme.swatch[1]} 50%)` }),
      h("span", { class: "theme-name" }, theme.name),
      h("span", { class: "theme-check" }, icon("check")));
    b.addEventListener("click", () => {
      setTheme(theme.id);
      buttons.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    });
    return b;
  });
  let dialog;
  const ctx = { close: () => dialog && dialog.close() };
  const body = h("div", {},
    h("div", { class: "setting-group" },
      h("h3", {}, "Mode"),
      h("div", { class: "theme-options", role: "group", "aria-label": "Color mode" }, buttons),
    ),
    extraSections.map((build) => build(ctx)).filter(Boolean),
  );
  dialog = openDialog({ title: "Settings", body, anchored: true });
  return dialog;
}
