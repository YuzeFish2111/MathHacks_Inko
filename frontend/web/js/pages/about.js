import { h, icon } from "../ui.js";
import { FOUNDERS, MIGGLE } from "../content.js";

export function mount(el) {
  el.append(
    h("div", { class: "card" },
      h("h1", { class: "page-title" }, "About Us"),
      h("h2", { class: "section-title about-heading" }, "Meet Miggle"),
      h("article", { class: "miggle-intro", "aria-label": `${MIGGLE.name}, ${MIGGLE.role}` },
        h("div", { class: "miggle-intro-side" },
          h("div", { class: "founder-photo" }, MIGGLE.photo ? h("img", { src: MIGGLE.photo, alt: MIGGLE.name }) : ""),
          h("div", { class: "founder-name" }, MIGGLE.name),
          h("div", { class: "miggle-intro-role" }, MIGGLE.role)),
        h("p", { class: "founder-bio miggle-intro-bio" }, MIGGLE.bio)),
      h("h2", { class: "section-title about-heading" }, "The founders"),
      h("div", { class: "founders" }, FOUNDERS.map((f, i) =>
        h("article", { class: "founder", "aria-label": f.name || `Founder ${i + 1}` },
          h("div", { class: "founder-photo" }, f.photo ? h("img", { src: f.photo, alt: f.name }) : icon("person")),
          h("div", { class: "founder-name" }, f.name),
          h("div", { class: "founder-bio" }, f.bio),
        ))),
    ));
}
