// mailgrant web app. No framework, no build step: the server ships these
// files as they are. Everything that comes from mail is inserted as text
// (textContent), never as HTML. The one exception is an HTML body, which the
// server sanitizes and serves as its own document for a sandboxed iframe.
// Interface text goes through t(): English in the code, the other languages
// in static/i18n/<lang>.json.

const API = "/app/api";
const WIDE = window.matchMedia("(min-width: 1000px)");

const state = {
  authed: false,
  hasPasskeys: false,
  setupCode: false,
  me: null,
  prefs: null,
  counts: {},
  total: 0,
  view: "inbox", // inbox | starred | drafts
  box: "all",
  q: "",
  limit: 40,
  list: [],
  fetched: 0,
  listErrors: [],
  listKey: null,
  loadingList: false,
  drafts: null,
  selecting: false,
  selected: new Set(),
  thread: null,
  threadKey: null,
  expanded: new Set(),
  showImages: new Set(),
  draft: null,
  passkeys: null,
  agents: null,
  activity: null,
  actKind: "all",
  invite: null,
  push: { supported: false, subscribed: false },
  busy: false,
  drawer: false,
  admin: null,
  form: null,
  reveal: null,
};

// ── helpers ───────────────────────────────────────────────────────────────

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

// ── language ──────────────────────────────────────────────────────────────

// English is the source and the fallback: t() looks the English text up in
// the active language's file. A plural is found by its singular form and
// holds one entry per Intl.PluralRules category. A "context|" prefix tells
// apart two texts that are the same in English (Read the verb, Read the state).
const LANGS = { en: "English", "pt-BR": "Português (Brasil)", es: "Español", fr: "Français", "zh-CN": "简体中文" };
let lang = "en";
let strings = {};
const warned = new Set();

const fill = (text, vars) => (vars ? text.replace(/\{(\w+)\}/g, (all, k) => (k in vars ? String(vars[k]) : all)) : text);

function missing(text) {
  if (lang === "en" || warned.has(text)) return;
  warned.add(text);
  console.warn(`[i18n] missing ${lang}: ${text}`);
}

function t(text, vars) {
  const s = lang === "en" ? null : strings[text];
  if (lang !== "en" && typeof s !== "string") missing(text);
  return fill(typeof s === "string" ? s : text.replace(/^[a-z]+\|/, ""), vars);
}

function tn(n, one, many, vars = {}) {
  const all = { n: n.toLocaleString(lang), ...vars };
  const forms = lang === "en" ? null : strings[one];
  if (lang !== "en" && (!forms || typeof forms !== "object")) missing(one);
  if (!forms || typeof forms !== "object") return fill(n === 1 ? one : many, all);
  // CLDR files 0 under "one" in Portuguese, but people write "0 mensagens".
  const cat = n === 0 && lang === "pt-BR" ? "other" : new Intl.PluralRules(lang).select(n);
  return fill(forms[cat] ?? forms.other, all);
}

// The explicit choice when there is one, else the first browser language we have.
function pickLang(choice) {
  if (choice && LANGS[choice]) return choice;
  for (const l of navigator.languages?.length ? navigator.languages : [navigator.language || "en"]) {
    const x = l.toLowerCase();
    if (x.startsWith("en")) return "en";
    if (x.startsWith("pt")) return "pt-BR";
    if (x.startsWith("es")) return "es";
    if (x.startsWith("fr")) return "fr";
    if (x.startsWith("zh")) return "zh-CN";
  }
  return "en";
}

// Kept on the device too, so the sign-in screen speaks the right language.
function storedLang() {
  try { return localStorage.getItem("mailgrant.lang") || ""; } catch (_) { return ""; }
}

async function setLanguage(choice) {
  try { choice ? localStorage.setItem("mailgrant.lang", choice) : localStorage.removeItem("mailgrant.lang"); } catch (_) { /* private mode */ }
  const next = pickLang(choice);
  if (next !== "en") {
    try {
      const res = await fetch(`/app/static/i18n/${next}.json`);
      if (!res.ok) throw new Error(res.status);
      strings = await res.json();
    } catch (_) {
      return; // keep the current language rather than show half a page
    }
  } else strings = {};
  lang = next;
  warned.clear();
  document.documentElement.lang = lang;
}

const ICONS = {
  inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
  agents: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  back: '<path d="m15 5-7 7 7 7"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  face: '<path d="M7 3H5a2 2 0 0 0-2 2v2M17 3h2a2 2 0 0 1 2 2v2M7 21H5a2 2 0 0 1-2-2v-2M17 21h2a2 2 0 0 0 2-2v-2"/><path d="M9 9v1M15 9v1M12 9v4h-1M9.5 16c1.5 1 3.5 1 5 0"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10h14V9M10 13h4"/>',
  mailOpen: '<path d="M3 10 12 4l9 6v9H3z"/><path d="m3 10 9 6 9-6"/>',
  reply: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 6 6v4"/>',
  replyAll: '<path d="M8 14 3 9l5-5"/><path d="M13 14 8 9l5-5"/><path d="M8 9h7a6 6 0 0 1 6 6v4"/>',
  forward: '<path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0-6 6v4"/>',
  clip: '<path d="m20 11.5-8.2 8.2a5 5 0 0 1-7-7L13 4.5a3.4 3.4 0 0 1 4.8 4.8l-8.2 8.2a1.7 1.7 0 0 1-2.4-2.4l7.5-7.5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12 4.5 4.5L19 7"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name]; // static strings only
  return svg;
}

async function api(path, { method = "GET", body, raw = false } = {}) {
  const res = await fetch(API + path, {
    method,
    credentials: "same-origin",
    headers: { "X-Mailgrant": "1", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    state.authed = false;
    render();
    throw new Error(t("Session ended. Sign in again."));
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const err = new Error(data.detail || t("Error {status}", { status: res.status }));
    err.status = res.status;
    throw err;
  }
  if (raw) {
    // A file to save: hand it to the browser as a download.
    const name = (/filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "") || [])[1] || "download";
    const url = URL.createObjectURL(await res.blob());
    const a = h("a", { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return null;
  }
  return res.json();
}

let toastTimer;
function toast(text) {
  document.querySelector(".toast")?.remove();
  const el = h("div", { class: "toast", role: "status" }, text);
  document.body.append(el);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.remove(), 3200);
}

const b64urlToBytes = (s) => {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
};
const bytesToB64url = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function when(ts, { withTime = false } = {}) {
  if (!ts) return "";
  const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date();
  const days = Math.floor((new Date(today.toDateString()) - new Date(d.toDateString())) / 86400000);
  const hm = clock(d);
  if (days === 0) return hm;
  if (days === 1) return withTime ? `${relDay(-1)} ${hm}` : relDay(-1);
  if (days < 7) return d.toLocaleDateString(lang, { weekday: "short" }).replace(".", "");
  return d.toLocaleDateString(lang, { day: "2-digit", month: "2-digit" });
}

// "8:05 AM" where clocks have 12 hours, "08:05" where they have 24.
const clock = (d) => d.toLocaleTimeString(lang, {
  hour: new Intl.DateTimeFormat(lang, { hour: "numeric" }).resolvedOptions().hour12 ? "numeric" : "2-digit", minute: "2-digit" });
const relDay = (n) => new Intl.RelativeTimeFormat(lang, { numeric: "auto" }).format(n, "day");
const capital = (s) => s.charAt(0).toLocaleUpperCase(lang) + s.slice(1);

function dayLabel(iso) {
  const d = new Date(iso);
  const days = Math.floor((new Date(new Date().toDateString()) - new Date(d.toDateString())) / 86400000);
  if (days === 0 || days === 1) return capital(relDay(-days));
  return d.toLocaleDateString(lang, { day: "numeric", month: "long" });
}

function linkify(text) {
  const out = [];
  const re = /\bhttps?:\/\/[^\s<>()"]+[^\s<>()".,;:!?]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    out.push(text.slice(last, m.index));
    out.push(h("a", { href: m[0], target: "_blank", rel: "noopener noreferrer" }, m[0]));
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

const standalone = () =>
  window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent);
const boxByName = (name) => state.me?.mailboxes.find((m) => m.name === name);
const scopeWord = (s) => ({ read: t("reads"), mark: t("marks"), delete: t("deletes"), send: t("sends") })[s];

// ── routing ───────────────────────────────────────────────────────────────

const LIST_VIEWS = ["inbox", "starred", "sent", "drafts"];
const viewTitle = (v) => ({ inbox: t("Inbox"), starred: t("Starred"), sent: t("Sent"), drafts: t("Drafts") })[v];
const COMPOSE_VIEWS = ["compose", "reply", "replyall", "forward", "draft"];

function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "inbox").split("/").map(decodeURIComponent);
  return { name: parts[0] || "inbox", args: parts.slice(1) };
}
const go = (path) => (location.hash = path);
const enc = encodeURIComponent;

function listHref() {
  if (state.view === "starred") return "#/starred";
  if (state.view === "sent") return "#/sent";
  if (state.view === "drafts") return "#/drafts";
  return state.box === "all" ? "#/inbox" : `#/inbox/${enc(state.box)}`;
}

async function onRoute() {
  const r = route();
  if (r.name === "invite") {
    state.invite = r.args[0] || null;
    if (!state.authed) return render();
  }
  if (!state.authed) return render();
  state.drawer = false;
  // Leaving the editor keeps what was written: it is saved as a draft.
  if (state.draft && !COMPOSE_VIEWS.includes(r.name)) await leaveDraft();
  if (!LIST_VIEWS.includes(r.name) && r.name !== "m" && state.selecting) stopSelecting(false);
  try {
    if (r.name === "inbox" || r.name === "starred" || r.name === "sent") {
      const box = r.name === "inbox" ? r.args[0] || "all" : "all";
      if (state.view !== r.name || state.box !== box) stopSelecting(false);
      // Rows of another view have another shape (Sent rows list recipients).
      if (state.view !== r.name) { state.list = []; state.listKey = null; }
      state.view = r.name;
      state.box = box;
      clearThread();
      render();
      await loadList();
    } else if (r.name === "drafts") {
      stopSelecting(false);
      state.view = "drafts";
      clearThread();
      render();
      await loadDrafts();
    } else if (r.name === "m") {
      if (!state.list.length && state.view !== "drafts") loadList();
      await openThread(r.args[0], r.args[1], r.args[2]);
    } else if (r.name === "reply" || r.name === "replyall" || r.name === "forward") {
      const key = `${r.name}:${r.args.join("/")}`;
      if (state.draft?.key !== key) {
        await leaveDraft();
        const m = await threadMessage(r.args[0], r.args[1], r.args[2]);
        startDraft(r.name, m, key);
      }
      render();
    } else if (r.name === "compose") {
      if (state.draft?.key !== "new") {
        await leaveDraft();
        startDraft("new", null, "new");
      }
      render();
    } else if (r.name === "draft") {
      await openDraft(r.args[0], r.args[1]);
    } else if (r.name === "agents") {
      render();
      await loadActivity();
    } else if (r.name === "settings" && (r.args[0] === "mailbox" || r.args[0] === "agent") && state.me.manage) {
      await openForm(r.args[0], r.args[1] || "new");
    } else if (r.name === "settings") {
      state.form = null;
      state.reveal = null;
      render();
      await loadSettings();
    } else {
      go("/inbox");
    }
  } catch (e) {
    toast(e.message);
  }
}

// ── data ──────────────────────────────────────────────────────────────────

async function loadMe() {
  const [me, prefs] = await Promise.all([api("/me"), api("/prefs")]);
  state.me = me;
  state.prefs = prefs;
  // A choice made in Ajustes on another device wins; "" follows this browser.
  if ((prefs.lang || "") !== storedLang()) await setLanguage(prefs.lang || "");
  // Pushes are written before any page is open: tell the server what we speak.
  if (prefs.ui_lang !== lang) api("/prefs", { method: "PUT", body: { ui_lang: lang } }).then((x) => { state.prefs = x; }).catch(() => {});
  refreshCounts();
}

const can = (scope) => !!state.me?.scopes.includes(scope);

async function refreshCounts() {
  try {
    const c = await api("/counts");
    state.counts = c.unseen;
    state.total = c.total;
    if ("setAppBadge" in navigator) c.total ? navigator.setAppBadge(c.total) : navigator.clearAppBadge();
    render();
  } catch (_) {
    /* counts are a nicety */
  }
}

const wantedList = () => `${state.view}|${state.box}|${state.q}|${state.limit}`;

async function loadList(force = false) {
  const key = wantedList();
  if (!force && key === state.listKey && state.list.length) return;
  // Another list empties the screen; "load more" (a bigger limit) keeps it.
  if (key.replace(/\|\d+$/, "") !== (state.listKey || "").replace(/\|\d+$/, "")) {
    state.list = [];
    state.listErrors = [];
  }
  state.loadingList = true;
  render();
  try {
    const params = new URLSearchParams({ limit: state.limit, view: state.view });
    if (state.box !== "all") params.set("mailbox", state.box);
    if (state.q) params.set("q", state.q);
    const data = await api(`/inbox?${params}`);
    // A slower answer for a list the person already left must not replace the current one.
    if (wantedList() !== key) return;
    state.list = data.messages;
    state.fetched = data.fetched;
    state.listErrors = data.errors;
    state.listKey = key;
  } finally {
    if (wantedList() === key) state.loadingList = false;
    render();
  }
}

async function loadDrafts() {
  state.loadingList = true;
  render();
  try {
    const data = await api("/drafts");
    state.drafts = data.drafts;
    state.listErrors = data.errors;
  } finally {
    state.loadingList = false;
    render();
  }
}

function clearThread() {
  state.thread = null;
  state.threadKey = null;
}

const msgKey = (m) => `${m.folder}/${m.uid}`;
const rowKey = (m) => `${m.mailbox}/${m.uid}`;

async function openThread(box, uid, folder, markSeen = true) {
  const key = `${box}/${folder || ""}/${uid}`;
  if (state.threadKey === key && state.thread) return render();
  state.threadKey = key;
  state.thread = null;
  render();
  const th = await api(`/thread/${enc(box)}/${enc(uid)}${folder ? `?folder=${enc(folder)}` : ""}`);
  if (state.threadKey !== key) return;
  state.thread = th;
  const last = th.messages.length - 1;
  state.expanded = new Set(th.messages.filter((m, i) => i === last || m.unread || m.opened).map(msgKey));
  render();
  const unread = th.messages.filter((m) => m.unread && !m.sent).map((m) => m.uid);
  if (markSeen && th.can.mark && unread.length) {
    await batch("seen", unread.map((u) => ({ mailbox: th.mailbox, uid: u })), { folder: th.folder });
    th.messages.forEach((m) => { if (!m.sent) m.unread = false; });
    rowsOf(th).forEach((r) => (r.unread = false));
    refreshCounts();
  }
}

// The message a reply or forward starts from, loading its conversation if needed.
async function threadMessage(box, uid, folder) {
  const find = () => state.thread?.mailbox === box &&
    state.thread.messages.find((m) => String(m.uid) === String(uid) && (!folder || m.folder === folder));
  if (!find()) await openThread(box, uid, folder, false);
  const m = find();
  if (!m) throw new Error(t("Message not found."));
  return m;
}

// List rows that hold any message of this conversation.
const rowsOf = (th) => state.list.filter((r) => r.mailbox === th.mailbox && r.members.some((u) => th.members.includes(u)));

async function loadActivity() {
  const [act, agents] = await Promise.all([api(`/activity?kind=${state.actKind}`), state.agents ? null : api("/agents")]);
  state.activity = act.events;
  if (agents) state.agents = agents;
  render();
}

async function loadSettings() {
  const [prefs, keys, agents] = await Promise.all([api("/prefs"), api("/passkeys"), api("/agents"),
    state.me.manage ? loadAdmin() : null]);
  state.prefs = prefs;
  state.passkeys = keys.passkeys;
  state.agents = agents;
  await checkPush();
  render();
}

async function checkPush() {
  state.push.supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (!state.push.supported) return;
  const reg = await navigator.serviceWorker.getRegistration("/app/");
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  state.push.subscribed = !!sub && Notification.permission === "granted";
}

// ── actions on messages ───────────────────────────────────────────────────

const batch = (action, items, extra = {}) => api("/batch", { method: "POST", body: { action, items, ...extra } });

async function actOnRows(action, rows) {
  if (!rows.length) return;
  // A star goes on the newest message of a conversation; taking it off clears them all.
  const items = action === "flag"
    ? rows.map((r) => ({ mailbox: r.mailbox, uid: r.uid }))
    : rows.flatMap((r) => r.members.map((uid) => ({ mailbox: r.mailbox, uid })));
  try {
    const res = await batch(action, items);
    const gone = new Set();
    for (const r of rows) {
      if (action === "seen" || action === "unseen") r.unread = action === "unseen";
      else if (action === "flag" || action === "unflag") {
        r.flagged = action === "flag";
        if (!r.flagged && state.view === "starred") gone.add(r);
      } else gone.add(r);
    }
    if (gone.size) state.list = state.list.filter((r) => !gone.has(r));
    if (action === "archive") toast(tn(rows.length, "Archived.", "{n} archived."));
    if (action === "trash") toast(tn(rows.length, "Moved to the trash.", "{n} moved to the trash."));
    if (res.errors?.length) toast(res.errors.map((e) => `${e.mailbox}: ${e.error}`).join(" · "));
    refreshCounts();
  } catch (e) {
    toast(e.message);
  }
  render();
}

function startSelecting(key) {
  state.selecting = true;
  state.selected = new Set(key ? [key] : []);
  render();
}

function stopSelecting(redraw = true) {
  state.selecting = false;
  state.selected = new Set();
  if (redraw) render();
}

// Lifting the finger after a long press produces a tap on whatever row is
// under it once the list is redrawn; that tap must not toggle anything.
let gesture = { pressed: false, at: 0 };

function toggleSelect(key) {
  if (gesture.pressed || Date.now() - gesture.at < 400) return;
  state.selected.has(key) ? state.selected.delete(key) : state.selected.add(key);
  render();
}

const selectedRows = () => state.list.filter((m) => state.selected.has(rowKey(m)));

// ── passkeys ──────────────────────────────────────────────────────────────

function assertionJSON(cred) {
  return {
    id: cred.id,
    rawId: bytesToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bytesToB64url(cred.response.clientDataJSON),
      authenticatorData: bytesToB64url(cred.response.authenticatorData),
      signature: bytesToB64url(cred.response.signature),
      userHandle: cred.response.userHandle ? bytesToB64url(cred.response.userHandle) : null,
    },
    clientExtensionResults: cred.getClientExtensionResults(),
  };
}

async function signIn() {
  state.busy = true;
  render();
  try {
    const { challenge_id, options } = await api("/auth/login/options", { method: "POST" });
    const cred = await navigator.credentials.get({
      publicKey: {
        ...options,
        challenge: b64urlToBytes(options.challenge),
        allowCredentials: (options.allowCredentials || []).map((c) => ({ ...c, id: b64urlToBytes(c.id) })),
      },
    });
    await api("/auth/login/verify", { method: "POST", body: { challenge_id, credential: assertionJSON(cred) } });
    await afterSignIn();
  } catch (e) {
    toast(e.name === "NotAllowedError" ? t("Sign-in cancelled.") : e.message);
  } finally {
    state.busy = false;
    render();
  }
}

async function register(deviceName, code = state.invite) {
  state.busy = true;
  render();
  try {
    const { challenge_id, options } = await api("/auth/register/options", {
      method: "POST",
      body: { invite: code || "" },
    });
    const cred = await navigator.credentials.create({
      publicKey: {
        ...options,
        challenge: b64urlToBytes(options.challenge),
        user: { ...options.user, id: b64urlToBytes(options.user.id) },
        excludeCredentials: (options.excludeCredentials || []).map((c) => ({ ...c, id: b64urlToBytes(c.id) })),
      },
    });
    await api("/auth/register/verify", {
      method: "POST",
      body: {
        challenge_id,
        name: deviceName,
        credential: {
          id: cred.id,
          rawId: bytesToB64url(cred.rawId),
          type: cred.type,
          response: {
            clientDataJSON: bytesToB64url(cred.response.clientDataJSON),
            attestationObject: bytesToB64url(cred.response.attestationObject),
            transports: cred.response.getTransports ? cred.response.getTransports() : [],
          },
          clientExtensionResults: cred.getClientExtensionResults(),
        },
      },
    });
    state.invite = null;
    state.setupCode = false;
    toast(t("Passkey created."));
    await afterSignIn();
  } catch (e) {
    toast(e.name === "NotAllowedError" ? t("Setup cancelled.")
      : e.status === 403 ? (code === state.invite ? t("This invite is invalid, used or expired.") : t("Wrong setup code."))
      : e.message);
  } finally {
    state.busy = false;
    render();
  }
}

async function afterSignIn() {
  state.authed = true;
  state.hasPasskeys = true;
  await loadMe();
  if (route().name === "invite" || route().name === "") go("/inbox");
  else onRoute();
}

function guessDevice() {
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  if (/Android/.test(ua)) return "Android";
  if (/Macintosh/.test(ua)) return "Mac";
  if (/Windows/.test(ua)) return "Windows";
  return t("This device");
}

// ── push ──────────────────────────────────────────────────────────────────

async function enablePush() {
  try {
    if (isIOS() && !standalone()) throw new Error(t("Add it to the Home Screen and open it from the icon."));
    const perm = await Notification.requestPermission();
    if (perm !== "granted") throw new Error(t("Notifications are blocked in the device settings."));
    const reg = await navigator.serviceWorker.ready;
    const { key } = await api("/push/key");
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64urlToBytes(key) });
    await api("/push/subscribe", { method: "POST", body: sub.toJSON() });
    state.push.subscribed = true;
    toast(t("Notifications are on for this device."));
  } catch (e) {
    toast(e.message);
  }
  render();
}

async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration("/app/");
  const sub = reg && (await reg.pushManager.getSubscription());
  if (sub) {
    await api("/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } }).catch(() => {});
    await sub.unsubscribe();
  }
  state.push.subscribed = false;
  render();
}

// ── writing: drafts, replies, forwards ────────────────────────────────────

const MAX_ATTACH = 25 * 1024 * 1024;
let saveTimer = null;

const emailOf = (s) => ((/<([^>]+)>/.exec(s || "") || [])[1] || s || "").trim().toLowerCase();

// "Ana <a@x>, "Silva, B" <b@y>" → two entries: commas inside quotes or <> don't split.
function splitAddrs(text) {
  const out = [];
  let cur = "";
  let quoted = false;
  let angle = false;
  for (const ch of text || "") {
    if (ch === '"') quoted = !quoted;
    else if (ch === "<") angle = true;
    else if (ch === ">") angle = false;
    if ((ch === "," || ch === ";") && !quoted && !angle) {
      if (cur.trim()) out.push(cur.trim());
      cur = "";
    } else cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out.filter((a) => a.includes("@"));
}

function myAddresses() {
  const mine = new Set();
  for (const m of state.me.mailboxes) {
    mine.add(emailOf(m.address));
    m.from_options.forEach((f) => mine.add(emailOf(f)));
  }
  return mine;
}

function signature(box) {
  const s = (state.prefs?.signatures?.[box] || "").trim();
  return s ? `\n\n-- \n${s}` : "";
}

const longDate = (m) => new Date(m.ts * 1000).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" });

function quoted(m) {
  const lines = (m.body || "").replace(/\s+$/, "").split("\n").map((l) => (l ? `> ${l}` : ">")).join("\n");
  return `\n\n${t("On {date}, {sender} wrote:", { date: longDate(m), sender: m.from_raw || m.from })}\n${lines}`;
}

function forwarded(m) {
  return `\n\n${t("---------- Forwarded message ----------")}\n` +
    `${t("From:")} ${m.from_raw || m.from}\n${t("Date:")} ${longDate(m)}\n${t("Subject:")} ${m.subject}\n${t("To:")} ${m.to || ""}` +
    (m.cc ? `\nCc: ${m.cc}` : "") + `\n\n${m.body || ""}`;
}

// What the person wrote, ignoring From: opening the editor and closing it again
// (or only switching the sender) must not leave a draft behind.
const snapshot = (d) => JSON.stringify([d.to, d.cc, d.bcc, d.subject, d.body, d.attachments.length]);
const worthSaving = (d) => !!d.saved || snapshot(d) !== d.initial;

function blankDraft(key, mode, mailbox) {
  return { key, mode, mailbox, from: "", to: "", cc: "", bcc: "", showCc: false, subject: "", body: "",
    in_reply_to: null, references: null, attachments: [], saved: null, dirty: false, status: "", sig: "" };
}

function startDraft(mode, m, key) {
  const sendable = state.me.mailboxes.filter((x) => x.smtp);
  if (mode === "new") {
    const first = sendable.find((x) => x.name === state.box) || sendable[0];
    const d = blankDraft(key, mode, first?.name || "");
    d.sig = signature(d.mailbox);
    d.body = d.sig;
    d.initial = snapshot(d);
    state.draft = d;
    return;
  }
  const th = state.thread;
  const d = blankDraft(key, mode, th.mailbox);
  d.sig = signature(th.mailbox);
  const subject = m.subject || "";
  if (mode === "forward") {
    d.subject = /^(fwd?|enc|tr|rv|转发)\s*[:：]/i.test(subject) ? subject : `Fwd: ${subject}`;
    d.body = d.sig + forwarded(m);
    d.attachments = m.attachments.map((a) => ({ kind: "ref", ref: { mailbox: th.mailbox, folder: m.folder, uid: m.uid, index: a.index },
      filename: a.filename || t("attachment"), size: a.size }));
  } else {
    const mine = myAddresses();
    // Answering my own sent message means writing to its recipients again.
    const to = m.sent ? splitAddrs(m.to) : splitAddrs(m.reply_to || m.from_raw || m.from_address);
    d.to = to.join(", ");
    if (mode === "replyall") {
      const taken = new Set(to.map(emailOf));
      const others = [...(m.sent ? [] : splitAddrs(m.to)), ...splitAddrs(m.cc)].filter((a) => {
        const e = emailOf(a);
        if (mine.has(e) || taken.has(e)) return false;
        taken.add(e);
        return true;
      });
      d.cc = others.join(", ");
      d.showCc = !!d.cc;
    }
    d.subject = /^(re|aw|回复)\s*[:：]/i.test(subject) ? subject : `Re: ${subject}`;
    d.body = d.sig + quoted(m);
    d.in_reply_to = m.message_id;
    d.references = `${m.references || ""} ${m.message_id || ""}`.trim();
  }
  d.initial = snapshot(d);
  state.draft = d;
}

async function openDraft(box, uid) {
  const key = `draft:${box}/${uid}`;
  if (state.draft?.key === key) return render();
  await leaveDraft();
  state.draft = null;
  render();
  const x = await api(`/drafts/${enc(box)}/${enc(uid)}`);
  const options = state.me.mailboxes.find((m) => m.name === box)?.from_options || [];
  const at = options.findIndex((f) => emailOf(f) === emailOf(x.from));
  const d = blankDraft(key, "draft", box);
  Object.assign(d, {
    from: at > 0 ? options[at] : "", to: x.to, cc: x.cc, bcc: x.bcc, showCc: !!(x.cc || x.bcc),
    subject: x.subject, body: x.body, in_reply_to: x.in_reply_to, references: x.references,
    attachments: x.attachments.map((a) => ({ kind: "ref", ref: { mailbox: box, folder: x.folder, uid: x.uid, index: a.index },
      filename: a.filename || t("attachment"), size: a.size })),
    saved: { mailbox: box, uid: x.uid }, sig: signature(box),
  });
  d.initial = snapshot(d);
  state.draft = d;
  render();
}

function draftPayload(d) {
  return {
    mailbox: d.mailbox, from_address: d.from || null,
    to: splitAddrs(d.to), cc: splitAddrs(d.cc), bcc: splitAddrs(d.bcc),
    subject: d.subject, body_text: d.body, in_reply_to: d.in_reply_to, references: d.references,
    attachments: d.attachments.map((a) => (a.kind === "upload"
      ? { filename: a.filename, content_type: a.content_type, data: a.data } : { ref: a.ref })),
  };
}

function setDraftStatus(d, text) {
  d.status = text;
  const el = document.getElementById("draft-status");
  if (el && state.draft === d) el.textContent = text;
}

function touchDraft() {
  const d = state.draft;
  if (!d) return;
  d.dirty = true;
  d.confirmDiscard = false;
  clearTimeout(saveTimer);
  if (!d.noDrafts && worthSaving(d)) saveTimer = setTimeout(() => saveDraft(d), 2500);
}

// Saves a new version in the mailbox's Drafts folder and erases the previous
// one. Attachments then point at the saved draft, so they upload only once.
function saveDraft(d = state.draft) {
  if (!d || d.noDrafts) return Promise.resolve();
  clearTimeout(saveTimer);
  if (d.saving) {
    d.again = true;
    return d.saving;
  }
  if (!d.dirty || !worthSaving(d)) return Promise.resolve();
  d.dirty = false;
  const sent = d.attachments.slice();
  setDraftStatus(d, t("Saving…"));
  d.saving = (async () => {
    try {
      const r = await api("/drafts", { method: "PUT", body: { ...draftPayload(d), replace: d.saved } });
      d.saved = r.uid ? { mailbox: r.mailbox, uid: r.uid } : null;
      if (r.uid) {
        sent.forEach((a, i) => {
          const at = d.attachments.indexOf(a);
          if (at >= 0 && r.attachments[i]) {
            d.attachments[at] = { kind: "ref", ref: { mailbox: r.mailbox, folder: r.folder, uid: r.uid, index: r.attachments[i].index },
              filename: a.filename, size: a.size };
          }
        });
      }
      setDraftStatus(d, t("Draft saved {time}", { time: clock(new Date()) }));
      state.drafts = null;
    } catch (e) {
      d.dirty = true;
      if (e.status === 409) {
        d.noDrafts = true;
        setDraftStatus(d, t("This mailbox has no Drafts folder"));
      } else setDraftStatus(d, t("Draft not saved"));
    } finally {
      d.saving = null;
      if (d.again) {
        d.again = false;
        await saveDraft(d);
      }
    }
  })();
  return d.saving;
}

async function leaveDraft() {
  const d = state.draft;
  if (!d) return;
  clearTimeout(saveTimer);
  state.draft = null;
  if (d.dirty && !d.noDrafts && worthSaving(d)) {
    await saveDraft(d);
    if (d.saved) toast(t("Draft saved."));
  } else if (d.saving) await d.saving;
}

function closeCompose() {
  history.length > 1 ? history.back() : go("/inbox");
}

async function discardDraft() {
  const d = state.draft;
  if (!d.confirmDiscard) {
    d.confirmDiscard = true;
    render();
    return;
  }
  clearTimeout(saveTimer);
  state.draft = null;
  if (d.saving) await d.saving;
  if (d.saved?.uid) await api(`/drafts/${enc(d.saved.mailbox)}/${enc(d.saved.uid)}`, { method: "DELETE" }).catch((e) => toast(e.message));
  state.drafts = null;
  toast(t("Draft discarded."));
  d.mode === "draft" ? go("/drafts") : closeCompose();
}

async function addFiles(files) {
  const d = state.draft;
  const used = () => d.attachments.reduce((n, a) => n + (a.size || 0), 0);
  for (const f of files) {
    if (used() + f.size > MAX_ATTACH) {
      toast(t("Attachments are over 25 MB."));
      break;
    }
    const data = await new Promise((ok, fail) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result).split(",")[1] || "");
      r.onerror = () => fail(new Error(t("Couldn't read {name}.", { name: f.name })));
      r.readAsDataURL(f);
    });
    d.attachments.push({ kind: "upload", filename: f.name, content_type: f.type || "application/octet-stream", size: f.size, data });
  }
  touchDraft();
  render();
}

async function sendDraft() {
  const d = state.draft;
  if (!splitAddrs(d.to).length) return toast(t("Add a recipient."));
  clearTimeout(saveTimer);
  state.busy = true;
  render();
  try {
    if (d.saving) await d.saving;
    await api("/send", { method: "POST", body: { ...draftPayload(d), draft: d.saved } });
    toast(t("Sent."));
    state.draft = null;
    state.drafts = null;
    if (["reply", "replyall", "forward"].includes(d.mode)) {
      state.threadKey = null; // reload it to show the answer
      closeCompose();
    } else go(d.mode === "draft" ? "/drafts" : "/inbox");
  } catch (e) {
    toast(e.message);
  } finally {
    state.busy = false;
    render();
  }
}

function changeFrom(value) {
  const d = state.draft;
  const [box, from] = value.split("|");
  const sig = signature(box);
  const untouched = snapshot(d) === d.initial;
  if (d.sig && d.body.includes(d.sig)) d.body = d.body.replace(d.sig, sig);
  else if (!d.sig && sig && d.mode === "new" && !d.body.trim()) d.body = sig;
  d.sig = sig;
  if (untouched) d.initial = snapshot(d);
  d.mailbox = box;
  d.from = from;
  touchDraft();
  render();
}

// ── views ─────────────────────────────────────────────────────────────────

function authView() {
  const inviting = !!state.invite;
  // First device without an invite link: the setup code from the server's env.
  const bySetup = !inviting && !state.hasPasskeys && state.setupCode;
  let nameInput, codeInput;
  if (bySetup) {
    const submit = () => register(nameInput.value.trim() || guessDevice(), codeInput.value.trim());
    return h("main", { class: "auth" },
      h("div", {},
        h("div", { class: "brand" }, "mailgrant", h("i", {}, ".")),
        h("p", {}, t("First sign-in. Enter the setup code and create this device's passkey.")),
      ),
      h("form", { class: "actions", onSubmit: (e) => { e.preventDefault(); submit(); } },
        (codeInput = h("input", { "aria-label": t("Setup code"), placeholder: t("Setup code"),
          autocomplete: "one-time-code", autocapitalize: "off", spellcheck: "false", required: true })),
        (nameInput = h("input", { "aria-label": t("This device's name"), value: guessDevice(), maxlength: 60 })),
        h("button", { class: "btn", type: "submit", disabled: state.busy }, icon("face"), t("Create passkey")),
        h("p", { class: "foot" }, t("The code is the server's MAILGRANT_SETUP_CODE. It stops working once the first passkey exists.")),
      ),
    );
  }
  return h("main", { class: "auth" },
    h("div", {},
      h("div", { class: "brand" }, "mailgrant", h("i", {}, ".")),
      h("p", {}, inviting ? t("Create this device's passkey. It uses Face ID, your fingerprint or the device passcode.") : t("All your mailboxes in one place, and what the agents did in them.")),
    ),
    h("div", { class: "actions" },
      inviting && (nameInput = h("input", { "aria-label": t("This device's name"), value: guessDevice(), maxlength: 60 })),
      h("button", { class: "btn", disabled: state.busy, onClick: () => (inviting ? register(nameInput.value.trim() || guessDevice()) : signIn()) },
        icon("face"), inviting ? t("Create passkey") : t("Sign in with passkey")),
      h("p", { class: "foot" }, inviting ? t("The invite works only once.") :
        state.hasPasskeys ? t("First time on this device? Create an invite in Settings on a device that is already signed in.") :
        t("No passkey yet. On the server, run mailgrant invite and open the link here.")),
    ),
  );
}

function sidebar(r, drawer = false) {
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const inList = LIST_VIEWS.includes(r.name) || r.name === "m";
  const at = (view, box = "all") => inList && state.view === view && (view !== "inbox" || state.box === box) ? "page" : null;
  return h("aside", { class: drawer ? "side drawer" : "side", "aria-label": t("Menu") },
    h("div", { class: "wordmark" }, h("span", {}, "mailgrant", h("i", {}, ".")),
      drawer && h("button", { type: "button", class: "icon-btn plain drawer-close", "aria-label": t("Close menu"), onClick: () => { state.drawer = false; render(); } }, icon("close"))),
    can("send") && h("a", { href: "#/compose", class: "btn small side-compose" }, t("Compose")),
    h("nav", { "aria-label": t("Folders") },
      h("a", { href: "#/inbox", "aria-current": at("inbox") },
        h("span", {}, t("All mailboxes")), state.total ? h("span", { class: "count" }, state.total) : null),
      h("a", { href: "#/starred", "aria-current": at("starred") }, h("span", {}, t("Starred"))),
      h("a", { href: "#/sent", "aria-current": at("sent") }, h("span", {}, t("Sent"))),
      can("send") && h("a", { href: "#/drafts", "aria-current": at("drafts") }, h("span", {}, t("Drafts")))),
    h("nav", { "aria-label": t("Mailboxes") },
      h("span", { class: "side-label" }, t("Mailboxes")),
      boxes.map((m) => h("a", { href: `#/inbox/${enc(m.name)}`, "aria-current": at("inbox", m.name) },
        h("span", {}, m.address), state.counts[m.name] ? h("span", { class: "count" }, state.counts[m.name]) : null)),
    ),
    h("nav", { class: "bottom", "aria-label": t("More") },
      h("a", { href: "#/agents", "aria-current": r.name === "agents" ? "page" : null }, h("span", {}, t("Agents"))),
      h("a", { href: "#/settings", "aria-current": r.name === "settings" ? "page" : null }, h("span", {}, t("Settings"))),
    ),
  );
}

// Swipe right: read/unread. Swipe left: archive. Long press: select.
function attachGestures(wrap, row, m) {
  let x0 = 0, y0 = 0, dx = 0, pid = null, active = false, swiping = false, press = null;
  const settle = () => {
    row.classList.remove("dragging");
    row.style.transform = "";
    wrap.classList.remove("swipe-left", "swipe-right", "armed");
  };
  row.addEventListener("click", (e) => {
    if (Date.now() - (row._gestureAt || 0) < 600) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  wrap.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || e.target.closest(".star")) return;
    x0 = e.clientX; y0 = e.clientY; dx = 0; pid = e.pointerId; active = true; swiping = false;
    press = setTimeout(() => {
      if (!active || swiping) return;
      active = false;
      row._gestureAt = Date.now();
      gesture = { pressed: true, at: row._gestureAt };
      navigator.vibrate?.(10);
      startSelecting(rowKey(m));
    }, 550);
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!active || e.pointerId !== pid) return;
    const mx = e.clientX - x0;
    const my = e.clientY - y0;
    if (!swiping) {
      if (Math.abs(my) > 10) { active = false; clearTimeout(press); return; }
      if (Math.abs(mx) < 12) return;
      swiping = true;
      clearTimeout(press);
      row.classList.add("dragging");
      try { wrap.setPointerCapture(pid); } catch (_) { /* pointer already gone */ }
    }
    dx = Math.max(-150, Math.min(150, mx));
    row.style.transform = `translateX(${dx}px)`;
    wrap.classList.toggle("swipe-right", dx > 0);
    wrap.classList.toggle("swipe-left", dx < 0);
    wrap.classList.toggle("armed", Math.abs(dx) > 80);
  });
  const end = () => {
    clearTimeout(press);
    if (gesture.pressed) gesture = { pressed: false, at: Date.now() };
    if (!active) return;
    active = false;
    if (!swiping) return;
    row._gestureAt = Date.now();
    row.classList.remove("dragging");
    if (dx > 80) { settle(); actOnRows(m.unread ? "seen" : "unseen", [m]); }
    else if (dx < -80) { row.style.transform = "translateX(-100%)"; setTimeout(() => actOnRows("archive", [m]), 180); }
    else settle();
  };
  wrap.addEventListener("pointerup", end);
  wrap.addEventListener("pointercancel", () => {
    clearTimeout(press);
    if (gesture.pressed) gesture = { pressed: false, at: Date.now() };
    if (active && swiping) settle();
    active = false;
  });
}

function rowView(m) {
  const key = rowKey(m);
  const selected = state.selected.has(key);
  const cls = `row${m.unread ? " unread" : ""}${selected ? " selected" : ""}`;
  const kids = [
    state.selecting ? h("span", { class: `check${selected ? " on" : ""}`, "aria-hidden": "true" }, selected && icon("check"))
      : m.unread && h("span", { class: "dot", "aria-label": t("Unread") }),
    h("div", { class: "top" },
      h("span", { class: "from" }, m.from || m.from_address),
      m.count > 1 && h("span", { class: "thread-n mono" }, m.count),
      h("span", { class: "mono" }, when(m.ts))),
    h("span", { class: "subject" }, m.subject || t("(no subject)")),
    h("span", { class: "mono" }, m.mark ? `${m.mailbox_address} · ${markText(m.mark)}` : m.mailbox_address),
  ];
  const row = state.selecting
    ? h("button", { type: "button", class: cls, "aria-pressed": selected ? "true" : "false", onClick: () => toggleSelect(key) }, kids)
    : h("a", { class: cls, href: `#/m/${enc(m.mailbox)}/${enc(m.uid)}`, "aria-current": state.thread && rowsOf(state.thread).includes(m) ? "true" : null }, kids);
  const star = !state.selecting && (can("mark") || m.flagged) && h("button", {
    type: "button", class: `star${m.flagged ? " on" : ""}`, disabled: !can("mark"),
    "aria-label": m.flagged ? t("Remove star") : t("Add star"), "aria-pressed": m.flagged ? "true" : "false",
    onClick: (e) => { e.preventDefault(); actOnRows(m.flagged ? "unflag" : "flag", [m]); },
  }, icon("star"));
  const wrap = h("div", { class: "row-wrap" },
    h("div", { class: "swipe-bg read", "aria-hidden": "true" }, icon(m.unread ? "mailOpen" : "mail"), m.unread ? t("Read") : t("Unread")),
    h("div", { class: "swipe-bg arch", "aria-hidden": "true" }, t("Archive"), icon("archive")),
    row, star);
  if (!state.selecting && can("mark") && !WIDE.matches) attachGestures(wrap, row, m);
  return wrap;
}

function sentRow(m) {
  const rcpts = m.to || [];
  const to = rcpts.length ? t("To {who}", { who: `${rcpts[0]}${rcpts.length > 1 ? ` +${rcpts.length - 1}` : ""}` }) : t("(no recipient)");
  const by = m.sent_by ? t("{agent} sent", { agent: m.sent_by }) : m.by_you ? t("you") : null;
  return h("a", { class: "row", href: `#/m/${enc(m.mailbox)}/${enc(m.uid)}/${enc(m.folder)}`,
    "aria-current": state.threadKey === `${m.mailbox}/${m.folder}/${m.uid}` ? "true" : null },
    h("div", { class: "top" }, h("span", { class: "from" }, to), h("span", { class: "mono" }, when(m.ts))),
    h("span", { class: "subject" }, m.subject || t("(no subject)")),
    h("span", { class: "mono" }, by ? [m.mailbox_address, " · ", h("span", { class: m.sent_by ? "by-agent" : null }, by)] : m.mailbox_address));
}

function menuButton() {
  return h("button", { type: "button", class: "icon-btn plain menu-btn", "aria-label": t("Open menu"),
    onClick: () => { state.drawer = true; render(); } }, icon("menu"));
}

function draftRow(d) {
  return h("a", { class: "row", href: `#/draft/${enc(d.mailbox)}/${enc(d.uid)}`,
    "aria-current": state.draft?.key === `draft:${d.mailbox}/${d.uid}` ? "true" : null },
    h("div", { class: "top" }, h("span", { class: "from" }, d.to ? t("To {who}", { who: d.to }) : t("(no recipient)")), h("span", { class: "mono" }, when(d.ts))),
    h("span", { class: "subject" }, d.subject || t("(no subject)")),
    h("span", { class: "mono" }, d.mailbox_address));
}

function selectionBar() {
  const rows = selectedRows();
  const allRead = rows.length > 0 && rows.every((r) => !r.unread);
  const allStarred = rows.length > 0 && rows.every((r) => r.flagged);
  const tool = (name, label, action) => h("button", { type: "button", class: "tool", disabled: !rows.length,
    onClick: async () => { await actOnRows(action, rows); stopSelecting(); } }, icon(name), h("span", {}, label));
  return h("div", { class: "selbar", role: "toolbar", "aria-label": t("Actions on the selected messages") },
    tool(allRead ? "mail" : "mailOpen", allRead ? t("Unread") : t("Read"), allRead ? "unseen" : "seen"),
    tool("star", allStarred ? t("Unstar") : t("Star"), allStarred ? "unflag" : "flag"),
    tool("archive", t("Archive"), "archive"),
    can("delete") && tool("trash", t("Trash"), "trash"));
}

function listPane() {
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const current = state.view === "inbox" ? boxByName(state.box) : null;
  const drafts = state.view === "drafts";
  let search;
  const doSearch = () => { state.q = search.value.trim(); state.limit = 40; loadList(true); };
  const unreadHere = state.box === "all" ? state.total : state.counts[state.box] || 0;
  const sent = state.view === "sent";
  const title = state.view === "inbox" ? (current ? current.address : WIDE.matches ? t("All mailboxes") : t("Inbox")) : viewTitle(state.view);
  const sub = sent ? t("By you and the agents, in every mailbox") :
    state.view === "starred" ? tn(state.list.length, "{n} message", "{n} messages") :
    drafts ? tn((state.drafts || []).length, "{n} draft", "{n} drafts") :
    `${tn(unreadHere, "{n} unread", "{n} unread")} · ${tn(boxes.length, "{n} mailbox", "{n} mailboxes")}`;
  const n = state.selected.size;
  const chip = (label, href, pressed, count) => h("a", { class: "chip", href, "aria-pressed": pressed ? "true" : "false" },
    label, count ? h("span", { class: "n" }, count) : null);
  const head = state.selecting
    ? h("div", { class: "hdr-row sel-row" },
        h("button", { type: "button", class: "btn quiet small bare", onClick: () => stopSelecting() }, t("Cancel")),
        h("strong", { class: "bar-title" }, n ? tn(n, "{n} selected", "{n} selected") : t("Select messages")),
        h("button", { type: "button", class: "btn quiet small bare", onClick: () => {
          state.selected = n === state.list.length ? new Set() : new Set(state.list.map(rowKey)); render(); } },
          n === state.list.length && n ? t("None") : t("All")))
    : h("div", { class: "hdr-row" },
        h("div", { class: "hdr-title" }, menuButton(), h("div", {}, h("h1", { class: "title" }, title), h("div", { class: "sub" }, sub))),
        h("div", { class: "hdr-actions" },
          !drafts && !sent && can("mark") && state.list.length > 0 && h("button", { type: "button", class: "btn quiet small", onClick: () => startSelecting() }, t("Select")),
          can("send") && h("a", { href: "#/compose", class: "icon-btn", "aria-label": t("Write an email") }, icon("pencil"))));
  return h("section", { class: "pane pane-list", "aria-label": t("Messages") },
    h("header", { class: "hdr" },
      head,
      !drafts && !state.selecting && h("label", { class: "search" }, icon("search"),
        search = h("input", { id: "q", type: "search", placeholder: t("Search"), "aria-label": t("Search the mailboxes"), value: state.q,
          onKeydown: (e) => e.key === "Enter" && doSearch(), onSearch: doSearch })),
      !state.selecting && h("div", { class: "chips", role: "group", "aria-label": t("Filter") },
        chip(t("All"), "#/inbox", state.view === "inbox" && state.box === "all", state.total),
        chip(t("Starred"), "#/starred", state.view === "starred"),
        chip(t("Sent"), "#/sent", sent),
        can("send") && chip(t("Drafts"), "#/drafts", drafts),
        boxes.map((m) => chip(m.address, `#/inbox/${enc(m.name)}`, state.view === "inbox" && state.box === m.name, state.counts[m.name])))),
    h("div", { class: "scroll", "data-key": `list:${state.view}|${state.box}|${state.q}` },
      state.listErrors.map((e) => h("div", { class: "err" }, `${e.mailbox}: ${e.error}`)),
      drafts ? (
        state.drafts === null ? h("div", { class: "empty" }, t("Loading…")) :
        !state.drafts.length ? h("div", { class: "empty" }, t("No drafts. Whatever you start writing is kept here.")) :
        h("div", { class: "rows" }, state.drafts.map(draftRow))
      ) : (
        state.loadingList && !state.list.length ? h("div", { class: "empty" }, t("Loading…")) :
        !state.list.length ? h("div", { class: "empty" }, state.q ? t("Nothing found.") : state.view === "starred" ? t("No starred messages.") :
          sent ? t("Nothing sent yet. What you and the agents send shows up here.") : t("No messages here.")) :
        h("div", { class: "rows" }, state.list.map(sent ? sentRow : rowView))
      ),
      !drafts && state.fetched >= state.limit && h("button", { class: "more", onClick: () => { state.limit += 40; loadList(true); } },
        state.loadingList ? t("Loading…") : t("Load older messages")),
    ),
    state.selecting && selectionBar(),
  );
}

// ── a conversation ─────────────────────────────────────────────────────────

function replyHref(kind, th, m) {
  return `#/${kind}/${enc(th.mailbox)}/${enc(m.uid)}/${enc(m.folder)}`;
}

// ── HTML mail ─────────────────────────────────────────────────────────────

// Each render rebuilds the page, and an iframe reloads when it is re-inserted.
// The browser cache answers the reload; remembering the height keeps the
// conversation from jumping while it does.
const frameHeights = new Map();
const senderDomain = (m) => (m.from_address || "").split("@").pop().toLowerCase();

function imagesShown(th, m) {
  const p = state.prefs || {};
  return !m.remote_images || p.images || (p.image_senders || []).includes(senderDomain(m)) || state.showImages.has(`${th.mailbox}/${msgKey(m)}`);
}

function fitFrame(frame, key) {
  const doc = frame.contentDocument;
  const root = doc?.documentElement;
  const body = doc?.body;
  if (!root || !body) return;
  // Mail laid out for 600px is scaled down to the screen instead of scrolling
  // sideways, the way phone mail apps do. A transform, not CSS zoom: browsers
  // disagree on how zoom shows up in measurements, and agree on transforms.
  const measure = () => {
    const height = Math.ceil(body.getBoundingClientRect().height);
    if (height && Math.abs(height - frame.offsetHeight) > 1) {
      frame.style.height = `${height}px`;
      frameHeights.set(key, height);
    }
  };
  const scale = () => {
    ["width", "transform", "box-sizing"].forEach((k) => body.style.removeProperty(k));
    root.style.removeProperty("overflow");
    const wide = root.scrollWidth;
    const room = frame.clientWidth;
    if (wide > room + 2) {
      body.style.setProperty("box-sizing", "border-box", "important");
      body.style.setProperty("width", `${wide}px`, "important");
      body.style.setProperty("transform", `scale(${room / wide})`, "important");
      body.style.setProperty("transform-origin", "0 0", "important");
      root.style.setProperty("overflow", "hidden", "important");
    }
    measure();
  };
  scale();
  new ResizeObserver(measure).observe(body);
  // An image arriving late can widen the layout; that needs a new scale.
  doc.querySelectorAll("img").forEach((img) => img.complete || img.addEventListener("load", scale, { once: true }));
}

function mailFrame(th, m) {
  const images = imagesShown(th, m);
  const key = `${th.mailbox}/${msgKey(m)}${images ? "+img" : ""}`;
  const src = `${API}/messages/${enc(th.mailbox)}/${enc(m.uid)}/html?folder=${enc(m.folder)}${images && m.remote_images ? "&images=1" : ""}`;
  const frame = h("iframe", {
    class: "mail-frame", src, title: t("Message from {who}", { who: m.from || m.from_address }),
    sandbox: "allow-same-origin allow-popups allow-popups-to-escape-sandbox", referrerpolicy: "no-referrer",
  });
  if (frameHeights.has(key)) frame.style.height = `${frameHeights.get(key)}px`;
  // Not the load event: it waits for every image, and a slow tracking pixel
  // would leave the frame at its default height. The text is enough to start.
  let tries = 0;
  const ready = () => {
    const doc = frame.contentDocument;
    if (doc && doc.URL !== "about:blank" && doc.readyState !== "loading" && doc.body) return fitFrame(frame, key);
    if (++tries < 200 && (frame.isConnected || tries < 5)) setTimeout(ready, 50);
  };
  setTimeout(ready, 0);
  return frame;
}

function imagesBar(th, m) {
  if (imagesShown(th, m)) return null;
  const domain = senderDomain(m);
  const show = () => { state.showImages.add(`${th.mailbox}/${msgKey(m)}`); render(); };
  const always = async () => {
    const list = [...new Set([...(state.prefs.image_senders || []), domain])];
    state.prefs = await api("/prefs", { method: "PUT", body: { image_senders: list } });
    render();
  };
  return h("div", { class: "images-bar" },
    h("span", { class: "grow" }, t("Remote images are blocked. They tell the sender when you open the email.")),
    h("button", { type: "button", class: "btn quiet small bare", onClick: show }, t("Show")),
    domain && h("button", { type: "button", class: "btn quiet small bare", onClick: always }, t("Always from {domain}", { domain })));
}

function threadMessageView(th, m, isLast) {
  const open = state.expanded.has(msgKey(m));
  const many = th.messages.length > 1;
  const who = m.sent ? t("You") : m.from || m.from_address;
  const toggle = () => { open ? state.expanded.delete(msgKey(m)) : state.expanded.add(msgKey(m)); render(); };
  if (!open) {
    return h("button", { type: "button", class: `tmsg folded${m.unread ? " unread" : ""}`, onClick: toggle },
      h("div", { class: "top" }, h("span", { class: "from" }, who), h("span", { class: "mono" }, when(m.ts))),
      h("span", { class: "snippet" }, (m.body || "").replace(/\s+/g, " ").slice(0, 140) || t("(no text)")));
  }
  const path = `/messages/${enc(th.mailbox)}/${enc(m.uid)}`;
  const recipients = [m.to && t("to {who}", { who: m.to }), m.cc && `cc ${m.cc}`].filter(Boolean).join(" · ");
  return h("div", { class: "tmsg" },
    h(many ? "button" : "div", { type: many ? "button" : null, class: "tmsg-head", onClick: many ? toggle : null },
      h("div", { class: "top" }, h("strong", {}, who), h("span", { class: "mono" }, when(m.ts, { withTime: true }))),
      h("span", { class: "mono addr" }, m.sent ? `${m.from_address} · ${t("Sent")}` : m.from_address),
      recipients && h("span", { class: "mono addr" }, recipients)),
    m.html ? [imagesBar(th, m), mailFrame(th, m)] : h("div", { class: "body" }, linkify(m.body || t("(this message has no text)"))),
    m.attachments.map((a) => h("a", { class: "attach", href: `${API}${path}/attachments/${a.index}?folder=${enc(m.folder)}`, download: a.filename || t("attachment") },
      icon("file"), h("span", {}, a.filename || t("attachment")), h("span", { class: "mono" }, size(a.size)))),
    th.can.reply && many && !isLast && h("div", { class: "tmsg-actions" },
      h("a", { class: "btn quiet small bare", href: replyHref("reply", th, m) }, t("Reply")),
      h("a", { class: "btn quiet small bare", href: replyHref("replyall", th, m) }, t("Reply all")),
      h("a", { class: "btn quiet small bare", href: replyHref("forward", th, m) }, t("Forward"))));
}

function threadActions(th) {
  const inbox = th.messages.filter((m) => m.folder === th.folder);
  const newest = inbox[inbox.length - 1];
  const flagged = inbox.some((m) => m.flagged);
  const items = (uids) => uids.map((uid) => ({ mailbox: th.mailbox, uid }));
  const leave = () => { clearThread(); go(listHref().slice(1)); };
  const run = async (fn) => { try { await fn(); } catch (e) { toast(e.message); } render(); };
  return {
    flagged,
    star: () => run(async () => {
      if (!newest) return;
      await batch(flagged ? "unflag" : "flag", items(flagged ? th.members : [newest.uid]), { folder: th.folder });
      inbox.forEach((m) => (m.flagged = !flagged && m === newest));
      rowsOf(th).forEach((r) => (r.flagged = !flagged));
      if (flagged && state.view === "starred") state.list = state.list.filter((r) => !rowsOf(th).includes(r));
    }),
    unread: () => run(async () => {
      if (!newest) return;
      await batch("unseen", items([newest.uid]), { folder: th.folder });
      rowsOf(th).forEach((r) => (r.unread = true));
      refreshCounts();
      leave();
    }),
    move: (action) => run(async () => {
      const res = await batch(action, items(th.members), { folder: th.folder });
      const gone = rowsOf(th);
      state.list = state.list.filter((r) => !gone.includes(r));
      toast(action === "archive" ? t("Conversation archived.") : res.moved_to?.[th.mailbox] ? t("Moved to {folder}.", { folder: res.moved_to[th.mailbox] }) : t("Conversation moved to the trash."));
      refreshCounts();
      leave();
    }),
  };
}

function messagePane() {
  const th = state.thread;
  if (!th) return h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, state.threadKey ? t("Opening…") : t("Select a message.")));
  const msgs = th.messages;
  const last = msgs[msgs.length - 1];
  const opened = msgs.find((m) => m.opened) || last;
  const a = threadActions(th);
  const hasInbox = th.members.length > 0;
  const iconBtn = (name, label, fn, on) => h("button", { type: "button", class: `icon-btn plain${on ? " on" : ""}`, "aria-label": label, title: label,
    "aria-pressed": on === undefined ? null : on ? "true" : "false", onClick: fn }, icon(name));
  // A function, not an array: the phone bar and the desktop bar each need their own nodes.
  const tools = () => [
    th.can.mark && hasInbox && iconBtn("star", a.flagged ? t("Remove star") : t("Add star"), a.star, a.flagged),
    th.can.archive && hasInbox && iconBtn("archive", t("Archive"), () => a.move("archive")),
    th.can.mark && hasInbox && iconBtn("mail", t("Mark as unread"), a.unread),
    th.can.trash && hasInbox && iconBtn("trash", t("Move to the trash"), () => a.move("trash")),
  ];
  return h("section", { class: "pane pane-detail", "aria-label": t("Conversation") },
    h("div", { class: "detail-bar" },
      h("a", { class: "back", href: listHref() }, icon("back"), viewTitle(state.view) || t("Inbox")),
      h("div", { class: "bar-tools" }, tools())),
    h("div", { class: "detail-tools", hidden: true },
      th.can.reply && h("a", { class: "btn small", href: replyHref("reply", th, last) }, icon("reply"), t("Reply")),
      th.can.reply && h("a", { class: "btn small ghost", href: replyHref("replyall", th, last) }, icon("replyAll"), t("Reply all")),
      th.can.reply && h("a", { class: "btn small ghost", href: replyHref("forward", th, last) }, icon("forward"), t("Forward")),
      h("span", { class: "spacer" }),
      tools()),
    h("div", { class: "scroll", "data-key": `m:${state.threadKey}` },
      h("article", { class: "msg" },
        h("div", { class: "msg-head" },
          h("h1", {}, opened.subject || t("(no subject)")),
          h("span", { class: "mono" }, msgs.length > 1 ? `${tn(msgs.length, "{n} message", "{n} messages")} · ${th.mailbox_address}` : th.mailbox_address),
          th.agents.map((x) => h("span", { class: "agent-line" }, `${markText(x)} ${when(x.ts, { withTime: true })}`))),
        h("div", { class: "thread" }, msgs.map((m, i) => threadMessageView(th, m, i === msgs.length - 1))))),
    th.can.reply && h("div", { class: "detail-foot" },
      h("a", { class: "btn", href: replyHref("reply", th, last) }, t("Reply")),
      h("a", { class: "icon-btn", href: replyHref("replyall", th, last), "aria-label": t("Reply all") }, icon("replyAll")),
      h("a", { class: "icon-btn", href: replyHref("forward", th, last), "aria-label": t("Forward") }, icon("forward"))),
  );
}

function size(bytes) {
  if (!bytes) return "0 KB";
  const mb = (bytes / 1048576).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return bytes >= 1048576 ? `${mb} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// What an agent did to a message: the API sends a code, the words are ours.
const markText = (x) => (x.what === "replied" ? t("{agent} replied", { agent: x.agent }) : t("{agent} read it", { agent: x.agent }));

// ── the editor ─────────────────────────────────────────────────────────────

function composePane() {
  const d = state.draft;
  if (!d) return h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, t("Opening…")));
  const sendable = state.me.mailboxes.filter((m) => m.smtp);
  const answering = ["reply", "replyall"].includes(d.mode) || (d.mode === "draft" && d.in_reply_to);
  const options = (answering ? sendable.filter((m) => m.name === d.mailbox) : sendable).flatMap((m) =>
    m.from_options.map((f, i) => ({ value: `${m.name}|${i === 0 ? "" : f}`, label: f })));
  const bind = (field) => (e) => { d[field] = e.target.value; touchDraft(); };
  const title = { new: t("New email"), reply: t("title|Reply"), replyall: t("title|Reply all"), forward: t("Forward"), draft: t("Draft") }[d.mode];
  const field = (id, label, value, extra = {}) => h("div", { class: "field" }, h("label", { for: id }, label),
    h("input", { id, value, onInput: bind(id), autocapitalize: id === "subject" ? null : "off", spellcheck: id === "subject" ? null : "false",
      inputmode: id === "subject" ? null : "email", autocomplete: id === "subject" ? "off" : "email", ...extra }));
  const files = h("input", { id: "files", type: "file", multiple: true, class: "sr", tabindex: "-1",
    onChange: (e) => { addFiles([...e.target.files]).catch((err) => toast(err.message)); e.target.value = ""; } });
  return h("section", { class: "pane pane-detail", "aria-label": title },
    h("div", { class: "compose-bar" },
      h("button", { type: "button", class: "btn quiet small", onClick: closeCompose }, t("Close")),
      h("strong", { class: "bar-title" }, title),
      h("div", { class: "bar-tools" },
        worthSaving(d) && h("button", { type: "button", class: d.confirmDiscard ? "btn quiet small danger" : "icon-btn plain",
          "aria-label": t("Discard draft"), title: t("Discard draft"), onClick: discardDraft }, d.confirmDiscard ? t("Discard?") : icon("trash")),
        h("button", { type: "button", class: "btn small", disabled: state.busy, onClick: sendDraft }, state.busy ? t("Sending…") : t("Send")))),
    h("div", { class: "scroll col", "data-key": `c:${d.key}` },
      h("div", { class: "field" }, h("label", { for: "from" }, t("From")),
        h("select", { id: "from", onChange: (e) => changeFrom(e.target.value) },
          options.map((o) => h("option", { value: o.value, selected: o.value === `${d.mailbox}|${d.from}` ? true : null }, o.label)))),
      h("div", { class: "field" }, h("label", { for: "to" }, t("To")),
        h("input", { id: "to", value: d.to, onInput: bind("to"), inputmode: "email", autocomplete: "email", autocapitalize: "off", spellcheck: "false" }),
        !d.showCc && h("button", { type: "button", class: "btn quiet small bare", onClick: () => { d.showCc = true; render(); document.getElementById("cc")?.focus(); } }, t("Cc Bcc"))),
      d.showCc && field("cc", "Cc", d.cc),
      d.showCc && field("bcc", t("Bcc"), d.bcc),
      field("subject", t("Subject"), d.subject),
      d.attachments.length > 0 && h("div", { class: "att-list" }, d.attachments.map((x, i) =>
        h("span", { class: "att" }, icon("file"), h("span", { class: "att-name" }, x.filename), h("span", { class: "mono" }, size(x.size)),
          h("button", { type: "button", class: "att-x", "aria-label": t("Remove {name}", { name: x.filename }),
            onClick: () => { d.attachments.splice(i, 1); touchDraft(); render(); } }, icon("close"))))),
      h("textarea", { id: "body", class: "editor", "aria-label": t("Message"), onInput: bind("body") }, d.body),
      h("div", { class: "compose-foot" },
        files,
        h("label", { for: "files", class: "btn ghost small" }, icon("clip"), t("Attach")),
        h("span", { id: "draft-status", class: "mono" }, d.status)),
      h("p", { class: "note" }, answering ? t("Goes in the same conversation and is kept in the Sent folder of {mailbox}.", { mailbox: boxByName(d.mailbox)?.address || "" }) :
        t("Kept in the Sent folder of the chosen mailbox. The draft saves itself while you write."))),
  );
}

function describe(e) {
  const to = (e.to || []).join(", ");
  if (e.outcome === "denied") {
    const action = { delete_message: t("Not allowed to delete."), send: t("Not allowed to send."), mark_seen: t("Not allowed to mark messages.") }[e.action];
    return [t("{agent} was blocked", { agent: e.agent }),
      e.reason === "not_found" ? t("Tried to use a mailbox outside its permission.") :
      e.reason === "from_address" ? t("Tried to send with a sender that isn't this mailbox's.") :
      action || t("Not allowed to {action}.", { action: e.action })];
  }
  if (e.outcome === "error") return [t("{agent}: {action} failed", { agent: e.agent, action: e.action }), t("The mail server refused.")];
  if (e.action === "send") return [t("{agent} sent an email", { agent: e.agent }), to ? t("To {who}.", { who: to }) : ""];
  if (e.action === "get_message") return [t("{agent} read a message", { agent: e.agent }), ""];
  if (e.action === "mark_seen") return [t("{agent} marked it as read", { agent: e.agent }), ""];
  if (e.action === "delete_message") return [t("{agent} moved it to the trash", { agent: e.agent }), e.moved_to ? t("Folder {folder}.", { folder: e.moved_to }) : ""];
  return [`${e.agent}: ${e.action}`, ""];
}

function agentsPane() {
  const kinds = [["all", t("Everything")], ["sent", t("Sends")], ["denied", t("Blocked")]];
  const events = state.activity || [];
  const groups = [];
  for (const e of events) {
    const label = dayLabel(e.ts);
    if (!groups.length || groups[groups.length - 1].label !== label) groups.push({ label, items: [] });
    groups[groups.length - 1].items.push(e);
  }
  return h("section", { class: "pane pane-detail", "aria-label": t("Agents") },
    h("header", { class: "hdr" },
      h("div", { class: "hdr-title" }, menuButton(), h("div", {}, h("h1", { class: "title" }, t("Agents")), h("div", { class: "sub" }, t("What each one read, marked and sent")))),
      h("div", { class: "seg", role: "group", "aria-label": t("Filter") }, kinds.map(([k, label]) =>
        h("button", { type: "button", class: "chip", "aria-pressed": state.actKind === k ? "true" : "false",
          onClick: () => { state.actKind = k; loadActivity(); } }, label)))),
    h("div", { class: "scroll ruled", "data-key": "agents" },
      state.activity === null ? h("div", { class: "empty" }, t("Loading…")) :
      !events.length ? h("div", { class: "empty" }, t("No activity yet.")) :
      groups.map((g) => [h("h2", { class: "day" }, g.label), g.items.map((e) => {
        const [what, detail] = describe(e);
        const kind = e.outcome === "denied" ? "denied" : e.action === "send" ? "sent" : "";
        const link = e.action === "get_message" && e.outcome === "ok" && e.uid && e.mailbox_name;
        return h(link ? "a" : "div", { class: `event ${kind}`, href: link ? `#/m/${encodeURIComponent(e.mailbox_name)}/${encodeURIComponent(e.uid)}` : null },
          h("span", { class: "mono time" }, clock(new Date(e.ts))),
          h("div", { class: "ev-body" },
            h("span", { class: "what" }, what), detail && h("span", { class: "ev-detail" }, detail),
            e.mailbox && h("span", { class: "mono" }, e.mailbox)));
      })]),
    ),
  );
}

function settingsPane() {
  const p = state.prefs;
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const savePrefs = async (patch) => { state.prefs = await api("/prefs", { method: "PUT", body: patch }); render(); };
  const sw = (checked, label, onChange) => h("button", { type: "button", class: "switch", role: "switch", "aria-checked": checked ? "true" : "false", "aria-label": label, onClick: onChange });
  const needsInstall = isIOS() && !standalone();
  const invite = async () => {
    const r = await api("/invites", { method: "POST" });
    state.newInvite = r.url;
    render();
  };
  return h("section", { class: "pane pane-detail", "aria-label": t("Settings") },
    h("header", { class: "hdr" }, h("div", { class: "hdr-title" }, menuButton(), h("h1", { class: "title" }, t("Settings")))),
    h("div", { class: "scroll padded", "data-key": "settings" },
      state.me.manage && manageSections(),
      h("section", { class: "section" + (state.me.manage ? "" : " first") },
        h("h2", {}, t("Notifications")),
        h("div", { class: "box" },
          needsInstall ? [
            h("strong", { class: "medium" }, t("On iPhone, notifications only arrive with mailgrant on the Home Screen.")),
            h("ol", {}, h("li", {}, t("Tap Share in Safari.")), h("li", {}, t("Choose Add to Home Screen.")), h("li", {}, t("Open it from the icon and come back here."))),
          ] : !state.push.supported ? h("span", {}, t("This browser can't receive notifications.")) :
          state.push.subscribed ? [
            h("span", {}, t("On for this device.")),
            h("div", { class: "btn-row" },
              h("button", { class: "btn ghost small", onClick: async () => { const r = await api("/push/test", { method: "POST" }); toast(r.sent ? t("push|Sent.") : t("No device received it.")); } }, t("Test")),
              h("button", { class: "btn quiet small", onClick: disablePush }, t("Turn off"))),
          ] : [
            h("span", {}, t("Get a notification when email arrives in the mailboxes chosen below.")),
            h("button", { class: "btn", onClick: enablePush }, t("Turn on notifications")),
          ]),
        p && h("div", { class: "plain" },
          boxes.map((m) => h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, m.address)),
            sw(p.notify[m.name], t("Notify for {mailbox}", { mailbox: m.address }), () => savePrefs({ notify: { [m.name]: !p.notify[m.name] } })))),
          h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, t("Notify me when an agent sends email"))),
            sw(p.notify_agent_send, t("Notify me when an agent sends email"), () => savePrefs({ notify_agent_send: !p.notify_agent_send }))))),
      p && h("section", { class: "section" },
        h("h2", {}, t("Reading")),
        h("div", { class: "plain" },
          h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, t("Group by conversation")),
            h("span", { class: "detail" }, t("Replies stay together in the list, and the conversation shows what you sent."))),
            sw(p.threads, t("Group by conversation"), async () => { await savePrefs({ threads: !p.threads }); state.listKey = null; clearThread(); })),
          h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, t("Always show remote images")),
            h("span", { class: "detail" }, p.images ? t("On for every sender.")
              : p.image_senders.length ? t("For now only from: {senders}.", { senders: p.image_senders.join(", ") })
              : t("A remote image tells the sender when and where you opened the email."))),
            sw(p.images, t("Always show remote images"), () => savePrefs({ images: !p.images }))),
          p.image_senders.length > 0 && h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, t("Forget the allowed senders"))),
            h("button", { type: "button", class: "btn small ghost", onClick: () => savePrefs({ image_senders: [] }) }, t("Forget"))))),
      p && h("section", { class: "section" },
        h("h2", {}, t("Language")),
        h("div", { class: "plain" },
          h("div", { class: "field" }, h("label", { for: "lang" }, t("Interface")),
            h("select", { id: "lang", onChange: async (e) => {
              const choice = e.target.value;
              await setLanguage(choice);
              state.prefs = await api("/prefs", { method: "PUT", body: { lang: choice, ui_lang: lang } });
              render();
            } },
              h("option", { value: "", selected: !p.lang ? true : null }, t("Automatic ({language})", { language: LANGS[pickLang("")] })),
              Object.entries(LANGS).map(([code, name]) => h("option", { value: code, lang: code, selected: p.lang === code ? true : null }, name)))))),
      p && can("send") && Object.keys(p.signatures).length > 0 && h("section", { class: "section" },
        h("h2", {}, t("Signatures")),
        h("div", { class: "plain" }, Object.keys(p.signatures).map((name) => h("div", { class: "item sig" },
          h("label", { for: `sig-${name}`, class: "mono" }, boxByName(name)?.address || name),
          h("textarea", { id: `sig-${name}`, class: "sig-text", rows: 3, maxlength: 2000, placeholder: t("No signature"),
            onChange: async (e) => { await savePrefs({ signatures: { [name]: e.target.value } }); toast(t("Signature saved.")); } },
            p.signatures[name])))),
        h("p", { class: "note tight" }, t("Added at the end of every new email, reply and forward from that mailbox."))),
      h("section", { class: "section" },
        h("h2", {}, "Passkeys"),
        h("div", { class: "plain" },
          (state.passkeys || []).map((k) => h("div", { class: "item" },
            h("span", { class: "grow" }, h("span", {}, k.name), h("span", { class: "mono" }, k.last_used_at ? t("used {when}", { when: when(k.last_used_at, { withTime: true }) }) : t("never used"))),
            (state.passkeys || []).length > 1 && h("button", { class: "btn quiet small", onClick: async () => {
              await api(`/passkeys/${encodeURIComponent(k.id)}`, { method: "DELETE" }); await loadSettings(); toast(t("Passkey removed.")); } }, t("Remove")))),
          h("div", { class: "item" }, h("button", { class: "btn quiet small link-btn", onClick: invite }, t("Add another device")))),
        state.newInvite && h("div", { class: "box" },
          h("span", {}, t("Open this link on the other device. It works once, for 30 minutes.")),
          h("span", { class: "link" }, state.newInvite),
          h("div", { class: "btn-row" },
            h("button", { class: "btn ghost small", onClick: () => navigator.clipboard?.writeText(state.newInvite).then(() => toast(t("Link copied."))) }, t("Copy")),
            navigator.share && h("button", { class: "btn ghost small", onClick: () => navigator.share({ url: state.newInvite }).catch(() => {}) }, t("Share"))))),
      !state.me.manage && h("section", { class: "section" },
        h("h2", {}, t("Agents with access")),
        h("div", { class: "plain" }, (state.agents?.agents || []).map((a) => h("div", { class: "item" },
          h("span", { class: "grow" },
            h("span", { class: "medium" }, a.name),
            h("span", { class: "detail" }, `${[["read", "mark", "send", "delete"].filter((s) => a.scopes.includes(s)).map(scopeWord).join(", "),
              !a.scopes.includes("delete") && t("Doesn't delete")].filter(Boolean).join(". ")}.`)),
          h("span", { class: "mono" }, a.mailboxes === "*" ? t("all mailboxes") : tn(a.mailboxes.length, "{n} mailbox", "{n} mailboxes"))))),
        h("p", { class: "note tight" }, t("Agent permissions live in the server's config."))),
      h("section", { class: "section" },
        h("div", { class: "plain" },
          h("div", { class: "item" }, h("button", { class: "btn quiet small bare", onClick: async () => { await api("/auth/logout", { method: "POST" }); state.authed = false; render(); } }, t("Sign out of this device")),
            h("span", { class: "grow" }), h("span", { class: "mono" }, `mailgrant ${state.me.version}`)))),
    ),
  );
}

// ── managing mailboxes and agents (web.manage) ─────────────────────────────

// Changes ask for the passkey again: the server answers 403 "confirm" until
// a fresh check, and the call is retried once after it.
async function confirmPasskey() {
  const { challenge_id, options } = await api("/auth/confirm/options", { method: "POST" });
  const cred = await navigator.credentials.get({
    publicKey: {
      ...options,
      challenge: b64urlToBytes(options.challenge),
      allowCredentials: (options.allowCredentials || []).map((c) => ({ ...c, id: b64urlToBytes(c.id) })),
    },
  });
  await api("/auth/confirm/verify", { method: "POST", body: { challenge_id, credential: assertionJSON(cred) } });
}

async function sensitive(path, opts) {
  try {
    return await api(path, opts);
  } catch (e) {
    if (e.status !== 403 || e.message !== "confirm") throw e;
    try {
      await confirmPasskey();
    } catch (err) {
      throw new Error(err.name === "NotAllowedError" ? t("Confirmation cancelled.") : err.message);
    }
    return api(path, opts);
  }
}

async function loadAdmin() {
  const [boxes, agents] = await Promise.all([api("/admin/mailboxes"), api("/admin/agents")]);
  state.admin = { ...boxes, ...agents };
}

const SCOPES = ["read", "mark", "delete", "send"];
const scopeInfo = () => [
  ["read", t("scope|Read"), t("List, search and open messages.")],
  ["mark", t("scope|Mark"), t("Mark as read or unread.")],
  ["delete", t("scope|Delete"), t("Move to the trash. Never erases for good.")],
  ["send", t("scope|Send"), t("Write and reply from the allowed mailboxes.")],
];

const slug = (email) => {
  const [local, domain = ""] = (email || "").toLowerCase().split("@");
  return [local, domain.split(".")[0]].filter(Boolean).join("-").replace(/[^a-z0-9_-]/g, "-").replace(/-+/g, "-");
};

function mailboxForm(name) {
  const a = state.admin;
  const m = name === "new" ? null : a.mailboxes.find((x) => x.name === name);
  if (name !== "new" && !m) throw new Error(t("Mailbox not found."));
  const s = a.suggested || { imap: { host: "", port: 993, tls: "ssl" }, smtp: { host: "", port: 465, tls: "ssl" } };
  const from = m?.smtp?.from_address || "";
  const display = (/^(.*?)\s*<[^>]+>$/.exec(from) || [])[1]?.replace(/^"|"$/g, "") || "";
  return {
    kind: "mailbox", key: `mailbox:${name}`, isNew: !m, existing: m,
    name: m?.name || "", nameTouched: false, description: m?.description || "",
    email: m?.address || "", password: "", display,
    imapOn: m ? !!m.imap : true, smtpOn: m ? !!m.smtp : true,
    imap: { host: m?.imap?.host ?? s.imap.host, port: m?.imap?.port ?? s.imap.port, tls: m?.imap?.tls ?? s.imap.tls },
    smtp: { host: m?.smtp?.host ?? s.smtp.host, port: m?.smtp?.port ?? s.smtp.port, tls: m?.smtp?.tls ?? s.smtp.tls },
    sameLogin: !m || !m.smtp || !m.imap || m.smtp.username === m.imap.username,
    smtpUser: m?.smtp?.username || "", smtpPassword: "",
    saveCopy: m ? m.smtp?.save_copy_to || "" : "Sent",
    test: null,
  };
}

function mailboxPayload(f) {
  const old = f.existing || {};
  const strip = (p) => { if (!p) return {}; const { has_password, ...rest } = p; return rest; };
  const imap = f.imapOn ? { ...strip(old.imap), host: f.imap.host.trim(), port: Number(f.imap.port), tls: f.imap.tls,
    username: f.email.trim(), password: f.password } : null;
  const smtp = f.smtpOn ? { ...strip(old.smtp), host: f.smtp.host.trim(), port: Number(f.smtp.port), tls: f.smtp.tls,
    username: f.sameLogin ? f.email.trim() : f.smtpUser.trim(), password: f.sameLogin ? f.password : f.smtpPassword,
    from_address: f.display.trim() ? `${f.display.trim()} <${f.email.trim()}>` : f.email.trim(),
    save_copy_to: f.imapOn && f.saveCopy.trim() ? f.saveCopy.trim() : null } : null;
  return { name: f.name.trim(), description: f.description.trim(), imap, smtp };
}

function agentForm(name) {
  const a = name === "new" ? null : state.admin.agents.find((x) => x.name === name);
  if (name !== "new" && !a) throw new Error(t("Agent not found."));
  return {
    kind: "agent", key: `agent:${name}`, isNew: !a, existing: a,
    name: a?.name || "", description: a?.description || "",
    all: a ? a.mailboxes === "*" : false,
    boxes: new Set(a && a.mailboxes !== "*" ? a.mailboxes : []),
    scopes: new Set(a ? a.scopes : ["read"]),
  };
}

async function openForm(kind, name) {
  if (state.form?.key === `${kind}:${name}`) return render();
  state.form = null;
  // A token just shown after creating the agent stays on its page.
  if (state.reveal?.agent !== name) state.reveal = null;
  render();
  await loadAdmin();
  state.form = kind === "mailbox" ? mailboxForm(name) : agentForm(name);
  render();
}

async function runForm(fn) {
  state.busy = true;
  render();
  try {
    await fn();
  } catch (e) {
    toast(e.message);
  } finally {
    state.busy = false;
    render();
  }
}

function saveMailbox() {
  const f = state.form;
  return runForm(async () => {
    const body = mailboxPayload(f);
    const m = f.isNew
      ? await sensitive("/admin/mailboxes", { method: "POST", body })
      : await sensitive(`/admin/mailboxes/${enc(f.existing.name)}`, { method: "PUT", body });
    toast(f.isNew ? t("Mailbox added.") : t("Mailbox saved."));
    state.form = null;
    state.me = await api("/me");
    refreshCounts();
    go(f.isNew ? `/settings/mailbox/${enc(m.name)}` : "/settings");
  });
}

function testMailbox() {
  const f = state.form;
  return runForm(async () => {
    const body = mailboxPayload(f);
    f.test = await api("/admin/mailboxes/test", { method: "POST", body: { ...body, name: f.existing?.name } });
  });
}

function deleteMailbox() {
  const f = state.form;
  if (!f.confirmDelete) { f.confirmDelete = true; return render(); }
  return runForm(async () => {
    await sensitive(`/admin/mailboxes/${enc(f.existing.name)}`, { method: "DELETE" });
    toast(t("Mailbox removed from mailgrant. The email stays on the server."));
    state.form = null;
    state.me = await api("/me");
    go("/settings");
  });
}

function agentPayload(f) {
  return { name: f.name.trim(), description: f.description.trim(),
    mailboxes: f.all ? ["*"] : [...f.boxes], scopes: SCOPES.filter((s) => f.scopes.has(s)) };
}

function saveAgent() {
  const f = state.form;
  if (!f.all && !f.boxes.size) return toast(t("Choose at least one mailbox."));
  if (!f.scopes.size) return toast(t("Choose at least one permission."));
  return runForm(async () => {
    const body = agentPayload(f);
    if (f.isNew) {
      const r = await sensitive("/admin/agents", { method: "POST", body });
      state.reveal = { ...r, agent: r.agent.name, created: true };
      state.form = null;
      state.agents = null;
      go(`/settings/agent/${enc(r.agent.name)}`);
    } else {
      await sensitive(`/admin/agents/${enc(f.existing.name)}`, { method: "PUT", body });
      toast(t("Permissions saved. They apply from now on."));
      state.form = null;
      state.agents = null;
      go("/settings");
    }
  });
}

function rotateToken() {
  const f = state.form;
  if (!f.confirmRotate) { f.confirmRotate = true; return render(); }
  return runForm(async () => {
    const r = await sensitive(`/admin/agents/${enc(f.existing.name)}/token`, { method: "POST" });
    state.reveal = { ...r, agent: f.existing.name, created: false };
    f.confirmRotate = false;
    await loadAdmin();
  });
}

function deleteAgent() {
  const f = state.form;
  if (!f.confirmDelete) { f.confirmDelete = true; return render(); }
  return runForm(async () => {
    await sensitive(`/admin/agents/${enc(f.existing.name)}`, { method: "DELETE" });
    toast(t("{agent} no longer has access to anything.", { agent: f.existing.name }));
    state.form = null;
    state.agents = null;
    go("/settings");
  });
}

async function exportConfig() {
  try {
    await sensitive("/admin/export", { method: "GET", raw: true });
  } catch (e) {
    return toast(e.message);
  }
}

function snippet(r) {
  return JSON.stringify({ mcpServers: { mailgrant: { url: r.mcp_url, headers: { Authorization: `Bearer ${r.token}` } } } }, null, 2);
}

const copy = (text, done) => navigator.clipboard?.writeText(text).then(() => toast(done)).catch(() => toast(t("Couldn't copy.")));

function revealBox(r) {
  return h("div", { class: "box reveal" },
    h("strong", { class: "medium" }, r.created ? t("Token for {agent}", { agent: r.agent }) : t("New token for {agent}", { agent: r.agent })),
    h("span", {}, r.created ? t("Save it now: it won't be shown again.") :
      t("The previous token stopped working. Change it in the agent now; this one won't be shown again.")),
    h("code", { class: "link" }, r.token),
    h("div", { class: "btn-row" },
      h("button", { class: "btn small", onClick: () => copy(r.token, t("Token copied.")) }, t("Copy token")),
      h("button", { class: "btn ghost small", onClick: () => copy(snippet(r), t("Configuration copied.")) }, t("Copy MCP configuration"))),
    h("pre", { class: "mcp-snippet" }, snippet(r)));
}

function formField(id, label, value, onInput, extra = {}) {
  return h("div", { class: "field" }, h("label", { for: id }, label),
    h("input", { id, value: value ?? "", onInput, autocapitalize: "off", spellcheck: "false", ...extra }));
}

function tlsSelect(id, value, onChange) {
  return h("select", { id, onChange }, [["ssl", "SSL/TLS"], ["starttls", "STARTTLS"], ["none", t("None (TLS)")]].map(([v, l]) =>
    h("option", { value: v, selected: v === value ? true : null }, l)));
}

function serverRows(prefix, part, f) {
  return [
    formField(`${prefix}-host`, t("Server"), part.host, (e) => { part.host = e.target.value; }),
    h("div", { class: "field" }, h("label", { for: `${prefix}-port` }, t("Port")),
      h("input", { id: `${prefix}-port`, value: part.port, inputmode: "numeric", class: "short", onInput: (e) => { part.port = e.target.value; } }),
      tlsSelect(`${prefix}-tls`, part.tls, (e) => { part.tls = e.target.value; })),
  ];
}

function toggleRow(label, on, onClick, detail) {
  return h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, label), detail && h("span", { class: "detail" }, detail)),
    h("button", { type: "button", class: "switch", role: "switch", "aria-checked": on ? "true" : "false", "aria-label": label, onClick }));
}

function formPane(title, body, actions) {
  return h("section", { class: "pane pane-detail", "aria-label": title },
    h("div", { class: "compose-bar" },
      h("a", { class: "btn quiet small", href: "#/settings" }, t("Back")),
      h("strong", { class: "bar-title" }, title),
      actions || h("span", { class: "bar-spacer" })),
    h("div", { class: "scroll padded", "data-key": `form:${state.form?.key || state.reveal?.agent}` }, body));
}

function mailboxPane() {
  const f = state.form;
  if (!f) return formPane(t("Mailbox"), h("div", { class: "empty" }, t("Opening…")));
  const set = (k) => (e) => { f[k] = e.target.value; if (k === "email" && f.isNew && !f.nameTouched) { f.name = slug(f.email); const n = document.getElementById("mb-name"); if (n) n.value = f.name; } };
  const th = f.test;
  return formPane(f.isNew ? t("New mailbox") : f.email, [
    h("div", { class: "plain" },
      formField("mb-email", t("Email"), f.email, set("email"), { type: "email", inputmode: "email", disabled: !f.isNew ? true : null }),
      formField("mb-password", t("Password"), f.password, set("password"), { type: "password", autocomplete: "new-password",
        placeholder: f.isNew ? t("Password or app password") : t("Kept (leave empty)") }),
      f.smtpOn && formField("mb-display", t("Name"), f.display, set("display"), { placeholder: t("How recipients see it"), autocapitalize: null, spellcheck: null }),
      f.isNew && formField("mb-name", t("Nickname"), f.name, (e) => { f.name = e.target.value; f.nameTouched = true; }, { placeholder: "contato-empresa" })),
    f.isNew && h("p", { class: "note" }, t("The nickname is how agents refer to the mailbox. It can't change later.")),
    h("section", { class: "section" },
      h("h2", {}, t("Receive (IMAP)")),
      h("div", { class: "plain" },
        toggleRow(t("Read and organize email"), f.imapOn, () => { f.imapOn = !f.imapOn; render(); }),
        f.imapOn && serverRows("imap", f.imap, f))),
    h("section", { class: "section" },
      h("h2", {}, t("Send (SMTP)")),
      h("div", { class: "plain" },
        toggleRow(t("Send email"), f.smtpOn, () => { f.smtpOn = !f.smtpOn; render(); }),
        f.smtpOn && serverRows("smtp", f.smtp, f),
        f.smtpOn && toggleRow(t("Same username and password as IMAP"), f.sameLogin, () => { f.sameLogin = !f.sameLogin; render(); }),
        f.smtpOn && !f.sameLogin && formField("smtp-user", t("Username"), f.smtpUser, set("smtpUser")),
        f.smtpOn && !f.sameLogin && formField("smtp-password", t("Password"), f.smtpPassword, set("smtpPassword"),
          { type: "password", autocomplete: "new-password", placeholder: f.isNew ? "" : t("Kept (leave empty)") }),
        f.smtpOn && f.imapOn && formField("smtp-copy", t("Copy in"), f.saveCopy, set("saveCopy"), { placeholder: "Sent" }))),
    h("section", { class: "section" },
      h("div", { class: "btn-row padded-x" },
        h("button", { class: "btn ghost small", disabled: state.busy, onClick: testMailbox }, state.busy && !th ? t("Testing…") : t("Test connection")),
        th && ["imap", "smtp"].filter((p) => th[p]).map((p) => h("span", { class: `test ${th[p].ok ? "ok" : "bad"}` },
          `${p.toUpperCase()}: ${th[p].ok ? (p === "imap" ? tn(th[p].folders.length, "ok, {n} folder", "ok, {n} folders") : "ok") : th[p].error}`)))),
    !f.isNew && h("section", { class: "section" },
      h("h2", {}, t("Who uses it")),
      h("p", { class: "note tight" }, f.existing.agents.length ? t("Agents: {agents}.", { agents: f.existing.agents.join(", ") }) : t("No agent has access to this mailbox.")),
      h("div", { class: "plain" }, h("div", { class: "item" },
        h("button", { class: `btn quiet small bare${f.confirmDelete ? " danger" : ""}`, disabled: state.busy, onClick: deleteMailbox },
          f.confirmDelete ? t("Remove from mailgrant? Tap again") : t("Remove mailbox from mailgrant"))))),
  ], h("button", { class: "btn small", disabled: state.busy, onClick: saveMailbox }, f.isNew ? t("Add") : t("Save")));
}

function agentPane() {
  const f = state.form;
  const r = state.reveal;
  if (!f) return formPane(t("Agent"), r ? revealBox(r) : h("div", { class: "empty" }, t("Opening…")));
  const boxes = state.me.mailboxes;
  return formPane(f.isNew ? t("New agent") : f.existing.name, [
    r && h("section", { class: "section first" }, revealBox(r)),
    h("div", { class: "plain" },
      f.isNew && formField("ag-name", t("Name"), f.name, (e) => { f.name = e.target.value; }, { placeholder: "hermes" }),
      formField("ag-desc", t("Description"), f.description, (e) => { f.description = e.target.value; },
        { placeholder: t("What it is for"), autocapitalize: null, spellcheck: null })),
    h("section", { class: "section" },
      h("h2", {}, t("Can")),
      h("div", { class: "plain" }, scopeInfo().map(([s, label, detail]) =>
        toggleRow(label, f.scopes.has(s), () => { f.scopes.has(s) ? f.scopes.delete(s) : f.scopes.add(s); render(); }, detail)))),
    h("section", { class: "section" },
      h("h2", {}, t("In the mailboxes")),
      h("div", { class: "plain" },
        toggleRow(t("All mailboxes"), f.all, () => { f.all = !f.all; render(); }, t("Includes the ones you add later.")),
        !f.all && boxes.map((m) => toggleRow(m.address, f.boxes.has(m.name), () => {
          f.boxes.has(m.name) ? f.boxes.delete(m.name) : f.boxes.add(m.name); render(); })))),
    !f.isNew && h("section", { class: "section" },
      h("h2", {}, t("Token")),
      h("p", { class: "note tight" }, f.existing.token_created_at ? t("Created {date}.", { date: new Date(f.existing.token_created_at).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" }) }) : t("Came from the config.")),
      h("div", { class: "plain" },
        h("div", { class: "item" }, h("button", { class: `btn quiet small bare${f.confirmRotate ? " danger" : ""}`, disabled: state.busy, onClick: rotateToken },
          f.confirmRotate ? t("The current token will stop working. Tap again") : t("Create a new token"))),
        h("div", { class: "item" }, h("button", { class: `btn quiet small bare${f.confirmDelete ? " danger" : ""}`, disabled: state.busy, onClick: deleteAgent },
          f.confirmDelete ? t("Take away all of {agent}'s access? Tap again", { agent: f.existing.name }) : t("Remove agent"))))),
  ], h("button", { class: "btn small", disabled: state.busy, onClick: saveAgent }, f.isNew ? t("Create") : t("Save")));
}

function manageSections() {
  const a = state.admin;
  if (!a) return h("section", { class: "section" }, h("div", { class: "empty" }, t("Loading…")));
  const scopeText = (s) => scopeInfo().filter(([k]) => s.includes(k)).map(([, l]) => l.toLocaleLowerCase(lang)).join(", ");
  return [
    h("section", { class: "section first" },
      h("h2", {}, t("Email mailboxes")),
      h("div", { class: "plain" },
        a.mailboxes.map((m) => h("a", { class: "item link-item", href: `#/settings/mailbox/${enc(m.name)}` },
          h("span", { class: "grow" }, h("span", {}, m.address),
            h("span", { class: "mono" }, [m.imap && t("receives"), m.smtp && t("sends")].filter(Boolean).join(" · "))),
          h("span", { class: "mono" }, m.name))),
        h("div", { class: "item" }, h("a", { class: "btn quiet small link-btn", href: "#/settings/mailbox/new" }, t("Add mailbox"))))),
    h("section", { class: "section" },
      h("h2", {}, t("Agents")),
      h("div", { class: "plain" },
        a.agents.map((x) => h("a", { class: "item link-item", href: `#/settings/agent/${enc(x.name)}` },
          h("span", { class: "grow" }, h("span", { class: "medium" }, x.name),
            h("span", { class: "detail" }, `${scopeText(x.scopes)}${x.description ? ` · ${x.description}` : ""}`)),
          h("span", { class: "mono" }, x.mailboxes === "*" ? t("all") : tn(x.mailboxes.length, "{n} mailbox", "{n} mailboxes")))),
        h("div", { class: "item" }, h("a", { class: "btn quiet small link-btn", href: "#/settings/agent/new" }, t("Add agent")))),
      h("p", { class: "note tight" }, t("Changes apply at once, without a restart. Saving asks for Face ID again."))),
    h("section", { class: "section" },
      h("div", { class: "plain" }, h("div", { class: "item" },
        h("span", { class: "grow" }, h("span", {}, t("Download config")), h("span", { class: "detail" }, t("A backup with the passwords. Keep it somewhere safe."))),
        h("button", { class: "btn ghost small", onClick: exportConfig }, t("Download"))))),
  ];
}

function tabs(r) {
  const tab = (href, name, label, active) => h("a", { class: "tab", href, "aria-current": active ? "page" : null }, icon(name), label);
  return h("nav", { class: "tabs", "aria-label": t("Sections") },
    tab("#/inbox", "inbox", t("Inbox"), LIST_VIEWS.includes(r.name) || r.name === "m"),
    tab("#/agents", "agents", t("Agents"), r.name === "agents"),
    tab("#/settings", "settings", t("Settings"), r.name === "settings"));
}

function render() {
  const root = document.getElementById("app");
  const focused = document.activeElement?.id;
  const sel = focused && document.activeElement.selectionStart;
  const scrolls = new Map([...document.querySelectorAll(".scroll[data-key]")].map((el) => [el.dataset.key, el.scrollTop]));
  root.replaceChildren();
  if (!state.authed) {
    document.body.dataset.view = "auth";
    root.append(authView());
    return;
  }
  if (!state.me) return;
  const r = route();
  let detail;
  if (r.name === "m") detail = messagePane();
  else if (COMPOSE_VIEWS.includes(r.name)) detail = composePane();
  else if (r.name === "agents") detail = agentsPane();
  else if (r.name === "settings" && r.args[0] === "mailbox") detail = mailboxPane();
  else if (r.name === "settings" && r.args[0] === "agent") detail = agentPane();
  else if (r.name === "settings") detail = settingsPane();
  else detail = state.view === "drafts" ? h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, t("Choose a draft to continue."))) : messagePane();
  document.body.dataset.view = ["agents", "settings"].includes(r.name) ? "page" :
    r.name === "m" || COMPOSE_VIEWS.includes(r.name) ? "detail" : "list";
  document.body.dataset.selecting = state.selecting ? "1" : "";
  root.append(h("div", { class: "shell" }, sidebar(r), listPane(), detail), tabs(r));
  if (state.drawer && !WIDE.matches) {
    root.append(h("div", { class: "scrim", onClick: () => { state.drawer = false; render(); } }), sidebar(r, true));
  }
  // Re-rendering replaces the nodes; keep the scroll positions and the caret.
  document.querySelectorAll(".scroll[data-key]").forEach((el) => { if (scrolls.get(el.dataset.key)) el.scrollTop = scrolls.get(el.dataset.key); });
  if (focused) {
    const el = document.getElementById(focused);
    if (el) { el.focus({ preventScroll: true }); if (sel !== undefined && sel !== null && el.setSelectionRange) try { el.setSelectionRange(sel, sel); } catch (_) {} }
  }
}

// ── boot ──────────────────────────────────────────────────────────────────

async function boot() {
  await setLanguage(storedLang());
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).catch(() => {});
  window.addEventListener("hashchange", onRoute);
  WIDE.addEventListener("change", render);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.drawer) { state.drawer = false; render(); } });
  // The row that saw a long press start is gone after the redraw: watch the release here.
  const released = () => { if (gesture.pressed) gesture = { pressed: false, at: Date.now() }; };
  document.addEventListener("pointerup", released, true);
  document.addEventListener("pointercancel", released, true);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      // iOS may close a backgrounded app without warning: keep what was typed.
      if (state.draft?.dirty) saveDraft(state.draft);
      return;
    }
    if (state.authed) { refreshCounts(); if (LIST_VIEWS.includes(route().name) && state.view !== "drafts") loadList(true); }
  });
  try {
    const s = await api("/auth/state");
    state.authed = s.authenticated;
    state.hasPasskeys = s.has_passkeys;
    state.setupCode = s.setup_code;
    if (state.authed) await loadMe();
  } catch (e) {
    toast(e.message);
  }
  onRoute();
}

boot();
