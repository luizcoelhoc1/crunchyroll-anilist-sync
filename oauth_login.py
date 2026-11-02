"""Autorização AniList por código no navegador habitual e retorno local."""
from __future__ import annotations

import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import urllib.error
import urllib.request
import webbrowser

from browser_bridge import open_chrome
from sync_anilist import ApiError, Cancelled, PinnedRedirect, SyncError

REDIRECT_URI = "http://127.0.0.1:8765/anilist/callback"
TOKEN_ENDPOINT = "https://anilist.co/api/v2/oauth/token"
SCRIPT = "history.replaceState(null, '', location.pathname);"


def callback_page(message):
    # As mensagens são constantes do aplicativo; nunca inclui código, state ou token.
    return ("<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
            "<title>AniList — Crunchyroll → AniList Sync</title>"
            "<style>body{font:18px system-ui;max-width:680px;margin:80px auto;padding:24px;"
            "background:#101827;color:#e8eef7;line-height:1.6}</style>"
            "<h1>Crunchyroll → AniList</h1><p>" + message + "</p>"
            "<script>" + SCRIPT + "</script></html>")


def token_response(data):
    if not isinstance(data, dict):
        raise SyncError("O AniList retornou uma resposta de acesso inválida.")
    token = data.get("access_token")
    if (not isinstance(token, str) or not token or any(c in token for c in "\r\n\x00") or
            str(data.get("token_type", "bearer")).lower() != "bearer"):
        raise SyncError("O AniList não retornou um acesso válido.")
    try:
        expires = int(data.get("expires_in", 31536000))
        if not 0 < expires <= 366 * 86400:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise SyncError("O AniList retornou uma validade de acesso inválida.") from None
    return {"access_token": token, "expires_at": time.time() + expires}


def exchange_code(client_id, client_secret, code, redirect_uri):
    # A troca é feita pelo processo local. O segredo não vai à URL nem ao navegador.
    body = {"grant_type": "authorization_code", "client_id": str(client_id),
            "client_secret": client_secret, "redirect_uri": redirect_uri, "code": code}
    request = urllib.request.Request(TOKEN_ENDPOINT, data=json.dumps(body).encode("utf-8"),
                                    headers={"Content-Type": "application/json", "Accept": "application/json",
                                             "User-Agent": "CrunchyrollAniListSync/1.0"},
                                    method="POST")
    try:
        with urllib.request.build_opener(PinnedRedirect()).open(request, timeout=30) as response:
            data = json.loads(response.read(1048576))
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read(8192)).get("error")
        except (ValueError, AttributeError, OSError):
            error = None
        if error == "invalid_client":
            message = "Confira ANILIST_CLIENT_ID e ANILIST_CLIENT_SECRET no .env ou em Configurar AniList."
        elif error == "invalid_grant":
            message = "O código AniList expirou ou já foi utilizado. Clique em Autorizar AniList novamente."
        elif error == "unsupported_grant_type":
            message = "O AniList recusou a troca por código. Tente novamente mais tarde."
        elif exc.code == 403:
            message = "O AniList recusou a conexão do aplicativo ao trocar o código (HTTP 403). " \
                      "O retorno no navegador foi recebido, mas o login ainda não foi concluído."
        else:
            message = f"AniList: não foi possível concluir a autorização (HTTP {exc.code})."
        raise SyncError(message) from None
    except ApiError:
        raise SyncError("Redirecionamento na troca AniList recusado. Confira a conexão e tente novamente.") from None
    except (OSError, ValueError):
        raise SyncError("Não foi possível concluir a autorização AniList. Confira a conexão e tente novamente.") from None
    return token_response(data)


def open_regular_browser(url):
    # Sem user-data-dir: o próprio Chrome escolhe o perfil/janela habitual.
    try:
        open_chrome(url)
    except (SyncError, OSError):
        if not webbrowser.open(url, new=2):
            raise SyncError("Não foi possível abrir o navegador habitual. Confira o navegador padrão.") from None


class OAuthCallback:
    def __init__(self, redirect_uri=REDIRECT_URI, ttl=600):
        target = urlsplit(redirect_uri)
        if (target.scheme != "http" or target.hostname != "127.0.0.1" or
                target.username or target.password or not target.port or
                target.path != "/anilist/callback" or target.query or target.fragment):
            raise SyncError("Configure o retorno local do AniList em auth_config.json: " + REDIRECT_URI)
        self.redirect_uri = redirect_uri
        self.origin = f"http://127.0.0.1:{target.port}"
        self.state = secrets.token_urlsafe(32)
        self.deadline = time.monotonic() + ttl
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.code = None
        self.error = None
        self.closed = False
        callback = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Não registrar query strings, códigos ou URLs de autorização.

            def reply(self, status, message):
                data = callback_page(message).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
                self.send_header("Content-Security-Policy",
                    f"default-src 'none'; script-src 'sha256-{script_hash}'; "
                    "style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.connection.settimeout(5)
                try:
                    request_url = urlsplit(self.path)
                    if (self.headers.get("Host") != target.netloc or
                            request_url.path != target.path or request_url.scheme or request_url.netloc or
                            callback.closed or time.monotonic() >= callback.deadline):
                        return self.reply(403, "Retorno recusado ou expirado. Inicie o login pelo sincronizador.")
                    if len(self.path) > 32768:
                        return self.reply(400, "Retorno inválido. Inicie o login pelo sincronizador.")
                    if not request_url.query:
                        return self.reply(200, "Inicie o login pelo sincronizador.")
                    values = parse_qs(request_url.query, keep_blank_values=True)
                    states = values.get("state", [])
                    if (len(states) != 1 or not states[0].isascii() or
                            not hmac.compare_digest(states[0], callback.state)):
                        return self.reply(403, "Retorno não reconhecido. Inicie o login pelo sincronizador.")
                    codes = values.get("code", [])
                    denied = "error" in values
                    if (not denied and (len(codes) != 1 or not codes[0] or
                                        any(c in codes[0] for c in "\r\n\x00"))):
                        return self.reply(400, "Código inválido. Inicie o login pelo sincronizador.")
                    with callback.lock:
                        if callback.done.is_set():
                            return self.reply(409, "Esse retorno já foi recebido. Volte ao sincronizador.")
                        if denied:
                            callback.error = SyncError("A autorização do AniList foi recusada ou cancelada.")
                            self.reply(400, "Autorização cancelada. Volte ao sincronizador para tentar novamente.")
                        else:
                            callback.code = codes[0]
                            self.reply(200, "Código de autorização recebido. O aplicativo ainda precisa validar "
                                            "o acesso no AniList. Volte ao sincronizador para conferir o resultado; "
                                            "esta página não confirma que o login foi concluído.")
                        # Responde antes de liberar quem vai fechar o servidor.
                        callback.done.set()
                except (OSError, ValueError):
                    self.reply(400, "Retorno inválido. Inicie o login pelo sincronizador.")

            def do_POST(self):
                self.reply(405, "Este retorno aceita somente a navegação de autorização do AniList.")

        class Server(ThreadingHTTPServer):
            allow_reuse_address = False
            daemon_threads = True

        try:
            self.server = Server(("127.0.0.1", target.port), Handler)
        except OSError:
            raise SyncError(f"A porta local {target.port} está ocupada. Feche outro login do sincronizador e tente novamente.") from None
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .1}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def wait(self, cancelled=None):
        cancelled = cancelled or (lambda: False)
        while True:
            if cancelled():
                raise Cancelled("Login cancelado.")
            if self.done.wait(.1):
                if self.error:
                    raise self.error
                return self.code
            if time.monotonic() >= self.deadline:
                raise SyncError("O prazo do login AniList terminou. Clique em Autorizar AniList para tentar novamente.")

    def __exit__(self, *args):
        self.closed = True
        self.server.shutdown()
        self.server.server_close()


def login_anilist(client_id, redirect_uri=REDIRECT_URI, cancelled=None, *, client_secret=None):
    if not re.fullmatch(r"[0-9]+", str(client_id)):
        raise SyncError("Configure o Client ID do aplicativo AniList em auth_config.json.")
    if (not isinstance(client_secret, str) or not client_secret.strip() or
            len(client_secret) > 4096 or any(c in client_secret for c in "\r\n\x00")):
        raise SyncError("Configure o Client Secret do aplicativo em Configurar AniList.")
    with OAuthCallback(redirect_uri) as callback:
        if cancelled and cancelled():
            raise Cancelled("Login cancelado.")
        url = "https://anilist.co/api/v2/oauth/authorize?" + urlencode({
            "client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
            "state": callback.state})
        open_regular_browser(url)
        code = callback.wait(cancelled)
    if cancelled and cancelled():
        raise Cancelled("Login cancelado.")
    return exchange_code(client_id, client_secret.strip(), code, redirect_uri)
