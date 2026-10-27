import test from "node:test";
import assert from "node:assert/strict";
import {pairFromMessage, validSession, credentialFromRequest, samePage} from "../extensao_chrome/protocol.mjs";

const key = "a".repeat(64);
const origin = "http://127.0.0.1:12345";
const sender = () => ({url: origin + "/conectar#" + key, frameId: 0, tab: {id: 10}});
const message = () => ({type: "cral-pair", origin, key});
const session = () => ({...pairFromMessage(message(), sender()),
                       tabs: {al: 11, cr: 12}});
const al = () => ({url: "https://anilist.co/graphql", method: "POST", tabId: 11,
  requestHeaders: [{name: "Cookie", value: "fake_session=fake"},
                  {name: "X-CSRF-TOKEN", value: "fake-csrf"},
                  {name: "Sec-Fetch-Site", value: "same-origin"}]});
const cr = () => ({url: "https://www.crunchyroll.com/content/v2/account/watch-history?page_size=100",
  method: "GET", tabId: 12, requestHeaders: [{name: "Authorization", value: "Bearer fake-jwt"}]});

test("pairing validates page, secret, frame and port", () => {
  assert.equal(pairFromMessage(message(), sender()).origin, origin);
  for (const url of ["https://evil.example/conectar#" + key,
                    "http://127.0.0.1/conectar#" + key,
                    origin + "/other#" + key, origin + "/conectar#wrong",
                    "http://user@127.0.0.1:12345/conectar#" + key]) {
    assert.throws(() => pairFromMessage(message(), {...sender(), url}));
  }
  assert.throws(() => pairFromMessage(message(), {...sender(), frameId: 1}));
  assert.throws(() => pairFromMessage({...message(), key: "wrong"}, sender()));
});

test("session expires and arbitrary targets are refused", () => {
  assert.equal(validSession(session()), true);
  assert.equal(validSession({...session(), expires: 0}), false);
  assert.equal(validSession({...session(), origin: "https://evil.example"}), false);
  assert.equal(samePage(sender(), session()), true);
  assert.equal(samePage({...sender(), tab: {id: 99}}, session()), false);
});

test("only necessary authenticated headers are forwarded", () => {
  const p = credentialFromRequest(al(), session());
  assert.equal(p.service, "al");
  assert.equal(p.headers.cookie, "fake_session=fake");
  assert.equal(p.headers["sec-fetch-site"], undefined);
  assert.equal(credentialFromRequest(cr(), session()).service, "cr");
});

test("capture is limited to owned helper tabs and exact endpoints", () => {
  for (const request of [{...al(), tabId: 999}, {...al(), tabId: -1},
                         {...al(), method: "GET"},
                         {...al(), url: "https://anilist.co/settings"},
                         {...cr(), url: "https://evil.example/content/v2/account/watch-history"}]) {
    assert.equal(credentialFromRequest(request, session()), null);
  }
  assert.equal(credentialFromRequest(al(), {...session(), expires: 0}), null);
  assert.equal(credentialFromRequest(al(), {...session(), received: {al: true}}), null);
});

test("partial and unsafe authentication headers are ignored", () => {
  assert.equal(credentialFromRequest({...al(), requestHeaders: []}, session()), null);
  assert.equal(credentialFromRequest({...cr(), requestHeaders: []}, session()), null);
  const request = al();
  request.requestHeaders[0].value += "\nInjected: bad";
  assert.equal(credentialFromRequest(request, session()), null);
});

test("background pairs, opens inactive tabs, captures both and closes owned tabs", async () => {
  const oldChrome = globalThis.chrome, oldFetch = globalThis.fetch;
  let stored = {}, networkListener, messageListener, nextTab = 20;
  const tabs = new Map(), posts = [], created = [];
  globalThis.chrome = {
    storage: {session: {
      get: async () => structuredClone(stored),
      set: async value => { stored = structuredClone({...stored, ...value}); },
      remove: async name => { delete stored[name]; }
    }},
    tabs: {
      create: async options => {
        created.push(options);
        const tab = {id: ++nextTab, url: options.url};
        tabs.set(tab.id, tab);
        return {...tab};
      },
      update: async (id, options) => {
        tabs.set(id, {id, ...options});
        const request = options.url.includes("anilist.co") ? al() : cr();
        request.tabId = id;
        networkListener(request);
        return tabs.get(id);
      },
      get: async id => tabs.get(id),
      remove: async id => { tabs.delete(id); }
    },
    webRequest: {onBeforeSendHeaders: {addListener: listener => { networkListener = listener; }}},
    runtime: {onMessage: {addListener: listener => { messageListener = listener; }}}
  };
  globalThis.fetch = async (url, options) => {
    assert.equal(new URL(url).origin, origin);
    assert.equal(options.headers.Authorization, "Bearer " + key);
    if (url.endsWith("/bridge/access")) posts.push(JSON.parse(options.body));
    return {ok: true, json: async () => ({protocol: "cral-local-bridge-v1"})};
  };
  try {
    await import("../extensao_chrome/background.mjs");
    const call = (msg, from = sender()) =>
      new Promise(resolve => assert.equal(messageListener(msg, from, resolve), true));
    const result = await call(message());
    assert.equal(result.ok, true);
    assert.equal(created.length, 2);
    assert.ok(created.every(options => options.active === false && options.url === "about:blank"));
    for (let i = 0; i < 50 && tabs.size; i++) await new Promise(resolve => setTimeout(resolve, 5));
    assert.deepEqual(posts.map(p => p.service).sort(), ["al", "cr"]);
    assert.equal(tabs.size, 0);
    assert.equal(JSON.stringify(stored).includes("fake_session"), false);
    assert.equal(JSON.stringify(stored).includes("fake-jwt"), false);
    const status = await call({type: "cral-status"});
    assert.equal(status.complete, true);
    await call(message());
    assert.equal(created.length, 2, "reload must not create duplicate tabs");
    const rejected = await call({...message(), key: "x"}, {...sender(), url: "https://evil.example/"});
    assert.equal(rejected.ok, false);
    assert.equal(posts.length, 2);
  } finally {
    globalThis.chrome = oldChrome;
    globalThis.fetch = oldFetch;
  }
});
