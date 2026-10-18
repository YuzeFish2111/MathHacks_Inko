// Three themes. Everyone starts on White Chocolate (light), whatever the device setting.
const KEY = "inko-theme";

export const THEMES = [
  { id: "light", name: "White Chocolate (Light mode)", swatch: ["#f8f4e8", "#967e76"], bar: "#f8f4e8" },
  { id: "milk", name: "Milk Chocolate (in between light and dark mode)", swatch: ["#27221e", "#c9b1a6"], bar: "#27221e" },
  { id: "dark", name: "Dark Chocolate", swatch: ["#37353e", "#725a5b"], bar: "#37353e" },
];

export function getTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    return THEMES.some((t) => t.id === saved) ? saved : "light";
  } catch (e) {
    return "light";
  }
}

export function setTheme(id) {
  try { localStorage.setItem(KEY, id); } catch (e) { /* ignore */ }
  applyTheme();
}

export function applyTheme() {
  const id = getTheme();
  const root = document.documentElement;
  if (id === "light") delete root.dataset.theme; else root.dataset.theme = id;
  const theme = THEMES.find((t) => t.id === id);
  // Keep the phone's status bar in step with the theme.
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", theme.bar));
}
