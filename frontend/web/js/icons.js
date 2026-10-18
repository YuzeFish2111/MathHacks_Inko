// Inline SVG icons, drawn thick and rounded to match the mockup tiles.
const wrap = (body, opts = "") =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${opts}>${body}</svg>`;

export const icons = {
  home: wrap('<path d="M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1h-4v-6.5h-7V21h-4a1 1 0 0 1-1-1z"/>'),
  decoder: wrap('<path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/><path d="M17.5 3.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/>'),
  practice: wrap('<path d="M5 3.5h10l4 4V20a.5.5 0 0 1-.5.5h-13A.5.5 0 0 1 5 20z"/><path d="M8.5 11h7M8.5 14.5h7M8.5 18h4"/>'),
  progress: wrap('<path d="M4 4v16h16"/><path d="m7.5 14.5 3.5-4 3 2.5 5-6"/>'),
  more: wrap('<circle cx="5.5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="18.5" cy="12" r="1.3" fill="currentColor"/>'),
  person: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7.5" r="4.5" fill="currentColor"/><path d="M3.5 21.5c0-5 3.8-8 8.5-8s8.5 3 8.5 8z" fill="currentColor"/></svg>',
  gear: wrap('<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
  plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.4 3h3.2v7.4H21v3.2h-7.4V21h-3.2v-7.4H3v-3.2h7.4z" fill="currentColor"/></svg>',
  camera: wrap('<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.5" r="3.5"/>'),
  image: wrap('<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m4 18 5.5-5.5 4 4 2.5-2.5 4 4"/>'),
  upload: wrap('<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>'),
  sparkle: wrap('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>'),
  pen: wrap('<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/>'),
  undo: wrap('<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>'),
  trash: wrap('<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>'),
  close: wrap('<path d="M6 6l12 12M18 6 6 18"/>'),
  check: wrap('<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
  arrow: wrap('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  refresh: wrap('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>'),
  sun: wrap('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>'),
  moon: wrap('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
  auto: wrap('<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17" /><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/>'),
  logout: wrap('<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4"/><path d="M10 16.5 5.5 12 10 7.5M5.5 12H15"/>'),
  mail: wrap('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>'),
  youtube: wrap('<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="m10 9.2 5 2.8-5 2.8z" fill="currentColor"/>'),
  instagram: wrap('<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r="0.9" fill="currentColor"/>'),
  info: wrap('<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>'),
  printer: wrap('<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="2"/><path d="M7 14h10v6.5H7z"/>'),
  share: wrap('<path d="M12 15V3.5M8 7.5l4-4 4 4"/><path d="M8.5 10.5H6a1 1 0 0 0-1 1V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8.5a1 1 0 0 0-1-1h-2.5"/>'),
  install: wrap('<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5"/><path d="M5 19.5h14"/>'),
  eye: wrap('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
};

export function iconEl(name) {
  const span = document.createElement("span");
  span.innerHTML = icons[name] || "";
  return span.firstElementChild;
}
