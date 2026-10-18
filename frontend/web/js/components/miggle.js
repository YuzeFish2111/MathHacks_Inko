import { h, sleep } from "../ui.js";

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Miggle's chat panel. Miggle is not a chatbot: there is no text box. She posts
 *  friendly messages built from the analysis results, one at a time with typing dots. */
export function createMiggle() {
  const log = h("div", { class: "miggle-log", role: "log", "aria-live": "polite", "aria-label": "Messages from Miggle" });
  const panel = h("div", { class: "panel miggle-panel solid" },
    h("div", { class: "miggle-head" },
      h("img", { src: "img/logo-mark.png", alt: "", width: 64, height: 64 }),
      h("div", {}, h("div", { class: "miggle-name" }, "Miggle"), h("div", { class: "miggle-role" }, "Miggle Assistant")),
    ),
    log,
  );
  let run = 0;  // bumping this cancels a sequence that is still typing
  let anchor = null;  // first bubble of the current sequence: never scroll past it

  function bubble(content, { wide = false, cls = "", onClick, tag = "div" } = {}) {
    const el = h(onClick ? "button" : tag, {
      class: `bubble${wide ? " wide" : ""}${onClick ? " clickable" : ""}${cls ? " " + cls : ""}`,
      type: onClick ? "button" : undefined,
    }, content);
    if (onClick) el.addEventListener("click", onClick);
    return el;
  }

  function scrollToEnd() {
    // On phones the log is not its own scroller, so leave the page where it is.
    if (log.scrollHeight <= log.clientHeight + 4) return;
    const end = log.scrollHeight - log.clientHeight;
    log.scrollTop = anchor && anchor.isConnected ? Math.min(end, anchor.offsetTop - 8) : end;
  }

  return {
    panel,
    log,
    clear() { run += 1; anchor = null; log.replaceChildren(); },
    say(content, opts) {
      const el = bubble(content, opts);
      log.append(el);
      scrollToEnd();
      return el;
    },
    typing() {
      const el = h("div", { class: "bubble typing", "aria-label": "Miggle is typing" }, h("i"), h("i"), h("i"));
      log.append(el);
      scrollToEnd();
      return el;
    },
    /** items: [{content, opts}] posted one by one. Resolves false if cancelled. */
    async sequence(items, { pause = 520 } = {}) {
      const mine = ++run;
      const fast = reducedMotion();
      let first = true;
      for (const item of items) {
        if (!fast) {
          const dots = this.typing();
          await sleep(Math.min(900, pause + (typeof item.content === "string" ? item.content.length * 4 : 260)));
          dots.remove();
          if (mine !== run) return false;
        }
        const el = this.say(item.content, item.opts);
        if (first) { anchor = el; first = false; scrollToEnd(); }
        item.ref && item.ref(el);
      }
      return true;
    },
  };
}
