import {pairFromMessage, validSession, credentialFromRequest, samePage} from "./protocol.mjs";

// Configuracao da ponte apenas em RAM (storage.session). Credenciais nunca sao armazenadas.
let serial = Promise.resolve();
function exclusive(job) {
  const result = serial.then(job);
  serial = result.catch(() => {});
  return result;
}

async function current() {
  const {bridge} = await chrome.storage.session.get("bridge");
  return validSession(bridge) ? bridge : null;
}

async function localRequest(session, path, payload) {
  const response = await fetch(session.origin + path, {
    method: payload ? "POST" : "GET",
    headers: {"Authorization": "Bearer " + session.key, ...(payload ? {"Content-Type": "application/json"} : {})},
    body: payload ? JSON.stringify(payload) : undefined,
    cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000)
  });
  if (!response.ok) throw new Error("A conexão local expirou. Clique em Conectar pelo Chrome novamente.");
  return response.json();
}

function status(session) {
  return {ok: true, received: session.received,
          complete: Boolean(session.received.cr && session.received.al),
          error: session.error || ""};
}

async function pair(message, sender) {
  const next = pairFromMessage(message, sender);
  const old = await current();
  if (old?.key === next.key && old.pageTab === next.pageTab) return status(old);
  const pong = await localRequest(next, "/bridge/ping");
  if (pong.protocol !== "cral-local-bridge-v1") throw new Error("Programa local não reconhecido.");
  // A nova conexao invalida imediatamente qualquer captura antiga.
  await chrome.storage.session.set({bridge: next});
  const targets = {al: "https://anilist.co/home", cr: "https://www.crunchyroll.com/history"};
  try {
    for (const [service, url] of Object.entries(targets)) {
      const tab = await chrome.tabs.create({url: "about:blank", active: false});
      const latest = await current();
      if (!latest || latest.key !== next.key) {
        await chrome.tabs.remove(tab.id).catch(() => {});
        throw new Error("Conexão substituída ou expirada.");
      }
      latest.tabs[service] = tab.id;
      await chrome.storage.session.set({bridge: latest});
      await chrome.tabs.update(tab.id, {url});
    }
  } catch {
    const latest = await current();
    if (latest?.key === next.key) {
      latest.error = "Não foi possível abrir as abas de apoio. Tente conectar novamente.";
      await chrome.storage.session.set({bridge: latest});
    }
    throw new Error("Não foi possível abrir as abas de apoio.");
  }
  return status((await current()) || next);
}

async function capture(details) {
  const session = await current();
  if (!session) return;
  const payload = credentialFromRequest(details, session);
  if (!payload) return;
  try {
    await localRequest(session, "/bridge/access", payload);
    const latest = await current();
    if (!latest || latest.key !== session.key) return;
    latest.received[payload.service] = true;
    latest.error = "";
    await chrome.storage.session.set({bridge: latest});
    if (latest.received.al && latest.received.cr) {
      for (const id of Object.values(latest.tabs)) {
        try {
          const tab = await chrome.tabs.get(id);
          const u = new URL(tab.url);
          // Fecha apenas abas de apoio que continuam nas paginas de coleta.
          if ((u.hostname === "anilist.co" && /^\/(?:home)?\/?$/.test(u.pathname)) ||
              (u.hostname === "www.crunchyroll.com" && /\/history\/?$/.test(u.pathname))) {
            await chrome.tabs.remove(id);
          }
        } catch {}
      }
    }
  } catch {
    const latest = await current();
    if (latest?.key === session.key) {
      latest.error = "O programa recusou o acesso ou a conexão local expirou. Conecte novamente.";
      await chrome.storage.session.set({bridge: latest});
    }
  }
}

chrome.webRequest.onBeforeSendHeaders.addListener(details => {
  // Serializa os dois envios para nao perder confirmacoes concorrentes.
  void exclusive(() => capture(details));
}, {urls: [
  "https://www.crunchyroll.com/content/v2/*/watch-history*",
  "https://anilist.co/graphql*"
]}, ["requestHeaders", "extraHeaders"]);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !["cral-pair", "cral-status", "cral-stop"].includes(message.type)) return false;
  (async () => {
    if (message.type === "cral-pair") return exclusive(() => pair(message, sender));
    const session = await current();
    if (!session || !samePage(sender, session)) return {ok: false, error: "Conexão encerrada ou expirada."};
    if (message.type === "cral-stop") {
      await exclusive(() => chrome.storage.session.remove("bridge"));
      return {ok: true};
    }
    return status(session);
  })().then(sendResponse).catch(error => sendResponse({ok: false, error: error.message}));
  return true;
});
