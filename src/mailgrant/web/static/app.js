// mailgrant web app. No framework, no build step: the server ships these
// files as they are. Everything that comes from mail is inserted as text
// (textContent), never as HTML. The one exception is an HTML body, which the
// server sanitizes and serves as its own document for a sandboxed iframe.

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
    throw new Error("Sessão encerrada. Entre de novo.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const err = new Error(data.detail || `Erro ${res.status}`);
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
  const hm = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (days === 0) return hm;
  if (days === 1) return withTime ? `ontem ${hm}` : "ontem";
  if (days < 7) return d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function dayLabel(iso) {
  const d = new Date(iso);
  const days = Math.floor((new Date(new Date().toDateString()) - new Date(d.toDateString())) / 86400000);
  if (days === 0) return "Hoje";
  if (days === 1) return "Ontem";
  return d.toLocaleDateString("pt-BR", { day: "numeric", month: "long" });
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
const SCOPE_WORDS = { read: "lê", mark: "marca", delete: "apaga", send: "envia" };

// ── routing ───────────────────────────────────────────────────────────────

const LIST_VIEWS = ["inbox", "starred", "sent", "drafts"];
const VIEW_TITLES = { inbox: "Entrada", starred: "Com estrela", sent: "Enviados", drafts: "Rascunhos" };
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
  const t = await api(`/thread/${enc(box)}/${enc(uid)}${folder ? `?folder=${enc(folder)}` : ""}`);
  if (state.threadKey !== key) return;
  state.thread = t;
  const last = t.messages.length - 1;
  state.expanded = new Set(t.messages.filter((m, i) => i === last || m.unread || m.opened).map(msgKey));
  render();
  const unread = t.messages.filter((m) => m.unread && !m.sent).map((m) => m.uid);
  if (markSeen && t.can.mark && unread.length) {
    await batch("seen", unread.map((u) => ({ mailbox: t.mailbox, uid: u })), { folder: t.folder });
    t.messages.forEach((m) => { if (!m.sent) m.unread = false; });
    rowsOf(t).forEach((r) => (r.unread = false));
    refreshCounts();
  }
}

// The message a reply or forward starts from, loading its conversation if needed.
async function threadMessage(box, uid, folder) {
  const find = () => state.thread?.mailbox === box &&
    state.thread.messages.find((m) => String(m.uid) === String(uid) && (!folder || m.folder === folder));
  if (!find()) await openThread(box, uid, folder, false);
  const m = find();
  if (!m) throw new Error("Mensagem não encontrada.");
  return m;
}

// List rows that hold any message of this conversation.
const rowsOf = (t) => state.list.filter((r) => r.mailbox === t.mailbox && r.members.some((u) => t.members.includes(u)));

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

const plural = (n, one, many) => (n === 1 ? one : many.replace("#", n));

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
    if (action === "archive") toast(plural(rows.length, "Arquivada.", "# arquivadas."));
    if (action === "trash") toast(plural(rows.length, "Movida para a lixeira.", "# na lixeira."));
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
    toast(e.name === "NotAllowedError" ? "Entrada cancelada." : e.message);
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
    toast("Passkey criada.");
    await afterSignIn();
  } catch (e) {
    toast(e.name === "NotAllowedError" ? "Cadastro cancelado."
      : e.status === 403 ? (code === state.invite ? "Convite inválido, já usado ou vencido." : "Código de configuração errado.")
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
  return "Este aparelho";
}

// ── push ──────────────────────────────────────────────────────────────────

async function enablePush() {
  try {
    if (isIOS() && !standalone()) throw new Error("Adicione à Tela de Início e abra pelo ícone.");
    const perm = await Notification.requestPermission();
    if (perm !== "granted") throw new Error("As notificações foram bloqueadas nos ajustes do aparelho.");
    const reg = await navigator.serviceWorker.ready;
    const { key } = await api("/push/key");
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64urlToBytes(key) });
    await api("/push/subscribe", { method: "POST", body: sub.toJSON() });
    state.push.subscribed = true;
    toast("Notificações ativadas neste aparelho.");
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

const longDate = (m) => new Date(m.ts * 1000).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

function quoted(m) {
  const lines = (m.body || "").replace(/\s+$/, "").split("\n").map((l) => (l ? `> ${l}` : ">")).join("\n");
  return `\n\nEm ${longDate(m)}, ${m.from_raw || m.from} escreveu:\n${lines}`;
}

function forwarded(m) {
  return "\n\n---------- Mensagem encaminhada ----------\n" +
    `De: ${m.from_raw || m.from}\nData: ${longDate(m)}\nAssunto: ${m.subject}\nPara: ${m.to || ""}` +
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
  const t = state.thread;
  const d = blankDraft(key, mode, t.mailbox);
  d.sig = signature(t.mailbox);
  const subject = m.subject || "";
  if (mode === "forward") {
    d.subject = /^(fwd?|enc):/i.test(subject) ? subject : `Fwd: ${subject}`;
    d.body = d.sig + forwarded(m);
    d.attachments = m.attachments.map((a) => ({ kind: "ref", ref: { mailbox: t.mailbox, folder: m.folder, uid: m.uid, index: a.index },
      filename: a.filename || "anexo", size: a.size }));
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
    d.subject = /^re:/i.test(subject) ? subject : `Re: ${subject}`;
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
      filename: a.filename || "anexo", size: a.size })),
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
  setDraftStatus(d, "Salvando…");
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
      setDraftStatus(d, `Rascunho salvo ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`);
      state.drafts = null;
    } catch (e) {
      d.dirty = true;
      if (e.status === 409) {
        d.noDrafts = true;
        setDraftStatus(d, "Esta caixa não tem pasta de rascunhos");
      } else setDraftStatus(d, "Rascunho não salvo");
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
    if (d.saved) toast("Rascunho salvo.");
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
  toast("Rascunho descartado.");
  d.mode === "draft" ? go("/drafts") : closeCompose();
}

async function addFiles(files) {
  const d = state.draft;
  const used = () => d.attachments.reduce((n, a) => n + (a.size || 0), 0);
  for (const f of files) {
    if (used() + f.size > MAX_ATTACH) {
      toast("Os anexos passam de 25 MB.");
      break;
    }
    const data = await new Promise((ok, fail) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result).split(",")[1] || "");
      r.onerror = () => fail(new Error(`Não deu para ler ${f.name}.`));
      r.readAsDataURL(f);
    });
    d.attachments.push({ kind: "upload", filename: f.name, content_type: f.type || "application/octet-stream", size: f.size, data });
  }
  touchDraft();
  render();
}

async function sendDraft() {
  const d = state.draft;
  if (!splitAddrs(d.to).length) return toast("Falta o destinatário.");
  clearTimeout(saveTimer);
  state.busy = true;
  render();
  try {
    if (d.saving) await d.saving;
    await api("/send", { method: "POST", body: { ...draftPayload(d), draft: d.saved } });
    toast("Enviado.");
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
        h("p", {}, "Primeiro acesso. Digite o código de configuração e crie a passkey deste aparelho."),
      ),
      h("form", { class: "actions", onSubmit: (e) => { e.preventDefault(); submit(); } },
        (codeInput = h("input", { "aria-label": "Código de configuração", placeholder: "Código de configuração",
          autocomplete: "one-time-code", autocapitalize: "off", spellcheck: "false", required: true })),
        (nameInput = h("input", { "aria-label": "Nome deste aparelho", value: guessDevice(), maxlength: 60 })),
        h("button", { class: "btn", type: "submit", disabled: state.busy }, icon("face"), "Criar passkey"),
        h("p", { class: "foot" }, "O código é o MAILGRANT_SETUP_CODE do servidor. Ele para de valer quando a primeira passkey é criada."),
      ),
    );
  }
  return h("main", { class: "auth" },
    h("div", {},
      h("div", { class: "brand" }, "mailgrant", h("i", {}, ".")),
      h("p", {}, inviting ? "Crie a passkey deste aparelho. Ela usa o Face ID, a digital ou a senha do aparelho." : "Suas caixas num lugar só, e o que os agentes fizeram nelas."),
    ),
    h("div", { class: "actions" },
      inviting && (nameInput = h("input", { "aria-label": "Nome deste aparelho", value: guessDevice(), maxlength: 60 })),
      h("button", { class: "btn", disabled: state.busy, onClick: () => (inviting ? register(nameInput.value.trim() || guessDevice()) : signIn()) },
        icon("face"), inviting ? "Criar passkey" : "Entrar com passkey"),
      h("p", { class: "foot" }, inviting ? "O convite vale uma vez só." :
        state.hasPasskeys ? "Primeira vez neste aparelho? Gere um convite em Ajustes, num aparelho já conectado." :
        "Nenhuma passkey ainda. No servidor, rode mailgrant invite e abra o link aqui."),
    ),
  );
}

function sidebar(r, drawer = false) {
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const inList = LIST_VIEWS.includes(r.name) || r.name === "m";
  const at = (view, box = "all") => inList && state.view === view && (view !== "inbox" || state.box === box) ? "page" : null;
  return h("aside", { class: drawer ? "side drawer" : "side", "aria-label": "Menu" },
    h("div", { class: "wordmark" }, h("span", {}, "mailgrant", h("i", {}, ".")),
      drawer && h("button", { type: "button", class: "icon-btn plain drawer-close", "aria-label": "Fechar menu", onClick: () => { state.drawer = false; render(); } }, icon("close"))),
    can("send") && h("a", { href: "#/compose", class: "btn small side-compose" }, "Escrever"),
    h("nav", { "aria-label": "Pastas" },
      h("a", { href: "#/inbox", "aria-current": at("inbox") },
        h("span", {}, "Todas as caixas"), state.total ? h("span", { class: "count" }, state.total) : null),
      h("a", { href: "#/starred", "aria-current": at("starred") }, h("span", {}, "Com estrela")),
      h("a", { href: "#/sent", "aria-current": at("sent") }, h("span", {}, "Enviados")),
      can("send") && h("a", { href: "#/drafts", "aria-current": at("drafts") }, h("span", {}, "Rascunhos"))),
    h("nav", { "aria-label": "Caixas" },
      h("span", { class: "side-label" }, "Caixas"),
      boxes.map((m) => h("a", { href: `#/inbox/${enc(m.name)}`, "aria-current": at("inbox", m.name) },
        h("span", {}, m.address), state.counts[m.name] ? h("span", { class: "count" }, state.counts[m.name]) : null)),
    ),
    h("nav", { class: "bottom", "aria-label": "Mais" },
      h("a", { href: "#/agents", "aria-current": r.name === "agents" ? "page" : null }, h("span", {}, "Agentes")),
      h("a", { href: "#/settings", "aria-current": r.name === "settings" ? "page" : null }, h("span", {}, "Ajustes")),
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
      : m.unread && h("span", { class: "dot", "aria-label": "Não lida" }),
    h("div", { class: "top" },
      h("span", { class: "from" }, m.from || m.from_address),
      m.count > 1 && h("span", { class: "thread-n mono" }, m.count),
      h("span", { class: "mono" }, when(m.ts))),
    h("span", { class: "subject" }, m.subject || "(sem assunto)"),
    h("span", { class: "mono" }, m.mark ? `${m.mailbox_address} · ${m.mark}` : m.mailbox_address),
  ];
  const row = state.selecting
    ? h("button", { type: "button", class: cls, "aria-pressed": selected ? "true" : "false", onClick: () => toggleSelect(key) }, kids)
    : h("a", { class: cls, href: `#/m/${enc(m.mailbox)}/${enc(m.uid)}`, "aria-current": state.thread && rowsOf(state.thread).includes(m) ? "true" : null }, kids);
  const star = !state.selecting && (can("mark") || m.flagged) && h("button", {
    type: "button", class: `star${m.flagged ? " on" : ""}`, disabled: !can("mark"),
    "aria-label": m.flagged ? "Tirar a estrela" : "Marcar com estrela", "aria-pressed": m.flagged ? "true" : "false",
    onClick: (e) => { e.preventDefault(); actOnRows(m.flagged ? "unflag" : "flag", [m]); },
  }, icon("star"));
  const wrap = h("div", { class: "row-wrap" },
    h("div", { class: "swipe-bg read", "aria-hidden": "true" }, icon(m.unread ? "mailOpen" : "mail"), m.unread ? "Lida" : "Não lida"),
    h("div", { class: "swipe-bg arch", "aria-hidden": "true" }, "Arquivar", icon("archive")),
    row, star);
  if (!state.selecting && can("mark") && !WIDE.matches) attachGestures(wrap, row, m);
  return wrap;
}

function sentRow(m) {
  const rcpts = m.to || [];
  const to = rcpts.length ? `Para ${rcpts[0]}${rcpts.length > 1 ? ` +${rcpts.length - 1}` : ""}` : "(sem destinatário)";
  const by = m.sent_by ? `${m.sent_by} enviou` : m.by_you ? "você" : null;
  return h("a", { class: "row", href: `#/m/${enc(m.mailbox)}/${enc(m.uid)}/${enc(m.folder)}`,
    "aria-current": state.threadKey === `${m.mailbox}/${m.folder}/${m.uid}` ? "true" : null },
    h("div", { class: "top" }, h("span", { class: "from" }, to), h("span", { class: "mono" }, when(m.ts))),
    h("span", { class: "subject" }, m.subject || "(sem assunto)"),
    h("span", { class: "mono" }, by ? [m.mailbox_address, " · ", h("span", { class: m.sent_by ? "by-agent" : null }, by)] : m.mailbox_address));
}

function menuButton() {
  return h("button", { type: "button", class: "icon-btn plain menu-btn", "aria-label": "Abrir menu",
    onClick: () => { state.drawer = true; render(); } }, icon("menu"));
}

function draftRow(d) {
  return h("a", { class: "row", href: `#/draft/${enc(d.mailbox)}/${enc(d.uid)}`,
    "aria-current": state.draft?.key === `draft:${d.mailbox}/${d.uid}` ? "true" : null },
    h("div", { class: "top" }, h("span", { class: "from" }, d.to ? `Para ${d.to}` : "(sem destinatário)"), h("span", { class: "mono" }, when(d.ts))),
    h("span", { class: "subject" }, d.subject || "(sem assunto)"),
    h("span", { class: "mono" }, d.mailbox_address));
}

function selectionBar() {
  const rows = selectedRows();
  const allRead = rows.length > 0 && rows.every((r) => !r.unread);
  const allStarred = rows.length > 0 && rows.every((r) => r.flagged);
  const tool = (name, label, action) => h("button", { type: "button", class: "tool", disabled: !rows.length,
    onClick: async () => { await actOnRows(action, rows); stopSelecting(); } }, icon(name), h("span", {}, label));
  return h("div", { class: "selbar", role: "toolbar", "aria-label": "Ações nas selecionadas" },
    tool(allRead ? "mail" : "mailOpen", allRead ? "Não lida" : "Lida", allRead ? "unseen" : "seen"),
    tool("star", allStarred ? "Sem estrela" : "Estrela", allStarred ? "unflag" : "flag"),
    tool("archive", "Arquivar", "archive"),
    can("delete") && tool("trash", "Lixeira", "trash"));
}

function listPane() {
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const current = state.view === "inbox" ? boxByName(state.box) : null;
  const drafts = state.view === "drafts";
  let search;
  const doSearch = () => { state.q = search.value.trim(); state.limit = 40; loadList(true); };
  const unreadHere = state.box === "all" ? state.total : state.counts[state.box] || 0;
  const sent = state.view === "sent";
  const title = state.view === "inbox" ? (current ? current.address : WIDE.matches ? "Todas as caixas" : "Entrada") : VIEW_TITLES[state.view];
  const sub = sent ? "Por você e pelos agentes, em todas as caixas" :
    state.view === "starred" ? plural(state.list.length, "1 mensagem", "# mensagens") :
    drafts ? plural((state.drafts || []).length, "1 rascunho", "# rascunhos") :
    `${unreadHere} não lidas · ${boxes.length} caixas`;
  const n = state.selected.size;
  const chip = (label, href, pressed, count) => h("a", { class: "chip", href, "aria-pressed": pressed ? "true" : "false" },
    label, count ? h("span", { class: "n" }, count) : null);
  const head = state.selecting
    ? h("div", { class: "hdr-row sel-row" },
        h("button", { type: "button", class: "btn quiet small bare", onClick: () => stopSelecting() }, "Cancelar"),
        h("strong", { class: "bar-title" }, n ? plural(n, "1 selecionada", "# selecionadas") : "Selecione"),
        h("button", { type: "button", class: "btn quiet small bare", onClick: () => {
          state.selected = n === state.list.length ? new Set() : new Set(state.list.map(rowKey)); render(); } },
          n === state.list.length && n ? "Nenhuma" : "Todas"))
    : h("div", { class: "hdr-row" },
        h("div", { class: "hdr-title" }, menuButton(), h("div", {}, h("h1", { class: "title" }, title), h("div", { class: "sub" }, sub))),
        h("div", { class: "hdr-actions" },
          !drafts && !sent && can("mark") && state.list.length > 0 && h("button", { type: "button", class: "btn quiet small", onClick: () => startSelecting() }, "Selecionar"),
          can("send") && h("a", { href: "#/compose", class: "icon-btn", "aria-label": "Escrever e-mail" }, icon("pencil"))));
  return h("section", { class: "pane pane-list", "aria-label": "Mensagens" },
    h("header", { class: "hdr" },
      head,
      !drafts && !state.selecting && h("label", { class: "search" }, icon("search"),
        search = h("input", { id: "q", type: "search", placeholder: "Buscar", "aria-label": "Buscar nas caixas", value: state.q,
          onKeydown: (e) => e.key === "Enter" && doSearch(), onSearch: doSearch })),
      !state.selecting && h("div", { class: "chips", role: "group", "aria-label": "Filtrar" },
        chip("Todas", "#/inbox", state.view === "inbox" && state.box === "all", state.total),
        chip("Com estrela", "#/starred", state.view === "starred"),
        chip("Enviados", "#/sent", sent),
        can("send") && chip("Rascunhos", "#/drafts", drafts),
        boxes.map((m) => chip(m.address, `#/inbox/${enc(m.name)}`, state.view === "inbox" && state.box === m.name, state.counts[m.name])))),
    h("div", { class: "scroll", "data-key": `list:${state.view}|${state.box}|${state.q}` },
      state.listErrors.map((e) => h("div", { class: "err" }, `${e.mailbox}: ${e.error}`)),
      drafts ? (
        state.drafts === null ? h("div", { class: "empty" }, "Carregando…") :
        !state.drafts.length ? h("div", { class: "empty" }, "Nenhum rascunho. O que você começa a escrever fica salvo aqui.") :
        h("div", { class: "rows" }, state.drafts.map(draftRow))
      ) : (
        state.loadingList && !state.list.length ? h("div", { class: "empty" }, "Carregando…") :
        !state.list.length ? h("div", { class: "empty" }, state.q ? "Nada encontrado." : state.view === "starred" ? "Nenhuma mensagem com estrela." :
          sent ? "Nada enviado ainda. O que você e os agentes enviarem aparece aqui." : "Nenhuma mensagem aqui.") :
        h("div", { class: "rows" }, state.list.map(sent ? sentRow : rowView))
      ),
      !drafts && state.fetched >= state.limit && h("button", { class: "more", onClick: () => { state.limit += 40; loadList(true); } },
        state.loadingList ? "Carregando…" : "Carregar mais antigas"),
    ),
    state.selecting && selectionBar(),
  );
}

// ── a conversation ─────────────────────────────────────────────────────────

function replyHref(kind, t, m) {
  return `#/${kind}/${enc(t.mailbox)}/${enc(m.uid)}/${enc(m.folder)}`;
}

// ── HTML mail ─────────────────────────────────────────────────────────────

// Each render rebuilds the page, and an iframe reloads when it is re-inserted.
// The browser cache answers the reload; remembering the height keeps the
// conversation from jumping while it does.
const frameHeights = new Map();
const senderDomain = (m) => (m.from_address || "").split("@").pop().toLowerCase();

function imagesShown(t, m) {
  const p = state.prefs || {};
  return !m.remote_images || p.images || (p.image_senders || []).includes(senderDomain(m)) || state.showImages.has(`${t.mailbox}/${msgKey(m)}`);
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

function mailFrame(t, m) {
  const images = imagesShown(t, m);
  const key = `${t.mailbox}/${msgKey(m)}${images ? "+img" : ""}`;
  const src = `${API}/messages/${enc(t.mailbox)}/${enc(m.uid)}/html?folder=${enc(m.folder)}${images && m.remote_images ? "&images=1" : ""}`;
  const frame = h("iframe", {
    class: "mail-frame", src, title: `Mensagem de ${m.from || m.from_address}`,
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

function imagesBar(t, m) {
  if (imagesShown(t, m)) return null;
  const domain = senderDomain(m);
  const show = () => { state.showImages.add(`${t.mailbox}/${msgKey(m)}`); render(); };
  const always = async () => {
    const list = [...new Set([...(state.prefs.image_senders || []), domain])];
    state.prefs = await api("/prefs", { method: "PUT", body: { image_senders: list } });
    render();
  };
  return h("div", { class: "images-bar" },
    h("span", { class: "grow" }, "Imagens externas bloqueadas. Elas avisam o remetente quando você abre."),
    h("button", { type: "button", class: "btn quiet small bare", onClick: show }, "Mostrar"),
    domain && h("button", { type: "button", class: "btn quiet small bare", onClick: always }, `Sempre de ${domain}`));
}

function threadMessageView(t, m, isLast) {
  const open = state.expanded.has(msgKey(m));
  const many = t.messages.length > 1;
  const who = m.sent ? "Você" : m.from || m.from_address;
  const toggle = () => { open ? state.expanded.delete(msgKey(m)) : state.expanded.add(msgKey(m)); render(); };
  if (!open) {
    return h("button", { type: "button", class: `tmsg folded${m.unread ? " unread" : ""}`, onClick: toggle },
      h("div", { class: "top" }, h("span", { class: "from" }, who), h("span", { class: "mono" }, when(m.ts))),
      h("span", { class: "snippet" }, (m.body || "").replace(/\s+/g, " ").slice(0, 140) || "(sem texto)"));
  }
  const path = `/messages/${enc(t.mailbox)}/${enc(m.uid)}`;
  const recipients = [m.to && `para ${m.to}`, m.cc && `cc ${m.cc}`].filter(Boolean).join(" · ");
  return h("div", { class: "tmsg" },
    h(many ? "button" : "div", { type: many ? "button" : null, class: "tmsg-head", onClick: many ? toggle : null },
      h("div", { class: "top" }, h("strong", {}, who), h("span", { class: "mono" }, when(m.ts, { withTime: true }))),
      h("span", { class: "mono addr" }, m.sent ? `${m.from_address} · Enviados` : m.from_address),
      recipients && h("span", { class: "mono addr" }, recipients)),
    m.html ? [imagesBar(t, m), mailFrame(t, m)] : h("div", { class: "body" }, linkify(m.body || "(mensagem sem texto)")),
    m.attachments.map((a) => h("a", { class: "attach", href: `${API}${path}/attachments/${a.index}?folder=${enc(m.folder)}`, download: a.filename || "anexo" },
      icon("file"), h("span", {}, a.filename || "anexo"), h("span", { class: "mono" }, size(a.size)))),
    t.can.reply && many && !isLast && h("div", { class: "tmsg-actions" },
      h("a", { class: "btn quiet small bare", href: replyHref("reply", t, m) }, "Responder"),
      h("a", { class: "btn quiet small bare", href: replyHref("replyall", t, m) }, "Responder a todos"),
      h("a", { class: "btn quiet small bare", href: replyHref("forward", t, m) }, "Encaminhar")));
}

function threadActions(t) {
  const inbox = t.messages.filter((m) => m.folder === t.folder);
  const newest = inbox[inbox.length - 1];
  const flagged = inbox.some((m) => m.flagged);
  const items = (uids) => uids.map((uid) => ({ mailbox: t.mailbox, uid }));
  const leave = () => { clearThread(); go(listHref().slice(1)); };
  const run = async (fn) => { try { await fn(); } catch (e) { toast(e.message); } render(); };
  return {
    flagged,
    star: () => run(async () => {
      if (!newest) return;
      await batch(flagged ? "unflag" : "flag", items(flagged ? t.members : [newest.uid]), { folder: t.folder });
      inbox.forEach((m) => (m.flagged = !flagged && m === newest));
      rowsOf(t).forEach((r) => (r.flagged = !flagged));
      if (flagged && state.view === "starred") state.list = state.list.filter((r) => !rowsOf(t).includes(r));
    }),
    unread: () => run(async () => {
      if (!newest) return;
      await batch("unseen", items([newest.uid]), { folder: t.folder });
      rowsOf(t).forEach((r) => (r.unread = true));
      refreshCounts();
      leave();
    }),
    move: (action) => run(async () => {
      const res = await batch(action, items(t.members), { folder: t.folder });
      const gone = rowsOf(t);
      state.list = state.list.filter((r) => !gone.includes(r));
      toast(action === "archive" ? "Conversa arquivada." : `Movida para ${res.moved_to?.[t.mailbox] || "a lixeira"}.`);
      refreshCounts();
      leave();
    }),
  };
}

function messagePane() {
  const t = state.thread;
  if (!t) return h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, state.threadKey ? "Abrindo…" : "Selecione uma mensagem."));
  const msgs = t.messages;
  const last = msgs[msgs.length - 1];
  const opened = msgs.find((m) => m.opened) || last;
  const a = threadActions(t);
  const hasInbox = t.members.length > 0;
  const iconBtn = (name, label, fn, on) => h("button", { type: "button", class: `icon-btn plain${on ? " on" : ""}`, "aria-label": label, title: label,
    "aria-pressed": on === undefined ? null : on ? "true" : "false", onClick: fn }, icon(name));
  // A function, not an array: the phone bar and the desktop bar each need their own nodes.
  const tools = () => [
    t.can.mark && hasInbox && iconBtn("star", a.flagged ? "Tirar a estrela" : "Marcar com estrela", a.star, a.flagged),
    t.can.archive && hasInbox && iconBtn("archive", "Arquivar", () => a.move("archive")),
    t.can.mark && hasInbox && iconBtn("mail", "Marcar como não lida", a.unread),
    t.can.trash && hasInbox && iconBtn("trash", "Mover para a lixeira", () => a.move("trash")),
  ];
  return h("section", { class: "pane pane-detail", "aria-label": "Conversa" },
    h("div", { class: "detail-bar" },
      h("a", { class: "back", href: listHref() }, icon("back"), VIEW_TITLES[state.view] || "Entrada"),
      h("div", { class: "bar-tools" }, tools())),
    h("div", { class: "detail-tools", hidden: true },
      t.can.reply && h("a", { class: "btn small", href: replyHref("reply", t, last) }, icon("reply"), "Responder"),
      t.can.reply && h("a", { class: "btn small ghost", href: replyHref("replyall", t, last) }, icon("replyAll"), "Responder a todos"),
      t.can.reply && h("a", { class: "btn small ghost", href: replyHref("forward", t, last) }, icon("forward"), "Encaminhar"),
      h("span", { class: "spacer" }),
      tools()),
    h("div", { class: "scroll", "data-key": `m:${state.threadKey}` },
      h("article", { class: "msg" },
        h("div", { class: "msg-head" },
          h("h1", {}, opened.subject || "(sem assunto)"),
          h("span", { class: "mono" }, msgs.length > 1 ? `${msgs.length} mensagens · ${t.mailbox_address}` : t.mailbox_address),
          t.agents.map((x) => h("span", { class: "agent-line" }, `${x.agent} ${x.what} ${when(x.ts, { withTime: true })}`))),
        h("div", { class: "thread" }, msgs.map((m, i) => threadMessageView(t, m, i === msgs.length - 1))))),
    t.can.reply && h("div", { class: "detail-foot" },
      h("a", { class: "btn", href: replyHref("reply", t, last) }, "Responder"),
      h("a", { class: "icon-btn", href: replyHref("replyall", t, last), "aria-label": "Responder a todos" }, icon("replyAll")),
      h("a", { class: "icon-btn", href: replyHref("forward", t, last), "aria-label": "Encaminhar" }, icon("forward"))),
  );
}

function size(bytes) {
  if (!bytes) return "0 KB";
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// ── the editor ─────────────────────────────────────────────────────────────

function composePane() {
  const d = state.draft;
  if (!d) return h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, "Abrindo…"));
  const sendable = state.me.mailboxes.filter((m) => m.smtp);
  const answering = ["reply", "replyall"].includes(d.mode) || (d.mode === "draft" && d.in_reply_to);
  const options = (answering ? sendable.filter((m) => m.name === d.mailbox) : sendable).flatMap((m) =>
    m.from_options.map((f, i) => ({ value: `${m.name}|${i === 0 ? "" : f}`, label: f })));
  const bind = (field) => (e) => { d[field] = e.target.value; touchDraft(); };
  const title = { new: "Novo e-mail", reply: "Resposta", replyall: "Resposta a todos", forward: "Encaminhar", draft: "Rascunho" }[d.mode];
  const field = (id, label, value, extra = {}) => h("div", { class: "field" }, h("label", { for: id }, label),
    h("input", { id, value, onInput: bind(id), autocapitalize: id === "subject" ? null : "off", spellcheck: id === "subject" ? null : "false",
      inputmode: id === "subject" ? null : "email", autocomplete: id === "subject" ? "off" : "email", ...extra }));
  const files = h("input", { id: "files", type: "file", multiple: true, class: "sr", tabindex: "-1",
    onChange: (e) => { addFiles([...e.target.files]).catch((err) => toast(err.message)); e.target.value = ""; } });
  return h("section", { class: "pane pane-detail", "aria-label": title },
    h("div", { class: "compose-bar" },
      h("button", { type: "button", class: "btn quiet small", onClick: closeCompose }, "Fechar"),
      h("strong", { class: "bar-title" }, title),
      h("div", { class: "bar-tools" },
        worthSaving(d) && h("button", { type: "button", class: d.confirmDiscard ? "btn quiet small danger" : "icon-btn plain",
          "aria-label": "Descartar rascunho", title: "Descartar rascunho", onClick: discardDraft }, d.confirmDiscard ? "Descartar?" : icon("trash")),
        h("button", { type: "button", class: "btn small", disabled: state.busy, onClick: sendDraft }, state.busy ? "Enviando…" : "Enviar"))),
    h("div", { class: "scroll col", "data-key": `c:${d.key}` },
      h("div", { class: "field" }, h("label", { for: "from" }, "De"),
        h("select", { id: "from", onChange: (e) => changeFrom(e.target.value) },
          options.map((o) => h("option", { value: o.value, selected: o.value === `${d.mailbox}|${d.from}` ? true : null }, o.label)))),
      h("div", { class: "field" }, h("label", { for: "to" }, "Para"),
        h("input", { id: "to", value: d.to, onInput: bind("to"), inputmode: "email", autocomplete: "email", autocapitalize: "off", spellcheck: "false" }),
        !d.showCc && h("button", { type: "button", class: "btn quiet small bare", onClick: () => { d.showCc = true; render(); document.getElementById("cc")?.focus(); } }, "Cc Cco")),
      d.showCc && field("cc", "Cc", d.cc),
      d.showCc && field("bcc", "Cco", d.bcc),
      field("subject", "Assunto", d.subject),
      d.attachments.length > 0 && h("div", { class: "att-list" }, d.attachments.map((x, i) =>
        h("span", { class: "att" }, icon("file"), h("span", { class: "att-name" }, x.filename), h("span", { class: "mono" }, size(x.size)),
          h("button", { type: "button", class: "att-x", "aria-label": `Remover ${x.filename}`,
            onClick: () => { d.attachments.splice(i, 1); touchDraft(); render(); } }, icon("close"))))),
      h("textarea", { id: "body", class: "editor", "aria-label": "Mensagem", onInput: bind("body") }, d.body),
      h("div", { class: "compose-foot" },
        files,
        h("label", { for: "files", class: "btn ghost small" }, icon("clip"), "Anexar"),
        h("span", { id: "draft-status", class: "mono" }, d.status)),
      h("p", { class: "note" }, answering ? `Vai na mesma conversa e fica salva em Enviados de ${boxByName(d.mailbox)?.address || ""}.` :
        "Fica salva em Enviados da caixa escolhida. Enquanto você escreve, o rascunho é salvo sozinho.")),
  );
}

function describe(e) {
  const to = (e.to || []).join(", ");
  if (e.outcome === "denied") {
    return [`${e.agent} foi barrado`,
      e.reason === "not_found" ? "Tentou usar uma caixa fora da permissão dele." :
      e.reason === "from_address" ? "Tentou enviar com um remetente que não é dessa caixa." :
      `Sem permissão para ${({ delete_message: "apagar", send: "enviar", mark_seen: "marcar" })[e.action] || e.action}.`];
  }
  if (e.outcome === "error") return [`${e.agent}: falha em ${e.action}`, "O servidor de e-mail recusou."];
  if (e.action === "send") return [`${e.agent} enviou um e-mail`, to ? `Para ${to}.` : ""];
  if (e.action === "get_message") return [`${e.agent} leu uma mensagem`, ""];
  if (e.action === "mark_seen") return [`${e.agent} marcou como lida`, ""];
  if (e.action === "delete_message") return [`${e.agent} moveu para a lixeira`, e.moved_to ? `Pasta ${e.moved_to}.` : ""];
  return [`${e.agent}: ${e.action}`, ""];
}

function agentsPane() {
  const kinds = [["all", "Tudo"], ["sent", "Envios"], ["denied", "Barrados"]];
  const events = state.activity || [];
  const groups = [];
  for (const e of events) {
    const label = dayLabel(e.ts);
    if (!groups.length || groups[groups.length - 1].label !== label) groups.push({ label, items: [] });
    groups[groups.length - 1].items.push(e);
  }
  return h("section", { class: "pane pane-detail", "aria-label": "Agentes" },
    h("header", { class: "hdr" },
      h("div", { class: "hdr-title" }, menuButton(), h("div", {}, h("h1", { class: "title" }, "Agentes"), h("div", { class: "sub" }, "O que cada um leu, marcou e enviou"))),
      h("div", { class: "seg", role: "group", "aria-label": "Filtrar" }, kinds.map(([k, label]) =>
        h("button", { type: "button", class: "chip", "aria-pressed": state.actKind === k ? "true" : "false",
          onClick: () => { state.actKind = k; loadActivity(); } }, label)))),
    h("div", { class: "scroll ruled", "data-key": "agents" },
      state.activity === null ? h("div", { class: "empty" }, "Carregando…") :
      !events.length ? h("div", { class: "empty" }, "Nenhuma atividade ainda.") :
      groups.map((g) => [h("h2", { class: "day" }, g.label), g.items.map((e) => {
        const [what, detail] = describe(e);
        const kind = e.outcome === "denied" ? "denied" : e.action === "send" ? "sent" : "";
        const link = e.action === "get_message" && e.outcome === "ok" && e.uid && e.mailbox_name;
        return h(link ? "a" : "div", { class: `event ${kind}`, href: link ? `#/m/${encodeURIComponent(e.mailbox_name)}/${encodeURIComponent(e.uid)}` : null },
          h("span", { class: "mono time" }, new Date(e.ts).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })),
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
  return h("section", { class: "pane pane-detail", "aria-label": "Ajustes" },
    h("header", { class: "hdr" }, h("div", { class: "hdr-title" }, menuButton(), h("h1", { class: "title" }, "Ajustes"))),
    h("div", { class: "scroll padded", "data-key": "settings" },
      state.me.manage && manageSections(),
      h("section", { class: "section" + (state.me.manage ? "" : " first") },
        h("h2", {}, "Notificações"),
        h("div", { class: "box" },
          needsInstall ? [
            h("strong", { class: "medium" }, "No iPhone, as notificações chegam só com o mailgrant na Tela de Início."),
            h("ol", {}, h("li", {}, "Toque em Compartilhar, no Safari."), h("li", {}, "Escolha Adicionar à Tela de Início."), h("li", {}, "Abra pelo ícone e volte aqui.")),
          ] : !state.push.supported ? h("span", {}, "Este navegador não recebe notificações.") :
          state.push.subscribed ? [
            h("span", {}, "Ativadas neste aparelho."),
            h("div", { class: "btn-row" },
              h("button", { class: "btn ghost small", onClick: async () => { const r = await api("/push/test", { method: "POST" }); toast(r.sent ? "Enviada." : "Nenhum aparelho recebeu."); } }, "Testar"),
              h("button", { class: "btn quiet small", onClick: disablePush }, "Desativar")),
          ] : [
            h("span", {}, "Receba um aviso quando chegar e-mail nas caixas escolhidas abaixo."),
            h("button", { class: "btn", onClick: enablePush }, "Ativar notificações"),
          ]),
        p && h("div", { class: "plain" },
          boxes.map((m) => h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, m.address)),
            sw(p.notify[m.name], `Notificar ${m.address}`, () => savePrefs({ notify: { [m.name]: !p.notify[m.name] } })))),
          h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, "Avisar quando um agente enviar e-mail")),
            sw(p.notify_agent_send, "Avisar quando um agente enviar", () => savePrefs({ notify_agent_send: !p.notify_agent_send }))))),
      p && h("section", { class: "section" },
        h("h2", {}, "Leitura"),
        h("div", { class: "plain" },
          h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, "Agrupar por conversa"),
            h("span", { class: "detail" }, "Respostas ficam juntas na lista, e a conversa mostra o que você enviou.")),
            sw(p.threads, "Agrupar por conversa", async () => { await savePrefs({ threads: !p.threads }); state.listKey = null; clearThread(); })),
          h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, "Mostrar imagens externas sempre"),
            h("span", { class: "detail" }, p.images ? "Ligado para todos os remetentes."
              : p.image_senders.length ? `Hoje só de: ${p.image_senders.join(", ")}.`
              : "Uma imagem externa avisa o remetente quando e de onde você abriu.")),
            sw(p.images, "Mostrar imagens externas sempre", () => savePrefs({ images: !p.images }))),
          p.image_senders.length > 0 && h("div", { class: "item" }, h("span", { class: "grow" }, h("span", {}, "Esquecer os remetentes liberados")),
            h("button", { type: "button", class: "btn small ghost", onClick: () => savePrefs({ image_senders: [] }) }, "Esquecer")))),
      p && can("send") && Object.keys(p.signatures).length > 0 && h("section", { class: "section" },
        h("h2", {}, "Assinaturas"),
        h("div", { class: "plain" }, Object.keys(p.signatures).map((name) => h("div", { class: "item sig" },
          h("label", { for: `sig-${name}`, class: "mono" }, boxByName(name)?.address || name),
          h("textarea", { id: `sig-${name}`, class: "sig-text", rows: 3, maxlength: 2000, placeholder: "Sem assinatura",
            onChange: async (e) => { await savePrefs({ signatures: { [name]: e.target.value } }); toast("Assinatura salva."); } },
            p.signatures[name])))),
        h("p", { class: "note tight" }, "Entra no fim de cada e-mail novo, resposta e encaminhamento dessa caixa.")),
      h("section", { class: "section" },
        h("h2", {}, "Passkeys"),
        h("div", { class: "plain" },
          (state.passkeys || []).map((k) => h("div", { class: "item" },
            h("span", { class: "grow" }, h("span", {}, k.name), h("span", { class: "mono" }, k.last_used_at ? `usada ${when(k.last_used_at, { withTime: true })}` : "nunca usada")),
            (state.passkeys || []).length > 1 && h("button", { class: "btn quiet small", onClick: async () => {
              await api(`/passkeys/${encodeURIComponent(k.id)}`, { method: "DELETE" }); await loadSettings(); toast("Passkey removida."); } }, "Remover"))),
          h("div", { class: "item" }, h("button", { class: "btn quiet small link-btn", onClick: invite }, "Adicionar outro aparelho"))),
        state.newInvite && h("div", { class: "box" },
          h("span", {}, "Abra este link no outro aparelho. Vale 30 minutos, uma vez."),
          h("span", { class: "link" }, state.newInvite),
          h("div", { class: "btn-row" },
            h("button", { class: "btn ghost small", onClick: () => navigator.clipboard?.writeText(state.newInvite).then(() => toast("Link copiado.")) }, "Copiar"),
            navigator.share && h("button", { class: "btn ghost small", onClick: () => navigator.share({ url: state.newInvite }).catch(() => {}) }, "Compartilhar")))),
      !state.me.manage && h("section", { class: "section" },
        h("h2", {}, "Agentes com acesso"),
        h("div", { class: "plain" }, (state.agents?.agents || []).map((a) => h("div", { class: "item" },
          h("span", { class: "grow" },
            h("span", { class: "medium" }, a.name),
            h("span", { class: "detail" }, `${["read", "mark", "send", "delete"].filter((s) => a.scopes.includes(s)).map((s) => SCOPE_WORDS[s]).join(", ")}${a.scopes.includes("delete") ? "" : ". Não apaga"}.`)),
          h("span", { class: "mono" }, a.mailboxes === "*" ? "todas as caixas" : `${a.mailboxes.length} caixa${a.mailboxes.length === 1 ? "" : "s"}`)))),
        h("p", { class: "note tight" }, "As permissões dos agentes ficam no config do servidor.")),
      h("section", { class: "section" },
        h("div", { class: "plain" },
          h("div", { class: "item" }, h("button", { class: "btn quiet small bare", onClick: async () => { await api("/auth/logout", { method: "POST" }); state.authed = false; render(); } }, "Sair deste aparelho"),
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
      throw new Error(err.name === "NotAllowedError" ? "Confirmação cancelada." : err.message);
    }
    return api(path, opts);
  }
}

async function loadAdmin() {
  const [boxes, agents] = await Promise.all([api("/admin/mailboxes"), api("/admin/agents")]);
  state.admin = { ...boxes, ...agents };
}

const SCOPE_INFO = [
  ["read", "Ler", "Listar, buscar e abrir mensagens."],
  ["mark", "Marcar", "Marcar como lida ou não lida."],
  ["delete", "Apagar", "Mover para a lixeira. Nunca apaga de vez."],
  ["send", "Enviar", "Escrever e responder pelas caixas permitidas."],
];

const slug = (email) => {
  const [local, domain = ""] = (email || "").toLowerCase().split("@");
  return [local, domain.split(".")[0]].filter(Boolean).join("-").replace(/[^a-z0-9_-]/g, "-").replace(/-+/g, "-");
};

function mailboxForm(name) {
  const a = state.admin;
  const m = name === "new" ? null : a.mailboxes.find((x) => x.name === name);
  if (name !== "new" && !m) throw new Error("Caixa não encontrada.");
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
  if (name !== "new" && !a) throw new Error("Agente não encontrado.");
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
    toast(f.isNew ? "Caixa adicionada." : "Caixa salva.");
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
    toast("Caixa removida do mailgrant. Os e-mails continuam no servidor.");
    state.form = null;
    state.me = await api("/me");
    go("/settings");
  });
}

function agentPayload(f) {
  return { name: f.name.trim(), description: f.description.trim(),
    mailboxes: f.all ? ["*"] : [...f.boxes], scopes: SCOPE_INFO.map(([s]) => s).filter((s) => f.scopes.has(s)) };
}

function saveAgent() {
  const f = state.form;
  if (!f.all && !f.boxes.size) return toast("Escolha ao menos uma caixa.");
  if (!f.scopes.size) return toast("Escolha ao menos uma permissão.");
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
      toast("Permissões salvas. Valem a partir de agora.");
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
    toast(`${f.existing.name} não acessa mais nada.`);
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

const copy = (text, done) => navigator.clipboard?.writeText(text).then(() => toast(done)).catch(() => toast("Não deu para copiar."));

function revealBox(r) {
  return h("div", { class: "box reveal" },
    h("strong", { class: "medium" }, r.created ? `Token do ${r.agent}` : `Novo token do ${r.agent}`),
    h("span", {}, r.created ? "Guarde agora: ele não aparece de novo." :
      "O token anterior parou de funcionar. Troque no agente agora; este não aparece de novo."),
    h("code", { class: "link" }, r.token),
    h("div", { class: "btn-row" },
      h("button", { class: "btn small", onClick: () => copy(r.token, "Token copiado.") }, "Copiar token"),
      h("button", { class: "btn ghost small", onClick: () => copy(snippet(r), "Configuração copiada.") }, "Copiar configuração MCP")),
    h("pre", { class: "mcp-snippet" }, snippet(r)));
}

function formField(id, label, value, onInput, extra = {}) {
  return h("div", { class: "field" }, h("label", { for: id }, label),
    h("input", { id, value: value ?? "", onInput, autocapitalize: "off", spellcheck: "false", ...extra }));
}

function tlsSelect(id, value, onChange) {
  return h("select", { id, onChange }, [["ssl", "SSL/TLS"], ["starttls", "STARTTLS"], ["none", "Nenhuma"]].map(([v, l]) =>
    h("option", { value: v, selected: v === value ? true : null }, l)));
}

function serverRows(prefix, part, f) {
  return [
    formField(`${prefix}-host`, "Servidor", part.host, (e) => { part.host = e.target.value; }),
    h("div", { class: "field" }, h("label", { for: `${prefix}-port` }, "Porta"),
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
      h("a", { class: "btn quiet small", href: "#/settings" }, "Voltar"),
      h("strong", { class: "bar-title" }, title),
      actions || h("span", { class: "bar-spacer" })),
    h("div", { class: "scroll padded", "data-key": `form:${state.form?.key || state.reveal?.agent}` }, body));
}

function mailboxPane() {
  const f = state.form;
  if (!f) return formPane("Caixa", h("div", { class: "empty" }, "Abrindo…"));
  const set = (k) => (e) => { f[k] = e.target.value; if (k === "email" && f.isNew && !f.nameTouched) { f.name = slug(f.email); const n = document.getElementById("mb-name"); if (n) n.value = f.name; } };
  const t = f.test;
  return formPane(f.isNew ? "Nova caixa" : f.email, [
    h("div", { class: "plain" },
      formField("mb-email", "E-mail", f.email, set("email"), { type: "email", inputmode: "email", disabled: !f.isNew ? true : null }),
      formField("mb-password", "Senha", f.password, set("password"), { type: "password", autocomplete: "new-password",
        placeholder: f.isNew ? "Senha ou senha de app" : "Mantida (deixe vazio)" }),
      f.smtpOn && formField("mb-display", "Nome", f.display, set("display"), { placeholder: "Como aparece para quem recebe", autocapitalize: null, spellcheck: null }),
      f.isNew && formField("mb-name", "Apelido", f.name, (e) => { f.name = e.target.value; f.nameTouched = true; }, { placeholder: "contato-empresa" })),
    f.isNew && h("p", { class: "note" }, "O apelido é como os agentes chamam a caixa. Não muda depois."),
    h("section", { class: "section" },
      h("h2", {}, "Receber (IMAP)"),
      h("div", { class: "plain" },
        toggleRow("Ler e organizar e-mails", f.imapOn, () => { f.imapOn = !f.imapOn; render(); }),
        f.imapOn && serverRows("imap", f.imap, f))),
    h("section", { class: "section" },
      h("h2", {}, "Enviar (SMTP)"),
      h("div", { class: "plain" },
        toggleRow("Enviar e-mails", f.smtpOn, () => { f.smtpOn = !f.smtpOn; render(); }),
        f.smtpOn && serverRows("smtp", f.smtp, f),
        f.smtpOn && toggleRow("Mesmo usuário e senha do IMAP", f.sameLogin, () => { f.sameLogin = !f.sameLogin; render(); }),
        f.smtpOn && !f.sameLogin && formField("smtp-user", "Usuário", f.smtpUser, set("smtpUser")),
        f.smtpOn && !f.sameLogin && formField("smtp-password", "Senha", f.smtpPassword, set("smtpPassword"),
          { type: "password", autocomplete: "new-password", placeholder: f.isNew ? "" : "Mantida (deixe vazio)" }),
        f.smtpOn && f.imapOn && formField("smtp-copy", "Cópia em", f.saveCopy, set("saveCopy"), { placeholder: "Sent" }))),
    h("section", { class: "section" },
      h("div", { class: "btn-row padded-x" },
        h("button", { class: "btn ghost small", disabled: state.busy, onClick: testMailbox }, state.busy && !t ? "Testando…" : "Testar conexão"),
        t && ["imap", "smtp"].filter((p) => t[p]).map((p) => h("span", { class: `test ${t[p].ok ? "ok" : "bad"}` },
          `${p.toUpperCase()}: ${t[p].ok ? (p === "imap" ? `ok, ${t[p].folders.length} pastas` : "ok") : t[p].error}`)))),
    !f.isNew && h("section", { class: "section" },
      h("h2", {}, "Quem usa"),
      h("p", { class: "note tight" }, f.existing.agents.length ? `Agentes: ${f.existing.agents.join(", ")}.` : "Nenhum agente tem acesso a esta caixa."),
      h("div", { class: "plain" }, h("div", { class: "item" },
        h("button", { class: `btn quiet small bare${f.confirmDelete ? " danger" : ""}`, disabled: state.busy, onClick: deleteMailbox },
          f.confirmDelete ? "Tirar do mailgrant? Toque de novo" : "Remover caixa do mailgrant")))),
  ], h("button", { class: "btn small", disabled: state.busy, onClick: saveMailbox }, f.isNew ? "Adicionar" : "Salvar"));
}

function agentPane() {
  const f = state.form;
  const r = state.reveal;
  if (!f) return formPane("Agente", r ? revealBox(r) : h("div", { class: "empty" }, "Abrindo…"));
  const boxes = state.me.mailboxes;
  return formPane(f.isNew ? "Novo agente" : f.existing.name, [
    r && h("section", { class: "section first" }, revealBox(r)),
    h("div", { class: "plain" },
      f.isNew && formField("ag-name", "Nome", f.name, (e) => { f.name = e.target.value; }, { placeholder: "hermes" }),
      formField("ag-desc", "Descrição", f.description, (e) => { f.description = e.target.value; },
        { placeholder: "Para que serve", autocapitalize: null, spellcheck: null })),
    h("section", { class: "section" },
      h("h2", {}, "Pode"),
      h("div", { class: "plain" }, SCOPE_INFO.map(([s, label, detail]) =>
        toggleRow(label, f.scopes.has(s), () => { f.scopes.has(s) ? f.scopes.delete(s) : f.scopes.add(s); render(); }, detail)))),
    h("section", { class: "section" },
      h("h2", {}, "Nas caixas"),
      h("div", { class: "plain" },
        toggleRow("Todas as caixas", f.all, () => { f.all = !f.all; render(); }, "Inclui as que você adicionar depois."),
        !f.all && boxes.map((m) => toggleRow(m.address, f.boxes.has(m.name), () => {
          f.boxes.has(m.name) ? f.boxes.delete(m.name) : f.boxes.add(m.name); render(); })))),
    !f.isNew && h("section", { class: "section" },
      h("h2", {}, "Token"),
      h("p", { class: "note tight" }, f.existing.token_created_at ? `Gerado em ${new Date(f.existing.token_created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}.` : "Veio do config."),
      h("div", { class: "plain" },
        h("div", { class: "item" }, h("button", { class: `btn quiet small bare${f.confirmRotate ? " danger" : ""}`, disabled: state.busy, onClick: rotateToken },
          f.confirmRotate ? "O token atual vai parar de funcionar. Toque de novo" : "Gerar novo token")),
        h("div", { class: "item" }, h("button", { class: `btn quiet small bare${f.confirmDelete ? " danger" : ""}`, disabled: state.busy, onClick: deleteAgent },
          f.confirmDelete ? `Tirar todo o acesso de ${f.existing.name}? Toque de novo` : "Remover agente")))),
  ], h("button", { class: "btn small", disabled: state.busy, onClick: saveAgent }, f.isNew ? "Criar" : "Salvar"));
}

function manageSections() {
  const a = state.admin;
  if (!a) return h("section", { class: "section" }, h("div", { class: "empty" }, "Carregando…"));
  const scopeText = (s) => SCOPE_INFO.filter(([k]) => s.includes(k)).map(([, l]) => l.toLowerCase()).join(", ");
  return [
    h("section", { class: "section first" },
      h("h2", {}, "Caixas de e-mail"),
      h("div", { class: "plain" },
        a.mailboxes.map((m) => h("a", { class: "item link-item", href: `#/settings/mailbox/${enc(m.name)}` },
          h("span", { class: "grow" }, h("span", {}, m.address),
            h("span", { class: "mono" }, [m.imap && "recebe", m.smtp && "envia"].filter(Boolean).join(" · "))),
          h("span", { class: "mono" }, m.name))),
        h("div", { class: "item" }, h("a", { class: "btn quiet small link-btn", href: "#/settings/mailbox/new" }, "Adicionar caixa")))),
    h("section", { class: "section" },
      h("h2", {}, "Agentes"),
      h("div", { class: "plain" },
        a.agents.map((x) => h("a", { class: "item link-item", href: `#/settings/agent/${enc(x.name)}` },
          h("span", { class: "grow" }, h("span", { class: "medium" }, x.name),
            h("span", { class: "detail" }, `${scopeText(x.scopes)}${x.description ? ` · ${x.description}` : ""}`)),
          h("span", { class: "mono" }, x.mailboxes === "*" ? "todas" : `${x.mailboxes.length} caixa${x.mailboxes.length === 1 ? "" : "s"}`))),
        h("div", { class: "item" }, h("a", { class: "btn quiet small link-btn", href: "#/settings/agent/new" }, "Adicionar agente"))),
      h("p", { class: "note tight" }, "Mudanças valem na hora, sem reiniciar. Salvar pede o Face ID de novo.")),
    h("section", { class: "section" },
      h("div", { class: "plain" }, h("div", { class: "item" },
        h("span", { class: "grow" }, h("span", {}, "Baixar config"), h("span", { class: "detail" }, "Cópia de segurança com as senhas. Guarde em lugar seguro.")),
        h("button", { class: "btn ghost small", onClick: exportConfig }, "Baixar")))),
  ];
}

function tabs(r) {
  const tab = (href, name, label, active) => h("a", { class: "tab", href, "aria-current": active ? "page" : null }, icon(name), label);
  return h("nav", { class: "tabs", "aria-label": "Seções" },
    tab("#/inbox", "inbox", "Entrada", LIST_VIEWS.includes(r.name) || r.name === "m"),
    tab("#/agents", "agents", "Agentes", r.name === "agents"),
    tab("#/settings", "settings", "Ajustes", r.name === "settings"));
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
  else detail = state.view === "drafts" ? h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, "Escolha um rascunho para continuar.")) : messagePane();
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
