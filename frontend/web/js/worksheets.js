// Printable worksheets, drawn as SVG on a US Letter page (816 x 1056 at 96 dpi).
// The page scales to fit A4 as well. Traced letters are light gray; the look-alike
// sheet uses hand-drawn single-stroke models so 1, l, and I really look different.

const W = 816, H = 1056, M = 56;
const GRAY = "#c9c4c0", GUIDE = "#b9c6d3", INK = "#6f5d56";
const ASC = 44, XH = 30, DESC = 14;   // ascender, x-height, descender above/below the baseline
const FONT = 60;                      // Figtree size whose x-height matches XH

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function guides(y, { slant = 0, bold = false } = {}) {
  let out = bold ? `<rect x="${M}" y="${y - XH}" width="${W - 2 * M}" height="${XH}" fill="#eef2f6"/>` : "";
  out += `<line x1="${M}" x2="${W - M}" y1="${y - ASC}" y2="${y - ASC}" stroke="${GUIDE}" stroke-width="1"/>`;
  out += `<line x1="${M}" x2="${W - M}" y1="${y - XH}" y2="${y - XH}" stroke="${GUIDE}" stroke-width="1" stroke-dasharray="6 5"/>`;
  out += `<line x1="${M}" x2="${W - M}" y1="${y}" y2="${y}" stroke="${bold ? "#8a9fb4" : INK}" stroke-width="${bold ? 3 : 1.4}"/>`;
  out += `<line x1="${M}" x2="${W - M}" y1="${y + DESC}" y2="${y + DESC}" stroke="${GUIDE}" stroke-width="0.8"/>`;
  if (slant) {
    const dx = Math.tan((slant * Math.PI) / 180) * (ASC + DESC);
    for (let x = M + 10; x < W - M - dx; x += 30) {
      out += `<line x1="${x}" y1="${y + DESC}" x2="${x + dx}" y2="${y - ASC}" stroke="${GUIDE}" stroke-width="0.8"/>`;
    }
  }
  return out;
}

const trace = (x, y, text, { size = FONT, slant = 0 } = {}) =>
  `<text transform="translate(${x} ${y})${slant ? ` skewX(${-slant})` : ""}" font-family="Figtree, sans-serif" font-size="${size}" font-weight="400" fill="${GRAY}" letter-spacing="2">${esc(text)}</text>`;

function header(title, instruction) {
  return `
  <rect width="${W}" height="${H}" fill="#fff"/>
  <text x="${M}" y="${M + 26}" font-family="Figtree, sans-serif" font-size="30" font-weight="800" fill="${INK}">Inko practice: ${esc(title)}</text>
  <text x="${W - M}" y="${M + 26}" text-anchor="end" font-family="Figtree, sans-serif" font-size="14" font-weight="700" fill="#9aa9b7">inko</text>
  <text x="${M}" y="${M + 62}" font-family="Figtree, sans-serif" font-size="14" fill="${INK}">Name</text>
  <line x1="${M + 44}" x2="${M + 330}" y1="${M + 64}" y2="${M + 64}" stroke="${INK}" stroke-width="1"/>
  <text x="${M + 360}" y="${M + 62}" font-family="Figtree, sans-serif" font-size="14" fill="${INK}">Date</text>
  <line x1="${M + 396}" x2="${W - M}" y1="${M + 64}" y2="${M + 64}" stroke="${INK}" stroke-width="1"/>
  <text x="${M}" y="${M + 100}" font-family="Figtree, sans-serif" font-size="16" font-weight="600" fill="${INK}">${esc(instruction)}</text>`;
}

function footer() {
  return `<text x="${W / 2}" y="${H - 28}" text-anchor="middle" font-family="Figtree, sans-serif" font-size="12" fill="#a8968e">Trace the gray letters, then copy them on the empty line below. Go slow: neat beats fast.</text>`;
}

/** Pairs of rows: one to trace, one to copy. */
function traceAndCopy(lines, opts = {}) {
  let y = M + 190, out = "";
  for (const line of lines) {
    if (y > H - 90) break;
    out += guides(y, opts) + trace(M + 8, y, line, { slant: opts.slant || 0 });
    y += 92;
    if (y > H - 90) break;
    out += guides(y, opts);
    y += 100;
  }
  return out;
}

function page(body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" class="worksheet-svg" role="img">${body}</svg>`;
}

// Width of a traced word, measured with the real font so spacer circles land between words.
let measureCtx = null;
function textWidth(word) {
  try {
    measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
    measureCtx.font = `400 ${FONT}px Figtree, sans-serif`;
    return measureCtx.measureText(word).width + 2 * word.length;
  } catch (e) {
    return word.length * FONT * 0.56;
  }
}

// Spacing sheet: ghost "o" circles show how much room to leave between words.
function spacingRows(lines) {
  let y = M + 190, out = "";
  for (const words of lines) {
    if (y > H - 90) break;
    out += guides(y);
    let x = M + 8;
    words.split(" ").forEach((word, i) => {
      if (i) {
        out += `<circle cx="${x + 20}" cy="${y - XH / 2}" r="${XH / 2 - 2}" fill="none" stroke="${GUIDE}" stroke-width="1.5" stroke-dasharray="3 3"/>`;
        x += 40;
      }
      out += trace(x, y, word);
      x += textWidth(word) + 4;
    });
    y += 92;
    if (y > H - 90) break;
    out += guides(y);
    y += 100;
  }
  return out;
}

// Single-stroke model glyphs in a box 60 units tall (0 = top line, 30 = x-height, 60 = baseline).
const GLYPHS = {
  "1": { w: 40, d: "M8 14 L20 2 L20 60 M8 60 H32", note: "flag + base" },
  l: { w: 30, d: "M14 0 L14 50 Q14 60 24 58", note: "tall + tail" },
  I: { w: 32, d: "M4 2 H28 M16 2 V60 M4 60 H28", note: "top + bottom bars" },
  "0": { w: 40, d: "M20 2 C6 2 4 20 4 31 C4 42 6 60 20 60 C34 60 36 42 36 31 C36 20 34 2 20 2 Z M9 52 L31 10", note: "narrow + slash" },
  O: { w: 54, d: "M27 2 C9 2 3 18 3 31 C3 46 11 60 27 60 C43 60 51 46 51 31 C51 18 45 2 27 2 Z", note: "round + wide" },
  "5": { w: 40, d: "M32 2 H9 L7 28 C15 22 34 22 34 42 C34 56 22 62 6 56", note: "flat top, sharp corner" },
  S: { w: 40, d: "M32 10 C28 2 8 0 6 14 C4 28 34 30 34 46 C34 60 10 64 4 52", note: "all curves" },
  "6": { w: 40, d: "M30 4 C14 6 4 22 4 40 C4 54 12 60 20 60 C30 60 36 52 36 44 C36 34 28 28 20 28 C12 28 6 34 4 40", note: "closed loop" },
  G: { w: 44, d: "M38 12 C32 2 8 0 4 28 C2 52 18 62 30 58 C36 56 38 50 38 40 H24", note: "clear bar" },
  "9": { w: 40, d: "M34 22 C34 10 28 2 18 2 C8 2 4 10 4 20 C4 30 12 36 20 36 C28 36 34 30 34 22 L30 60", note: "straight tail" },
  "8": { w: 40, d: "M20 30 C8 26 6 18 6 14 C6 6 12 2 20 2 C28 2 34 6 34 14 C34 20 30 26 20 30 C10 34 4 40 4 46 C4 56 12 60 20 60 C28 60 36 56 36 46 C36 40 30 34 20 30 Z", note: "two round loops" },
  B: { w: 42, d: "M6 2 V60 M6 2 H22 C32 2 34 10 34 15 C34 24 28 29 6 29 H24 C34 29 38 36 38 44 C38 54 32 60 22 60 H6", note: "straight back" },
  rn: { w: 64, d: "M6 30 V60 M6 42 C10 32 18 30 24 32 M36 30 V60 M36 42 C38 34 44 30 50 30 C58 30 60 36 60 42 V60", note: "gap between r and n" },
  m: { w: 50, d: "M6 30 V60 M6 42 C8 33 12 30 17 30 C23 30 25 35 25 42 V60 M25 42 C27 33 31 30 36 30 C42 30 44 35 44 42 V60", note: "humps joined" },
  cl: { w: 58, d: "M30 36 C27 31 22 30 18 30 C9 30 4 37 4 45 C4 54 10 60 18 60 C23 60 27 58 30 54 M46 0 L46 50 Q46 60 54 58", note: "gap between c and l" },
  d: { w: 36, d: "M30 0 V60 M30 45 C30 36 24 30 17 30 C9 30 4 37 4 45 C4 53 9 60 17 60 C24 60 30 54 30 45", note: "circle joins stem" },
};

function glyph(key, x, baseline, { dotted = false } = {}) {
  const g = GLYPHS[key];
  const s = ASC / 60;
  return `<path d="${g.d}" transform="translate(${x} ${baseline - ASC}) scale(${s})" fill="none" stroke="${dotted ? "#b3aca7" : INK}" stroke-width="${(dotted ? 2.2 : 3) / s}" stroke-linecap="round" stroke-linejoin="round"${dotted ? ` stroke-dasharray="${2 / s} ${4 / s}"` : ""}/>`;
}

const LOOKALIKE_GROUPS = [["1", "l", "I"], ["0", "O"], ["5", "S"], ["6", "G", "9"], ["8", "B"], ["rn", "m"], ["cl", "d"]];

function lookalikeRows() {
  let y = M + 196, out = "";
  const s = ASC / 60;
  for (const group of LOOKALIKE_GROUPS) {
    out += guides(y);
    let x = M + 10;
    for (const key of group) {
      out += glyph(key, x, y);
      out += `<text x="${x}" y="${y + DESC + 16}" text-anchor="start" font-family="Figtree, sans-serif" font-size="11" font-weight="700" fill="${INK}">${esc(GLYPHS[key].note)}</text>`;
      const noteWidth = GLYPHS[key].note.length * 6.3;
      x += Math.max(GLYPHS[key].w * s, noteWidth) + 26;
    }
    out += `<line x1="${x - 18}" x2="${x - 18}" y1="${y - ASC}" y2="${y + DESC}" stroke="${GUIDE}" stroke-width="1"/>`;
    let k = 0;
    while (x < W - M - 40) {
      const key = group[k % group.length];
      const gw = GLYPHS[key].w * s;
      if (x + gw > W - M) break;
      out += glyph(key, x, y, { dotted: true });
      x += gw + 22;
      k += 1;
    }
    y += 112;
  }
  return out;
}

export const WORKSHEETS = {
  size: {
    title: "Size",
    instruction: "Small letters touch the dashed line. Tall letters reach the top line. Tails hang to the bottom line.",
    tips: [
      "Use two guide lines: small letters touch the dashed middle line, tall letters reach the top.",
      "Write a little slower. Rushing makes letters grow and shrink.",
      "Check three letters at a time: are they all the same height?",
    ],
    build: () => page(header("Size", WORKSHEETS.size.instruction) + traceAndCopy(["a c e m n o r s u", "b d f h k l t", "g j p q y", "moon sun rain"]) + footer()),
  },
  spacing: {
    title: "Spacing",
    instruction: "Leave one o of space between words (the dotted circles). Keep letters in a word close, not touching.",
    tips: [
      "Leave about one letter o of space between words.",
      "Keep letters inside a word close together, but never touching.",
      "Try the finger trick: rest a finger on the page after each word.",
    ],
    build: () => page(header("Spacing", WORKSHEETS.spacing.instruction) + spacingRows(["the cat sat", "a big red hat", "we can read it", "see you soon"]) + footer()),
  },
  slant: {
    title: "Slant",
    instruction: "Follow the thin slanted lines with every tall stroke so all your letters lean the same way.",
    tips: [
      "Tilt your paper a little so your arm moves naturally (left-handers tilt it the other way).",
      "Pick one direction for tall letters, straight up or a gentle right lean, and stick to it.",
      "Draw the downstrokes of l, t, h, and k slowly. They set the slant for everything else.",
    ],
    build: () => page(header("Slant", WORKSHEETS.slant.instruction) + traceAndCopy(["l t h k b d f", "little kittens", "tall trees", "the lake hill"], { slant: 12 }) + footer()),
  },
  shape: {
    title: "Shape",
    instruction: "Close every loop all the way and keep round letters round.",
    tips: [
      "Close the tops of a, d, g, o, and q all the way.",
      "Make round letters round, not pointy or flat.",
      "Keep the humps on n, m, and h clear so they don’t turn into u or w.",
    ],
    build: () => page(header("Shape", WORKSHEETS.shape.instruction) + traceAndCopy(["o o o o o o o", "a d g q a d g q", "n m h r u n m h", "good dog quiz"]) + footer()),
  },
  alignment: {
    title: "Alignment",
    instruction: "Rest the bottom of every letter on the bold line. Short letters stay inside the shaded band.",
    tips: [
      "Rest every letter on the line, like it’s sitting on a bench.",
      "Use lined paper, or slip a lined sheet under plain paper so the lines show through.",
      "Watch short letters like e, r, and n. They love to float.",
    ],
    build: () => page(header("Alignment", WORKSHEETS.alignment.instruction) + traceAndCopy(["sit on the line", "every letter rests", "a neat row", "seven red roses"], { bold: true }) + footer()),
  },
  lookalikes: {
    title: "Look-alikes",
    instruction: "Copy the dark models, then trace the dotted ones. Each look-alike gets its own special feature.",
    tips: [
      "Give 1 a flag, I some bars, and l a little tail.",
      "Slash your zeros and keep your O round and wide.",
      "Leave a gap in rn and cl so they never become m and d.",
    ],
    build: () => page(header("Look-alikes", WORKSHEETS.lookalikes.instruction) + lookalikeRows() + footer()),
  },
};

export const WORKSHEET_ORDER = ["size", "spacing", "slant", "shape", "alignment", "lookalikes"];
