import { h, icon } from "../ui.js";
import { FEATURES, PAGE_WIDE_FEATURES } from "../features.js";
import { factorLabel, strongestFactor, weakestFactor } from "./results.js";

const quote = (s) => `“${s}”`;

function opening(score) {
  if (score === null) return "I found your writing, but couldn’t measure enough of it to give an overall score.";
  if (score >= 85) return `Wow, ${score} out of 100! Your handwriting is really easy to read.`;
  if (score >= 70) return `Nice work! You scored ${score}. Pretty readable, with a few spots to polish.`;
  if (score >= 50) return `You scored ${score}. I can read most of it, and a few small tweaks will make a big difference!`;
  return `You scored ${score}. Everyone starts somewhere! Let’s make your letters easier to read together.`;
}

/** Build Miggle's messages for a result. onPick(featureId) highlights that feature on the photo. */
export function buildMessages(result, { onPick, refs, highlights }) {
  const a = result.analysis;
  const items = [];
  const best = strongestFactor(result.scores);
  const weakest = weakestFactor(result.scores);

  let intro = opening(a.legibilityScore);
  if (best && weakest && best !== weakest) intro += ` Your ${factorLabel(best).toLowerCase()} is your superpower.`;
  items.push({ content: intro });
  items.push({
    content: "This score is an experimental estimate: it hasn’t been checked against people’s ratings yet, so treat it as a guide.",
    opts: { cls: "note" },
  });

  if (result.photo_check && result.photo_check.shadows) {
    items.push({ content: "I spotted some shadows on the page. A brighter spot will help me read even better next time." });
  }

  const marked = Object.keys(FEATURES).filter((id) => !PAGE_WIDE_FEATURES.has(id) && highlights && highlights.count(id) > 0);
  if (marked.length) {
    items.push({ content: `I marked the spots behind ${marked.length === 1 ? "one feature" : `${marked.length} features`} on your page. Tap a feature above, or a tip below, to see them.` });
  }

  a.advice.forEach((tip) => {
    items.push({
      content: h("span", {},
        h("b", {}, tip.title), h("br"), tip.message, " ",
        h("span", { class: "exercise" }, h("b", {}, "Try this: "), tip.exercise)),
      opts: { onClick: () => onPick(tip.featureId) },
      ref: (el) => { refs[`tip-${tip.featureId}`] = el; },
    });
  });

  if (a.recognizedText) {
    items.push({
      content: h("span", {}, "What a computer read (just for interest, it never changes your score): ",
        h("i", {}, quote(a.recognizedText))),
    });
  }

  a.warnings.forEach((warning) => items.push({ content: warning, opts: { cls: "note" } }));

  const sheet = weakest && FEATURES[weakest] ? FEATURES[weakest].worksheet : null;
  items.push({
    content: h("div", {},
      sheet ? `Want to level up your ${factorLabel(weakest).toLowerCase()}? I made a worksheet just for that.` : "Want some practice? I made worksheets for you.",
      h("div", { class: "bubble-actions" }, h("a", { class: "btn btn-small", href: "#/practice" }, icon("practice"), "Open Practice"))),
  });
  return items;
}
