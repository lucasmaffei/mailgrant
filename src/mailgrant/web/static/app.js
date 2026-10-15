// mailgrant web app. No framework, no build step: the server ships these
// files as they are. Everything that comes from mail is inserted as text
// (textContent), never as HTML.

const API = "/app/api";
const WIDE = window.matchMedia("(min-width: 1000px)");

const state = {
  authed: false,
  hasPasskeys: false,
  setupCode: false,
  me: null,
  counts: {},
  total: 0,
  box: "all",
  q: "",
  limit: 40,
  list: [],
  listErrors: [],
  listKey: null,
  loadingList: false,
  msg: null,
  msgKey: null,
  draft: null,
  prefs: null,
  passkeys: null,
  agents: null,
  activity: null,
  actKind: "all",
  invite: null,
  push: { supported: false, subscribed: false },
  busy: false,
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

async function api(path, { method = "GET", body } = {}) {
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
const shortAddr = (a) => (a || "").replace(/\.(com|com\.br|link|net|org|dev)$/, "");
const SCOPE_WORDS = { read: "lê", mark: "marca", delete: "apaga", send: "envia" };

// ── routing ───────────────────────────────────────────────────────────────

function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "inbox").split("/").map(decodeURIComponent);
  return { name: parts[0] || "inbox", args: parts.slice(1) };
}
const go = (path) => (location.hash = path);

async function onRoute() {
  const r = route();
  if (r.name === "invite") {
    state.invite = r.args[0] || null;
    if (!state.authed) return render();
  }
  if (!state.authed) return render();
  try {
    if (r.name === "inbox") {
      state.box = r.args[0] || "all";
      state.msg = null;
      state.msgKey = null;
      render();
      await loadList();
    } else if (r.name === "m") {
      if (!state.list.length) loadList();
      await openMessage(r.args[0], r.args[1]);
    } else if (r.name === "reply" || r.name === "compose") {
      if (r.name === "reply" && state.msgKey !== `${r.args[0]}/${r.args[1]}`) await openMessage(r.args[0], r.args[1], false);
      startDraft(r.name === "reply" ? state.msg : null);
      render();
    } else if (r.name === "agents") {
      render();
      await loadActivity();
    } else if (r.name === "settings") {
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
  state.me = await api("/me");
  refreshCounts();
}

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

async function loadList(force = false) {
  const key = `${state.box}|${state.q}|${state.limit}`;
  if (!force && key === state.listKey && state.list.length) return;
  state.loadingList = true;
  render();
  try {
    const params = new URLSearchParams({ limit: state.limit });
    if (state.box !== "all") params.set("mailbox", state.box);
    if (state.q) params.set("q", state.q);
    const data = await api(`/inbox?${params}`);
    state.list = data.messages;
    state.listErrors = data.errors;
    state.listKey = key;
  } finally {
    state.loadingList = false;
    render();
  }
}

async function openMessage(box, uid, markSeen = true) {
  state.msgKey = `${box}/${uid}`;
  state.msg = null;
  render();
  const msg = await api(`/messages/${encodeURIComponent(box)}/${encodeURIComponent(uid)}`);
  if (state.msgKey !== `${box}/${uid}`) return;
  state.msg = msg;
  render();
  const row = state.list.find((m) => m.mailbox === box && String(m.uid) === String(uid));
  if (markSeen && msg.can.mark && row?.unread) {
    await api(`/messages/${encodeURIComponent(box)}/${encodeURIComponent(uid)}/seen`, { method: "POST", body: { seen: true } });
    row.unread = false;
    refreshCounts();
  }
}

async function loadActivity() {
  const [act, agents] = await Promise.all([api(`/activity?kind=${state.actKind}`), state.agents ? null : api("/agents")]);
  state.activity = act.events;
  if (agents) state.agents = agents;
  render();
}

async function loadSettings() {
  const [prefs, keys, agents] = await Promise.all([api("/prefs"), api("/passkeys"), api("/agents")]);
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

// ── passkeys ──────────────────────────────────────────────────────────────

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
    await api("/auth/login/verify", {
      method: "POST",
      body: {
        challenge_id,
        credential: {
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
        },
      },
    });
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

// ── drafts ────────────────────────────────────────────────────────────────

function startDraft(original) {
  const key = original ? `reply:${original.mailbox}/${original.uid}` : "new";
  if (state.draft?.key === key) return;
  const sendable = state.me.mailboxes.filter((m) => m.smtp && state.me.scopes.includes("send"));
  if (original) {
    const quoted = original.body.split("\n").map((l) => `> ${l}`).join("\n");
    state.draft = {
      key,
      mailbox: original.mailbox,
      from: "",
      to: original.from_address,
      subject: /^re:/i.test(original.subject) ? original.subject : `Re: ${original.subject}`,
      body: `\n\nEm ${new Date(original.date).toLocaleString("pt-BR")}, ${original.from} escreveu:\n${quoted}`,
      in_reply_to: original.message_id,
      references: `${original.references || ""} ${original.message_id || ""}`.trim(),
    };
  } else {
    const first = sendable.find((m) => m.name === state.box) || sendable[0];
    state.draft = { key, mailbox: first?.name || "", from: "", to: "", subject: "", body: "", in_reply_to: null, references: null };
  }
}

async function sendDraft() {
  const d = state.draft;
  const to = d.to.split(/[,;\s]+/).filter(Boolean);
  if (!to.length) return toast("Falta o destinatário.");
  state.busy = true;
  render();
  try {
    await api("/send", {
      method: "POST",
      body: { mailbox: d.mailbox, to, subject: d.subject, body_text: d.body, from_address: d.from || null,
              in_reply_to: d.in_reply_to, references: d.references },
    });
    toast("Enviado.");
    const wasReply = d.key.startsWith("reply:");
    state.draft = null;
    history.length > 1 && wasReply ? history.back() : go("/inbox");
  } catch (e) {
    toast(e.message);
  } finally {
    state.busy = false;
    render();
  }
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

function sidebar(r) {
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const current = r.name === "inbox" || r.name === "m" ? state.box : null;
  return h("aside", { class: "side" },
    h("div", { class: "wordmark" }, "mailgrant", h("i", {}, ".")),
    state.me.scopes.includes("send") && h("a", { href: "#/compose", class: "btn small side-compose" }, "Escrever"),
    h("nav", { "aria-label": "Caixas" },
      h("a", { href: "#/inbox", "aria-current": current === "all" ? "page" : null },
        h("span", {}, "Todas as caixas"), state.total ? h("span", { class: "count" }, state.total) : null),
      boxes.map((m) => h("a", { href: `#/inbox/${encodeURIComponent(m.name)}`, "aria-current": current === m.name ? "page" : null },
        h("span", {}, m.address), state.counts[m.name] ? h("span", { class: "count" }, state.counts[m.name]) : null)),
    ),
    h("nav", { class: "bottom", "aria-label": "Mais" },
      h("a", { href: "#/agents", "aria-current": r.name === "agents" ? "page" : null }, h("span", {}, "Agentes")),
      h("a", { href: "#/settings", "aria-current": r.name === "settings" ? "page" : null }, h("span", {}, "Ajustes")),
    ),
  );
}

function listPane(r) {
  const boxes = state.me.mailboxes.filter((m) => m.imap);
  const current = boxByName(state.box);
  let search;
  const doSearch = () => { state.q = search.value.trim(); state.limit = 40; loadList(true); };
  const unreadHere = state.box === "all" ? state.total : state.counts[state.box] || 0;
  return h("section", { class: "pane pane-list", "aria-label": "Mensagens" },
    h("header", { class: "hdr" },
      h("div", { class: "hdr-row" },
        h("div", {},
          h("h1", { class: "title" }, current ? current.address : WIDE.matches ? "Todas as caixas" : "Entrada"),
          h("div", { class: "sub" }, `${unreadHere} não lidas · ${boxes.length} caixas`)),
        state.me.scopes.includes("send") && h("a", { href: "#/compose", class: "icon-btn", "aria-label": "Escrever e-mail" }, icon("pencil")),
      ),
      h("label", { class: "search" }, icon("search"),
        search = h("input", { id: "q", type: "search", placeholder: "Buscar", "aria-label": "Buscar nas caixas", value: state.q,
          onKeydown: (e) => e.key === "Enter" && doSearch(), onSearch: doSearch })),
      h("div", { class: "chips", role: "group", "aria-label": "Filtrar por caixa" },
        [{ name: "all", address: "Todas" }, ...boxes].map((m) =>
          h("button", { type: "button", class: "chip", "aria-pressed": state.box === m.name ? "true" : "false",
            onClick: () => go(m.name === "all" ? "/inbox" : `/inbox/${encodeURIComponent(m.name)}`) },
            shortAddr(m.address), (m.name === "all" ? state.total : state.counts[m.name]) ? h("span", { class: "n" }, m.name === "all" ? state.total : state.counts[m.name]) : null))),
    ),
    h("div", { class: "scroll" },
      state.listErrors.map((e) => h("div", { class: "err" }, `${e.mailbox}: ${e.error}`)),
      state.loadingList && !state.list.length ? h("div", { class: "empty" }, "Carregando…") :
      !state.list.length ? h("div", { class: "empty" }, state.q ? "Nada encontrado." : "Nenhuma mensagem aqui.") :
      h("div", { class: "rows" }, state.list.map((m) =>
        h("a", { class: `row${m.unread ? " unread" : ""}`, href: `#/m/${encodeURIComponent(m.mailbox)}/${encodeURIComponent(m.uid)}`,
          "aria-current": state.msgKey === `${m.mailbox}/${m.uid}` ? "true" : null },
          m.unread && h("span", { class: "dot", "aria-label": "Não lida" }),
          h("div", { class: "top" }, h("span", { class: "from" }, m.from || m.from_address), h("span", { class: "mono" }, when(m.ts))),
          h("span", { class: "subject" }, m.subject || "(sem assunto)"),
          h("span", { class: "mono" }, m.mark ? `${m.mailbox_address} · ${m.mark}` : m.mailbox_address)))),
      state.list.length >= state.limit && h("button", { class: "more", onClick: () => { state.limit += 40; loadList(true); } }, "Carregar mais"),
    ),
  );
}

function messagePane() {
  const m = state.msg;
  const backTo = state.box === "all" ? "#/inbox" : `#/inbox/${encodeURIComponent(state.box)}`;
  if (!m) return h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, state.msgKey ? "Abrindo…" : "Selecione uma mensagem."));
  const path = `/messages/${encodeURIComponent(m.mailbox)}/${encodeURIComponent(m.uid)}`;
  const markUnread = async () => {
    await api(`${path}/seen`, { method: "POST", body: { seen: false } });
    const row = state.list.find((x) => x.mailbox === m.mailbox && String(x.uid) === String(m.uid));
    if (row) row.unread = true;
    refreshCounts();
    go(backTo.slice(1));
  };
  const trash = async () => {
    const r = await api(`${path}/trash`, { method: "POST", body: {} });
    state.list = state.list.filter((x) => !(x.mailbox === m.mailbox && String(x.uid) === String(m.uid)));
    toast(`Movida para ${r.moved_to || "a lixeira"}.`);
    refreshCounts();
    go(backTo.slice(1));
  };
  const replyHref = `#/reply/${encodeURIComponent(m.mailbox)}/${encodeURIComponent(m.uid)}`;
  return h("section", { class: "pane pane-detail", "aria-label": "Mensagem" },
    h("div", { class: "detail-bar" },
      h("a", { class: "back", href: backTo }, icon("back"), "Entrada"),
      h("div", {},
        m.can.mark && h("button", { class: "icon-btn plain", "aria-label": "Marcar como não lida", onClick: markUnread }, icon("mail")),
        m.can.trash && h("button", { class: "icon-btn plain", "aria-label": "Mover para a lixeira", onClick: trash }, icon("trash")))),
    h("div", { class: "detail-tools", hidden: true },
      m.can.reply && h("a", { class: "btn small", href: replyHref }, "Responder"),
      h("span", { class: "spacer" }),
      m.can.mark && h("button", { class: "btn small quiet", onClick: markUnread }, "Marcar como não lida"),
      m.can.trash && h("button", { class: "btn small quiet", onClick: trash }, "Lixeira")),
    h("div", { class: "scroll" },
      h("article", { class: "msg" },
        h("div", { class: "msg-head" },
          h("h1", {}, m.subject || "(sem assunto)"),
          h("div", { class: "who" }, h("strong", {}, m.from || m.from_address),
            h("span", { class: "mono" }, `${m.from_address} → ${m.mailbox_address} · ${when(Date.parse(m.date) / 1000, { withTime: true })}`)),
          m.agents.map((a) => h("span", { class: "agent-line" }, `${a.agent} ${a.what} ${when(a.ts, { withTime: true })}`))),
        h("div", { class: "rule" }),
        h("div", { class: "body" }, linkify(m.body || "(mensagem sem texto)")),
        m.attachments.map((a) => h("a", { class: "attach", href: `${API}${path}/attachments/${a.index}`, download: a.filename || "anexo" },
          icon("file"), h("span", {}, a.filename || "anexo"), h("span", { class: "mono" }, `${Math.max(1, Math.round(a.size / 1024))} KB`))))),
    m.can.reply && h("div", { class: "detail-foot" }, h("a", { class: "btn", href: replyHref }, "Responder")),
  );
}

function composePane() {
  const d = state.draft;
  if (!d) return h("section", { class: "pane pane-detail" }, h("div", { class: "empty" }, "Abrindo…"));
  const sendable = state.me.mailboxes.filter((m) => m.smtp);
  const replying = d.key.startsWith("reply:");
  const options = (replying ? sendable.filter((m) => m.name === d.mailbox) : sendable).flatMap((m) =>
    m.from_options.map((f, i) => ({ value: `${m.name}|${i === 0 ? "" : f}`, label: f })));
  const bind = (field) => (e) => { d[field] = e.target.value; };
  return h("section", { class: "pane pane-detail", "aria-label": replying ? "Resposta" : "Novo e-mail" },
    h("div", { class: "compose-bar" },
      h("button", { class: "btn quiet small", onClick: () => { state.draft = null; history.back(); } }, "Cancelar"),
      h("strong", { class: "bar-title" }, replying ? "Resposta" : "Novo e-mail"),
      h("button", { class: "btn small", disabled: state.busy, onClick: sendDraft }, state.busy ? "Enviando…" : "Enviar")),
    h("div", { class: "scroll col" },
      h("div", { class: "field" }, h("label", { for: "from" }, "De"),
        h("select", { id: "from", onChange: (e) => { const [box, from] = e.target.value.split("|"); d.mailbox = box; d.from = from; } },
          options.map((o) => h("option", { value: o.value, selected: o.value === `${d.mailbox}|${d.from}` ? true : null }, o.label)))),
      h("div", { class: "field" }, h("label", { for: "to" }, "Para"),
        h("input", { id: "to", type: "email", multiple: true, value: d.to, autocomplete: "email", onInput: bind("to") })),
      h("div", { class: "field" }, h("label", { for: "subject" }, "Assunto"),
        h("input", { id: "subject", value: d.subject, onInput: bind("subject") })),
      h("textarea", { id: "body", class: "editor", "aria-label": "Mensagem", onInput: bind("body") }, d.body),
      h("p", { class: "note" }, replying ? `Vai na mesma conversa e fica salva em Enviados de ${boxByName(d.mailbox)?.address || ""}.` :
        "Fica salva em Enviados da caixa escolhida.")),
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
      h("div", {}, h("h1", { class: "title" }, "Agentes"), h("div", { class: "sub" }, "O que cada um leu, marcou e enviou")),
      h("div", { class: "seg", role: "group", "aria-label": "Filtrar" }, kinds.map(([k, label]) =>
        h("button", { type: "button", class: "chip", "aria-pressed": state.actKind === k ? "true" : "false",
          onClick: () => { state.actKind = k; loadActivity(); } }, label)))),
    h("div", { class: "scroll ruled" },
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
    h("header", { class: "hdr" }, h("h1", { class: "title" }, "Ajustes")),
    h("div", { class: "scroll padded" },
      h("section", { class: "section first" },
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
      h("section", { class: "section" },
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

function tabs(r) {
  const tab = (href, name, label, active) => h("a", { class: "tab", href, "aria-current": active ? "page" : null }, icon(name), label);
  return h("nav", { class: "tabs", "aria-label": "Seções" },
    tab("#/inbox", "inbox", "Entrada", ["inbox", "m"].includes(r.name)),
    tab("#/agents", "agents", "Agentes", r.name === "agents"),
    tab("#/settings", "settings", "Ajustes", r.name === "settings"));
}

function render() {
  const root = document.getElementById("app");
  const focused = document.activeElement?.id;
  const sel = focused && document.activeElement.selectionStart;
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
  else if (r.name === "reply" || r.name === "compose") detail = composePane();
  else if (r.name === "agents") detail = agentsPane();
  else if (r.name === "settings") detail = settingsPane();
  else detail = messagePane();
  document.body.dataset.view = ["agents", "settings"].includes(r.name) ? "page" :
    ["m", "reply", "compose"].includes(r.name) ? "detail" : "list";
  root.append(h("div", { class: "shell" }, sidebar(r), listPane(r), detail), tabs(r));
  if (focused) {
    const el = document.getElementById(focused);
    if (el) { el.focus(); if (sel !== undefined && el.setSelectionRange) try { el.setSelectionRange(sel, sel); } catch (_) {} }
  }
}

// ── boot ──────────────────────────────────────────────────────────────────

async function boot() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).catch(() => {});
  window.addEventListener("hashchange", onRoute);
  WIDE.addEventListener("change", render);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && state.authed) { refreshCounts(); if (route().name === "inbox") loadList(true); } });
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
