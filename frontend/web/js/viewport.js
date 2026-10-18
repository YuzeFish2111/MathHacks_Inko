// iOS WebKit (Safari, and in-app browsers such as links opened from Messages) can leave the layout viewport
// shrunk after the keyboard, camera or photo picker closes. Everything with `position: fixed; bottom: 0`
// (the tab bar, toasts, the install hint) then stays where the sheet's top edge was, partway up the screen.
// The visual viewport (what is actually on screen) is still right, so this measures how far the visible
// screen extends below the layout viewport and sets --vv-shift; the CSS moves those elements down by it.
// Only ever downward: when the keyboard really is open the visible screen is SMALLER, and the tab bar should
// stay hidden behind the keyboard as usual, not jump above it.

let queued = false;

export function viewportShiftPx(visualTopPx, visualHeightPx, layoutHeightPx) {
  return Math.max(0, Math.round(visualTopPx + visualHeightPx - layoutHeightPx));
}

function sync() {
  queued = false;
  const vv = window.visualViewport;
  if (!vv) return;
  const shift = viewportShiftPx(vv.offsetTop, vv.height, document.documentElement.clientHeight);
  document.documentElement.style.setProperty("--vv-shift", `${shift}px`);
}

function schedule() {
  if (!queued) { queued = true; requestAnimationFrame(sync); }
}

export function initViewportFix() {
  if (!window.visualViewport) return;
  window.visualViewport.addEventListener("resize", schedule);
  window.visualViewport.addEventListener("scroll", schedule);
  for (const type of ["resize", "scroll", "orientationchange", "pageshow", "focus", "focusout"]) {
    window.addEventListener(type, schedule, { passive: true });
  }
  document.addEventListener("visibilitychange", schedule);
  // The keyboard and the photo picker animate closed; check again once they have finished
  window.addEventListener("focusout", () => setTimeout(schedule, 400));
  window.addEventListener("focus", () => setTimeout(schedule, 400));
  schedule();
}
