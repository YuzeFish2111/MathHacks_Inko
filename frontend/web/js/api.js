import { MSG } from "./messages.js";

export class ApiError extends Error {
  constructor(code, message, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request(path, { method = "GET", body, json, timeout = 90000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const headers = {};
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }
  let res;
  try {
    res = await fetch(path, { method, body, headers, credentials: "same-origin", signal: controller.signal, cache: "no-store" });
  } catch (e) {
    throw new ApiError("server_down", MSG.server_down);
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty or HTML body */ }
  if (!res.ok) {
    const code = data && data.error ? data.error.code : res.status >= 500 ? "analysis_failed" : "server_down";
    // A proxy or crashed server can answer 502/503/504 with no JSON: treat it as "can't connect".
    if (!data && [502, 503, 504].includes(res.status)) throw new ApiError("server_down", MSG.server_down, res.status);
    throw new ApiError(code, MSG[code] || (data && data.error && data.error.message) || MSG.analysis_failed, res.status);
  }
  return data;
}

export const api = {
  /** wholePage: the whole image is the page (on-screen drawing, bundled example), not a photo of one. */
  analyze(blob, filename = "photo.jpg", { wholePage = false } = {}) {
    const form = new FormData();
    form.append("file", blob, filename);
    if (wholePage) form.append("whole_page", "true");
    return request("/analyze", { method: "POST", body: form, timeout: 120000 });
  },
  health: () => request("/api/health", { timeout: 5000 }),
  me: () => request("/api/me", { timeout: 8000 }),
  signUp: (name, username, password) => request("/api/auth/signup", { method: "POST", json: { name, username, password } }),
  signIn: (username, password) => request("/api/auth/signin", { method: "POST", json: { username, password } }),
  signOut: () => request("/api/auth/signout", { method: "POST" }),
  uploadAvatar(blob) {
    const form = new FormData();
    form.append("file", blob, "avatar.jpg");
    return request("/api/me/avatar", { method: "POST", body: form });
  },
  history: () => request("/api/history"),
  historyItem: (id) => request(`/api/history/${encodeURIComponent(id)}`),
  saveResult: (resultId) => request("/api/history/save", { method: "POST", json: { result_id: resultId } }),
  clearHistory: () => request("/api/history", { method: "DELETE" }),
};
