export function pairFromMessage(message, sender) {
  if (sender?.frameId !== 0 || !Number.isInteger(sender?.tab?.id)) {
    throw new Error("Página de conexão inválida.");
  }
  const url = new URL(sender.url);
  if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" ||
      url.username || url.password || !url.port || url.pathname !== "/conectar" ||
      url.search || message.origin !== url.origin ||
      !/^[a-f0-9]{64}$/.test(message.key || "") || url.hash !== "#" + message.key) {
    throw new Error("Abra a conexão pelo botão no programa Python.");
  }
  return {origin: url.origin, key: message.key, pageTab: sender.tab.id,
          expires: Date.now() + 180000, tabs: {}, received: {cr: false, al: false}};
}

export function validSession(session, now = Date.now()) {
  if (!session || session.expires <= now || !/^[a-f0-9]{64}$/.test(session.key || "")) return false;
  try {
    const u = new URL(session.origin);
    return u.protocol === "http:" && u.hostname === "127.0.0.1" &&
           Boolean(u.port) && u.origin === session.origin && !u.username && !u.password;
  } catch { return false; }
}

export function credentialFromRequest(details, session) {
  if (!validSession(session) || details.tabId < 0) return null;
  let u;
  try { u = new URL(details.url); } catch { return null; }
  if (u.protocol !== "https:" || u.port || u.username || u.password || u.hash) return null;
  let service;
  if (u.hostname === "www.crunchyroll.com" && details.method === "GET" &&
      /^\/content\/v2\/[A-Za-z0-9-]+\/watch-history$/.test(u.pathname)) service = "cr";
  if (u.hostname === "anilist.co" && u.pathname === "/graphql" &&
      details.method === "POST") service = "al";
  if (!service || session.received[service] || details.tabId !== session.tabs[service]) return null;
  const headers = {};
  const allowed = new Set(["authorization", "cookie", "x-csrf-token", "user-agent", "accept-language"]);
  for (const h of details.requestHeaders || []) {
    const name = String(h.name).toLowerCase();
    if (allowed.has(name) && typeof h.value === "string") {
      if (/[\r\n]/.test(h.value)) return null;
      headers[name] = h.value;
    }
  }
  if (service === "cr" && !/^Bearer \S+$/i.test(headers.authorization || "")) return null;
  if (service === "al" && (!headers.cookie || !headers["x-csrf-token"])) return null;
  return {service, url: u.href, headers};
}

export function samePage(sender, session) {
  try {
    const u = new URL(sender.url);
    return sender.frameId === 0 && sender.tab?.id === session.pageTab &&
           u.origin === session.origin && u.pathname === "/conectar";
  } catch { return false; }
}
