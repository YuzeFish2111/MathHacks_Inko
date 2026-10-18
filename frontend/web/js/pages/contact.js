import { h, icon, toast } from "../ui.js";
import { CONTACT } from "../content.js";

const YT_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1.5" y="4.5" width="21" height="15" rx="4.5" fill="#ff0033"/><path d="M10 9v6l5.2-3z" fill="#fff"/></svg>';
const IG_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="igg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#feda75"/><stop offset=".35" stop-color="#fa7e1e"/><stop offset=".6" stop-color="#d62976"/><stop offset=".85" stop-color="#962fbf"/><stop offset="1" stop-color="#4f5bd5"/></linearGradient></defs><rect x="2" y="2" width="20" height="20" rx="6" fill="url(#igg)"/><rect x="6.5" y="6.5" width="11" height="11" rx="5.5" fill="none" stroke="#fff" stroke-width="2"/><circle cx="17.3" cy="6.8" r="1.2" fill="#fff"/></svg>';

let mounted = false;
let ytBody;

export function mount(el) {
  // The checkmark only appears once the address is actually on the clipboard.
  const copy = h("button", { class: "btn btn-small", type: "button" }, "Copy");
  let resetCopy;
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(CONTACT.email);
      copy.replaceChildren(icon("check"), "Copied");
      clearTimeout(resetCopy);
      resetCopy = setTimeout(() => copy.replaceChildren("Copy"), 2000);
      toast("Email address copied!");
    } catch (e) {
      toast(CONTACT.email);
    }
  });

  ytBody = h("div", { class: "social-media" }, placeholder("youtube"));
  const youtube = h("section", { class: "social-card", "aria-label": "Inko on YouTube" },
    h("header", { class: "social-head" },
      h("span", { class: "social-avatar" }, h("img", { src: "img/logo-mark.png", alt: "" })),
      h("div", { class: "social-who" }, h("b", {}, "Inko"), h("span", {}, CONTACT.youtubeHandle)),
      h("span", { class: "social-brand", html: YT_ICON })),
    ytBody,
    h("div", { class: "social-foot" },
      h("a", { class: "btn btn-small yt-btn", href: `${CONTACT.youtube}?sub_confirmation=1`, target: "_blank", rel: "noopener" }, "Subscribe"),
      h("a", { class: "social-link", href: CONTACT.youtube, target: "_blank", rel: "noopener" }, CONTACT.youtube.replace("https://www.", ""))));

  const instagram = h("section", { class: "social-card", "aria-label": "Inko on Instagram" },
    h("header", { class: "social-head" },
      h("span", { class: "social-avatar ig-ring" }, h("img", { src: "img/logo-mark.png", alt: "" })),
      h("div", { class: "social-who" }, h("b", {}, CONTACT.instagramHandle), h("span", {}, "Inko Labs")),
      h("span", { class: "social-brand", html: IG_ICON })),
    CONTACT.instagramPosts.length ? instagramPosts() : placeholder("instagram"),
    h("div", { class: "social-foot" },
      h("a", { class: "btn btn-small ig-btn", href: CONTACT.instagram, target: "_blank", rel: "noopener" }, "Follow"),
      h("a", { class: "social-link", href: CONTACT.instagram, target: "_blank", rel: "noopener" }, CONTACT.instagram.replace("https://www.", "").replace(/\/$/, ""))));

  el.append(h("div", { class: "card" },
    h("h1", { class: "page-title" }, "Contact Us"),
    h("ul", { class: "contact-list" },
      h("li", {},
        h("span", { class: "icon-box" }, icon("mail")),
        h("div", { class: "contact-main" }, h("b", {}, "Email Us Here:"), " ", h("a", { href: `mailto:${CONTACT.email}` }, CONTACT.email)),
        copy)),
    h("div", { class: "social-grid" }, youtube, instagram)));
}

export function show() {
  if (mounted) return;
  mounted = true;
  loadLatestVideo();
}

function placeholder(kind) {
  if (kind === "youtube") {
    return h("div", { class: "social-placeholder yt-placeholder" },
      h("span", { class: "social-brand big", html: YT_ICON }),
      h("p", {}, "Our first video is on the way! Subscribe so you don’t miss it."));
  }
  return h("div", { class: "ig-grid", "aria-hidden": "true" },
    Array.from({ length: 6 }, (_, i) => h("span", { class: `ig-tile t${i % 3}` }, i === 0 ? h("img", { src: "img/logo-mark.png", alt: "" }) : null)),
    h("p", { class: "ig-note" }, "Handwriting tips, before and afters, and behind the scenes. Follow along!"));
}

async function loadLatestVideo() {
  try {
    const res = await fetch("/api/social/youtube", { cache: "no-store" });
    const { latest } = await res.json();
    if (!latest || !/^[\w-]{6,20}$/.test(latest.id)) return;
    ytBody.replaceChildren(h("div", { class: "video-frame" },
      h("iframe", {
        src: `https://www.youtube-nocookie.com/embed/${latest.id}`,
        title: latest.title || "Latest Inko video",
        loading: "lazy",
        allow: "accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen",
        allowfullscreen: true,
        referrerpolicy: "strict-origin-when-cross-origin",
      })));
  } catch (e) {
    /* offline or server down: keep the placeholder */
  }
}

function instagramPosts() {
  const wrap = h("div", { class: "ig-posts" }, CONTACT.instagramPosts.map((url) =>
    h("blockquote", { class: "instagram-media", "data-instgrm-permalink": url, "data-instgrm-version": "14" },
      h("a", { href: url, target: "_blank", rel: "noopener" }, "View this post on Instagram"))));
  // Instagram's official embed script turns each blockquote into the real post.
  if (!document.querySelector('script[src*="instagram.com/embed.js"]')) {
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://www.instagram.com/embed.js";
    document.body.append(s);
  } else if (window.instgrm) {
    setTimeout(() => window.instgrm.Embeds.process(), 0);
  }
  return wrap;
}
