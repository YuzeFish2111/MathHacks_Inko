// App-wide state with a tiny event bus. Pages subscribe instead of reaching into each other.
const bus = new EventTarget();

export const state = {
  user: null,          // { id, name, username, avatar_url } when signed in
  lastResult: null,    // most recent analysis shown in the Decoder
};

export function on(event, fn) {
  const handler = (e) => fn(e.detail);
  bus.addEventListener(event, handler);
  return () => bus.removeEventListener(event, handler);
}

export function emit(event, detail) {
  bus.dispatchEvent(new CustomEvent(event, { detail }));
}

export function setUser(user) {
  state.user = user;
  emit("user", user);
}

// The guest's latest scores stay on this device so Practice can still pick a focus.
const LAST_KEY = "inko-last-scores";

export function rememberScores(result) {
  state.lastResult = result;
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({ scores: result.scores, overall_score: result.overall_score, created_at: result.created_at }));
  } catch (e) { /* private mode: fine */ }
  emit("result", result);
}

export function lastScores() {
  if (state.lastResult) return state.lastResult;
  try { return JSON.parse(localStorage.getItem(LAST_KEY) || "null"); } catch (e) { return null; }
}

export function forgetScores() {
  state.lastResult = null;
  try { localStorage.removeItem(LAST_KEY); } catch (e) { /* ignore */ }
  emit("result", null);
}
