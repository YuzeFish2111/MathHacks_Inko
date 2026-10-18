import { h, icon } from "../ui.js";
import { MSG } from "../messages.js";

// What the analysis backend measures (its eight featureIds, grouped for a friendly overview).
const FACTORS = [
  ["Size", "Are your letters a readable size, and are small letters clearly shorter than tall ones?"],
  ["Spacing", "Is there enough, and even, space between the letters in a word?"],
  ["Shape", "Do your letters lean the same way and keep the same height?"],
  ["Alignment", "Do your letters sit neatly on the line?"],
  ["Pen strokes", "Is your pen pressure even, and your strokes neither too thin nor too thick?"],
];

export function mount(el) {
  const hero = h("div", { class: "card hero" },
    h("div", {},
      h("h1", {}, "Decode Bad", h("br"), "Handwriting ", h("em", {}, "Instantly")),
      h("p", { class: "hero-text" },
        "Upload messy notes, faded letters, rushed scribbles, or difficult cursive. Our handwriting reader interprets messy writing and turns it into clear, editable digital text, while also giving feedback to help you improve your handwriting."),
      h("div", { class: "btn-pair stack-phone hero-actions" },
        h("a", { class: "btn btn-big", href: "#/decoder" }, "Try the Decoder", icon("arrow")),
        h("a", { class: "btn btn-big btn-soft", href: "#/decoder?example=1" }, icon("sparkle"), "Try an example"),
      ),
    ),
    h("div", { class: "highlights dashed" },
      h("h2", {}, "Highlights:"),
      h("ul", {},
        h("li", {}, "Designed for bad handwriting"),
        h("li", {}, "Improve clarity and readability instantly"),
        h("li", {}, "Work directly in your browser"),
      ),
    ),
  );

  const steps = h("div", { class: "card" },
    h("h2", { class: "section-title" }, "How it works"),
    h("div", { class: "steps" },
      step("upload", "Upload", "Snap a photo of your handwriting, pick one from your photos or files, or write right on the screen."),
      step("eye", "Analyze", "Miggle straightens the page and measures size, spacing, shape, alignment, and pen strokes."),
      step("progress", "Improve", "Get an experimental score out of 100, see the tricky spots marked, and practice with worksheets made for you."),
    ),
  );

  const factors = h("div", { class: "card" },
    h("h2", { class: "section-title" }, "What Miggle checks"),
    h("div", { class: "factors" },
      FACTORS.map(([name, text]) => h("div", { class: "factor-card" }, h("h3", {}, name), h("p", {}, text))),
    ),
  );

  const tips = h("div", { class: "card" },
    h("h2", { class: "section-title" }, "Before you snap"),
    h("p", { class: "tip-card" }, MSG.tips),
  );

  el.append(hero, steps, factors, tips,
    h("footer", { class: "site-footer" }, "Inko 2026", h("a", { href: "#/about" }, "About Us"), h("a", { href: "#/contact" }, "Contact")));
}

function step(ic, title, text) {
  return h("div", { class: "step" }, h("div", { class: "step-icon" }, icon(ic)), h("h3", {}, title), h("p", {}, text));
}
