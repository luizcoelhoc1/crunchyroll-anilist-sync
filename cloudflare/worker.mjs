// No tokens, authorization codes or secrets are logged or persisted.
const TOKEN = "https://anilist.co/api/v2/oauth/token";
const TTL = 600;
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", {fatal: true});
const secureHeaders = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
};

class Failure extends Error {
  constructor(status, code) { super(code); this.status = status; }
}

function response(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {status, headers: {
    ...secureHeaders, "Content-Type": "application/json; charset=utf-8", ...extra,
  }});
}

function base64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decode(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Failure(400, "invalid_session");
  return Uint8Array.from(atob(value.replaceAll("-", "+").replaceAll("_", "/")), c => c.charCodeAt(0));
}

async function jsonBody(request) {
  if (!request.headers.get("Content-Type")?.toLowerCase().startsWith("application/json")) {
    throw new Failure(415, "json_required");
  }
  const reader = request.body?.getReader();
  if (!reader) throw new Failure(400, "invalid_request");
  const chunks = [];
  let length = 0;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    length += value.length;
    if (length > 16384) { await reader.cancel(); throw new Failure(413, "request_too_large"); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  try {
    const value = JSON.parse(decoder.decode(bytes));
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
    return value;
  } catch { throw new Failure(400, "invalid_request"); }
}

function localRedirect(value) {
  if (typeof value !== "string" || !/^http:\/\/127\.0\.0\.1:\d{1,5}\/anilist\/callback$/.test(value)) {
    throw new Failure(400, "invalid_redirect");
  }
  const url = new URL(value);
  if (+url.port < 1024 || +url.port > 65535) throw new Failure(400, "invalid_redirect");
  return url.href;
}

async function key(env) {
  if (!/^[0-9]+$/.test(env.ANILIST_CLIENT_ID || "") ||
      typeof env.ANILIST_CLIENT_SECRET !== "string" || !env.ANILIST_CLIENT_SECRET ||
      typeof env.STATE_SECRET !== "string" || env.STATE_SECRET.length < 43) {
    throw new Failure(503, "not_configured");
  }
  return crypto.subtle.importKey("raw", encoder.encode(env.STATE_SECRET),
    {name: "HMAC", hash: "SHA-256"}, false, ["sign", "verify"]);
}

async function sign(payload, signingKey) {
  const body = base64url(encoder.encode(JSON.stringify(payload)));
  return body + "." + base64url(await crypto.subtle.sign("HMAC", signingKey, encoder.encode(body)));
}

async function verify(session, signingKey, origin, clientId, now) {
  if (typeof session !== "string" || session.length > 4096 || session.split(".").length !== 2) {
    throw new Failure(400, "invalid_session");
  }
  const [body, signature] = session.split(".");
  try {
    if (!await crypto.subtle.verify("HMAC", signingKey, decode(signature), encoder.encode(body))) {
      throw new Error();
    }
    const value = JSON.parse(decoder.decode(decode(body)));
    if (value.v !== 1 || value.origin !== origin || value.client_id !== clientId ||
        !Number.isInteger(value.exp) || !Number.isInteger(value.iat) ||
        value.iat > now + 5 || value.exp <= now || value.exp - value.iat !== TTL ||
        !/^[A-Za-z0-9_-]{43}$/.test(value.state) || !/^[A-Za-z0-9_-]{43}$/.test(value.challenge)) {
      throw new Error();
    }
    localRedirect(value.redirect_uri);
    return value;
  } catch { throw new Failure(400, "invalid_or_expired_session"); }
}

function once(url, name) {
  const values = url.searchParams.getAll(name);
  if (values.length !== 1 || !values[0]) throw new Failure(400, "invalid_request");
  return values[0];
}

export function createWorker({fetcher = (url, options) => globalThis.fetch(url, options),
  now = () => Math.floor(Date.now() / 1000)} = {}) {
  return {async fetch(request, env) {
    try {
      const url = new URL(request.url);
      if (url.protocol !== "https:" || url.search.length > 16384) throw new Failure(400, "invalid_request");
      if (url.pathname === "/health" && request.method === "GET") {
        await key(env);
        return response({service: "crunchyroll-anilist-auth", protocol: 1, client_id: env.ANILIST_CLIENT_ID});
      }
      const allowed = {"/v1/session": "POST", "/v1/callback": "GET", "/v1/token": "POST"};
      if (!allowed[url.pathname]) throw new Failure(404, "not_found");
      if (request.method !== allowed[url.pathname]) throw new Failure(405, "method_not_allowed");
      // Browser scripts cannot initiate exchanges. The desktop client has no Origin header.
      if (request.headers.has("Origin")) throw new Failure(403, "origin_not_allowed");
      if (!env.AUTH_RATE_LIMITER) throw new Failure(503, "not_configured");
      const ip = request.headers.get("CF-Connecting-IP") || "unknown";
      if (!(await env.AUTH_RATE_LIMITER.limit({key: ip})).success) throw new Failure(429, "rate_limited");
      const signingKey = await key(env);
      const time = now();
      if (url.pathname === "/v1/session") {
        const body = await jsonBody(request);
        if (body.client_id !== env.ANILIST_CLIENT_ID || !/^[A-Za-z0-9_-]{43}$/.test(body.state || "") ||
            !/^[A-Za-z0-9_-]{43}$/.test(body.code_challenge || "")) throw new Failure(400, "invalid_request");
        const session = await sign({v: 1, iat: time, exp: time + TTL, origin: url.origin,
          client_id: env.ANILIST_CLIENT_ID, state: body.state, challenge: body.code_challenge,
          redirect_uri: localRedirect(body.redirect_uri)}, signingKey);
        return response({session, client_id: env.ANILIST_CLIENT_ID});
      }
      if (url.pathname === "/v1/callback") {
        const payload = await verify(once(url, "state"), signingKey, url.origin, env.ANILIST_CLIENT_ID, time);
        const target = new URL(payload.redirect_uri);
        target.searchParams.set("state", payload.state);
        if (url.searchParams.has("error")) target.searchParams.set("error", "access_denied");
        else {
          const code = once(url, "code");
          if (code.length > 8192 || /[\r\n\0]/.test(code)) throw new Failure(400, "invalid_request");
          target.searchParams.set("code", code);
        }
        return new Response(null, {status: 302, headers: {...secureHeaders, Location: target.href}});
      }
      const body = await jsonBody(request);
      const payload = await verify(body.session, signingKey, url.origin, env.ANILIST_CLIENT_ID, time);
      if (typeof body.code !== "string" || !body.code || body.code.length > 8192 || /[\r\n\0]/.test(body.code) ||
          typeof body.code_verifier !== "string" || !/^[A-Za-z0-9._~-]{43,128}$/.test(body.code_verifier)) {
        throw new Failure(400, "invalid_request");
      }
      const challenge = base64url(await crypto.subtle.digest("SHA-256", encoder.encode(body.code_verifier)));
      // Compare the fixed-size proof without an early-return character comparison.
      let difference = challenge.length ^ payload.challenge.length;
      for (let i = 0; i < challenge.length; i++) difference |= challenge.charCodeAt(i) ^ payload.challenge.charCodeAt(i);
      if (difference) throw new Failure(403, "invalid_proof");
      let upstream, data;
      try {
        // workerd supports manual/follow, not the browser's redirect: "error".
        upstream = await fetcher(TOKEN, {method: "POST", redirect: "manual", signal: AbortSignal.timeout(25000),
          headers: {"Content-Type": "application/json", Accept: "application/json",
            "User-Agent": "CrunchyrollAniListSync/1.0"},
          body: JSON.stringify({grant_type: "authorization_code", client_id: env.ANILIST_CLIENT_ID,
            client_secret: env.ANILIST_CLIENT_SECRET, code: body.code, redirect_uri: url.origin + "/v1/callback"})});
        if (upstream.status >= 300 && upstream.status < 400) throw new Failure(502, "provider_redirect");
        const text = await upstream.text();
        if (text.length > 65536) throw new Failure(502, "provider_response_too_large");
        if (!upstream.ok) {
          let reason = "provider_http_" + upstream.status;
          try {
            const error = JSON.parse(text)?.error;
            if (["invalid_client", "invalid_grant", "unsupported_grant_type"].includes(error)) reason = error;
          } catch { /* Never reflect the provider's response body. */ }
          throw new Failure(502, reason);
        }
        data = JSON.parse(text);
      } catch (error) {
        if (error instanceof Failure) throw error;
        throw new Failure(502, "provider_unreachable");
      }
      if (!data || typeof data !== "object" || typeof data.access_token !== "string" || !data.access_token || data.access_token.length > 16384 ||
          /[\r\n\0]/.test(data.access_token) || String(data.token_type).toLowerCase() !== "bearer" ||
          !Number.isInteger(data.expires_in) || data.expires_in <= 0 || data.expires_in > 366 * 86400) {
        throw new Failure(502, "invalid_token_response");
      }
      return response({access_token: data.access_token, token_type: "Bearer", expires_in: data.expires_in});
    } catch (error) {
      return response({error: error instanceof Failure ? error.message : "service_unavailable"},
        error instanceof Failure ? error.status : 503);
    }
  }};
}

export default createWorker();
