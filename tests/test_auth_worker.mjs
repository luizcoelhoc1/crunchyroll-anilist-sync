import test from "node:test";
import assert from "node:assert/strict";
import {createWorker} from "../cloudflare/worker.mjs";

const ORIGIN = "https://auth.example.workers.dev";
const SECRET = "server-secret-that-must-never-leak";
const VERIFIER = "v".repeat(43);
const STATE = "s".repeat(43);
const CALLBACK = "http://127.0.0.1:8765/anilist/callback";
const b64 = bytes => Buffer.from(bytes).toString("base64url");

async function fixture() {
  let clock = 1700000000;
  const calls = [];
  const spent = new Set();
  const env = {ANILIST_CLIENT_ID: "55193", ANILIST_CLIENT_SECRET: SECRET, STATE_SECRET: "k".repeat(64),
    AUTH_RATE_LIMITER: {limit: async () => ({success: true})}};
  const worker = createWorker({now: () => clock, fetcher: async (url, options) => {
    calls.push({url, options});
    const body = JSON.parse(options.body);
    if (spent.has(body.code)) return new Response('{"error":"invalid_grant"}', {status: 400});
    spent.add(body.code);
    return Response.json({access_token: "user-token", token_type: "Bearer", expires_in: 3600,
      client_secret: SECRET, unrelated: "not returned to the client"});
  }});
  const invoke = (path, data, options = {}) => worker.fetch(new Request(ORIGIN + path, {
    method: data === undefined ? "GET" : "POST",
    headers: {"Content-Type": "application/json", "CF-Connecting-IP": "192.0.2.1", ...options.headers},
    ...(data === undefined ? {} : {body: JSON.stringify(data)}), ...options,
  }), env);
  const challenge = b64(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(VERIFIER)));
  const sessionBody = {client_id: "55193", state: STATE, code_challenge: challenge, redirect_uri: CALLBACK};
  const issue = async (change = {}) => {
    const result = await invoke("/v1/session", {...sessionBody, ...change});
    assert.equal(result.status, 200);
    assert.equal(result.headers.get("Cache-Control"), "no-store");
    return (await result.json()).session;
  };
  return {env, calls, invoke, worker, sessionBody, issue, advance: seconds => {clock += seconds;}};
}

test("complete flow binds state, loopback, proof and the fixed AniList endpoint", async () => {
  const f = await fixture();
  const session = await f.issue();
  const callback = await f.invoke("/v1/callback?" + new URLSearchParams({state: session, code: "code-one"}));
  assert.equal(callback.status, 302);
  const target = new URL(callback.headers.get("Location"));
  assert.equal(target.origin + target.pathname, CALLBACK);
  assert.equal(target.searchParams.get("state"), STATE);
  assert.equal(target.searchParams.get("code"), "code-one");
  assert.equal(callback.headers.get("Referrer-Policy"), "no-referrer");
  const result = await f.invoke("/v1/token", {session, code: "code-one", code_verifier: VERIFIER});
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), {access_token: "user-token", token_type: "Bearer", expires_in: 3600});
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].url, "https://anilist.co/api/v2/oauth/token");
  assert.equal(f.calls[0].options.redirect, "manual");
  assert.equal(f.calls[0].options.headers["User-Agent"], "CrunchyrollAniListSync/1.0");
  assert.deepEqual(JSON.parse(f.calls[0].options.body), {grant_type: "authorization_code",
    client_id: "55193", client_secret: SECRET, code: "code-one", redirect_uri: ORIGIN + "/v1/callback"});
});

test("wrong proof is refused before calling AniList", async () => {
  const f = await fixture(), session = await f.issue();
  const result = await f.invoke("/v1/token", {session, code: "code-one", code_verifier: "x".repeat(43)});
  assert.equal(result.status, 403);
  assert.equal(f.calls.length, 0);
});

test("redirect responses are rejected without forwarding the secret to another host", async () => {
  const f = await fixture(), session = await f.issue();
  const calls = [];
  const worker = createWorker({now: () => 1700000000, fetcher: async (url, options) => {
    calls.push({url, options});
    assert.equal(options.redirect, "manual");
    return new Response(null, {status: 302, headers: {Location: "https://untrusted.example/token"}});
  }});
  const result = await worker.fetch(new Request(ORIGIN + "/v1/token", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({session, code: "valid-code", code_verifier: VERIFIER}),
  }), f.env);
  assert.equal(result.status, 502);
  assert.deepEqual(await result.json(), {error: "provider_redirect"});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://anilist.co/api/v2/oauth/token");
});

test("default fetch preserves the receiver required by the Workers runtime", async () => {
  const f = await fixture(), session = await f.issue();
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async function() {
      assert.equal(this, globalThis, "Cloudflare rejects an unbound global fetch");
      return Response.json({access_token: "user-token", token_type: "Bearer", expires_in: 3600});
    };
    const worker = createWorker({now: () => 1700000000});
    const result = await worker.fetch(new Request(ORIGIN + "/v1/token", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session, code: "valid-code", code_verifier: VERIFIER}),
    }), f.env);
    assert.equal(result.status, 200);
  } finally { globalThis.fetch = original; }
});

test("tampered, expired or cross-origin sessions cannot redirect or exchange", async () => {
  const f = await fixture(), session = await f.issue();
  const modified = "x" + session.slice(1);
  assert.equal((await f.invoke("/v1/callback?" + new URLSearchParams({state: modified, code: "secret-code"}))).status, 400);
  const crossOrigin = await f.worker.fetch(new Request("https://other.example.workers.dev/v1/token", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({session, code: "secret-code", code_verifier: VERIFIER}),
  }), f.env);
  assert.equal(crossOrigin.status, 400);
  f.advance(601);
  assert.equal((await f.invoke("/v1/token", {session, code: "secret-code", code_verifier: VERIFIER})).status, 400);
  assert.equal(f.calls.length, 0);
});

test("redirects are limited to the exact loopback route", async () => {
  const f = await fixture();
  for (const redirect_uri of ["https://evil.example/", "http://localhost:8765/anilist/callback",
    CALLBACK + "?next=evil", CALLBACK + "#fragment", "http://127.0.0.1:22/anilist/callback",
    "http://127.0.0.1:8765/other", "http://127.0.0.1.evil.example:8765/anilist/callback"]) {
    const result = await f.invoke("/v1/session", {...f.sessionBody, redirect_uri});
    assert.equal(result.status, 400, redirect_uri);
  }
});

test("provider denial returns only a fixed error and the correct local state", async () => {
  const f = await fixture(), session = await f.issue();
  const result = await f.invoke("/v1/callback?" + new URLSearchParams({state: session, error: SECRET}));
  const target = new URL(result.headers.get("Location"));
  assert.equal(target.searchParams.get("error"), "access_denied");
  assert.equal(target.searchParams.get("state"), STATE);
  assert.ok(!target.href.includes(SECRET));
});

test("a spent code is not retried and provider errors are sanitized", async () => {
  const f = await fixture(), session = await f.issue();
  const body = {session, code: "same-code", code_verifier: VERIFIER};
  assert.equal((await f.invoke("/v1/token", body)).status, 200);
  const result = await f.invoke("/v1/token", body);
  assert.equal(result.status, 502);
  assert.ok(!(await result.text()).includes("same-code"));
  assert.equal(f.calls.length, 2);
});

test("foreign browser origins, duplicate state, quota and wrong methods are refused", async () => {
  const f = await fixture(), session = await f.issue();
  assert.equal((await f.invoke("/v1/session", f.sessionBody, {headers: {Origin: "https://evil.example"}})).status, 403);
  assert.equal((await f.invoke("/v1/callback?state=" + session + "&state=" + session + "&code=x")).status, 400);
  assert.equal((await f.invoke("/v1/token")).status, 405);
  f.env.AUTH_RATE_LIMITER.limit = async () => ({success: false});
  assert.equal((await f.invoke("/v1/session", f.sessionBody)).status, 429);
  assert.equal(f.calls.length, 0);
});

test("health and invalid requests do not disclose configuration secrets", async () => {
  const f = await fixture();
  assert.equal((await f.invoke("/health")).status, 200);
  for (const [path, data] of [["/health"], ["/missing"], ["/v1/token", {session: SECRET}],
    ["/v1/session", {...f.sessionBody, client_id: "wrong"}],
    ["/v1/session", {padding: "x".repeat(17000)}]]) {
    const result = await f.invoke(path, data);
    assert.ok(!(await result.text()).includes(SECRET));
  }
  delete f.env.STATE_SECRET;
  assert.equal((await f.invoke("/health")).status, 503);
});
