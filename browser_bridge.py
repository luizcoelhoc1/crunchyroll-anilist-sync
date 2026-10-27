"""Ponte local e temporaria entre a extensao Chrome e a janela Python."""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit

from sync_anilist import AniList, Crunchyroll, SyncError, parse_fetch

PROTOCOL = "cral-local-bridge-v1"
PAGE = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="cral-bridge" content="1"><title>Conectar Chrome ao sincronizador</title>
<style>body{font:17px system-ui;background:#101827;color:#e8eef7;max-width:760px;
margin:60px auto;padding:28px;line-height:1.65}h1{font-size:30px}
.box{background:#1d2b40;padding:22px;border-radius:16px}code{color:#9bdaff}
.small{color:#bbc9dc;font-size:14px}</style>
<h1>Crunchyroll → AniList</h1><div class="box">
<strong id="status">Aguardando a extensão local do Chrome…</strong>
<p id="details">Se esta é a primeira vez: abra <code>chrome://extensions</code>,
ative <b>Modo do desenvolvedor</b>, clique em <b>Carregar sem compactação</b>
e selecione a pasta <b>extensao_chrome</b> que veio no ZIP.
Depois recarregue esta página. A conexão expira em 3 minutos;
se necessário, clique novamente em Conectar pelo Chrome no programa.</p>
<p id="services">AniList: aguardando · Crunchyroll: aguardando</p></div>
<p>A extensão abre duas abas de apoio em segundo plano. Se algum site pedir,
entre na sua conta e selecione no Crunchyroll o perfil cujo histórico deseja usar.</p>
<p class="small">Os acessos são entregues somente ao programa neste computador.
A conexão não altera sua lista. Depois volte ao programa e gere a prévia.</p></html>"""


def credential_from_payload(payload):
    if not isinstance(payload, dict) or payload.get("service") not in ("cr", "al"):
        raise SyncError("Servico de acesso invalido.")
    service = payload["service"]
    url, headers = payload.get("url"), payload.get("headers")
    if not isinstance(url, str) or not isinstance(headers, dict):
        raise SyncError("Formato de acesso invalido.")
    p = urlsplit(url)
    expected = "www.crunchyroll.com" if service == "cr" else "anilist.co"
    if p.scheme != "https" or p.netloc != expected or p.fragment:
        raise SyncError("Origem de acesso invalida.")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise SyncError("Headers invalidos.")
    copied = "fetch(" + json.dumps(url) + "," + json.dumps({"headers": headers}) + ")"
    clean_url, clean_headers = parse_fetch(copied, service)
    # Confere os campos necessarios sem consultar a rede ou salvar credenciais.
    value = "fetch(" + json.dumps(clean_url) + "," + json.dumps({"headers": clean_headers}) + ")"
    if service == "cr":
        Crunchyroll(value, profile="")
    else:
        AniList(value)
    return service, value


class LocalBridge:
    """So escuta em loopback. Acesso autenticado por segredo aleatorio por clique."""
    def __init__(self, on_access, ttl=180):
        self.on_access = on_access
        self.key = secrets.token_hex(32)
        self.deadline = time.monotonic() + ttl
        self.received = set()
        self.lock = threading.Lock()
        self.closed = False
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Nao registrar URLs, headers ou corpo.

            def reply(self, code, payload, html=False):
                body = payload.encode("utf-8") if html else json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def valid_host(self):
                return self.headers.get("Host") == f"127.0.0.1:{bridge.port}"

            def authorized(self):
                origin = self.headers.get("Origin", "")
                return (self.valid_host() and not bridge.closed and not bridge.expired
                        and (not origin or re.fullmatch(r"chrome-extension://[a-p]{32}", origin))
                        and hmac.compare_digest(self.headers.get("Authorization", ""),
                                                "Bearer " + bridge.key))

            def do_GET(self):
                self.connection.settimeout(5)
                if not self.valid_host():
                    return self.reply(403, {"error": "host"})
                if self.path == "/conectar":
                    return self.reply(200, PAGE, html=True)
                if self.path == "/bridge/ping" and self.authorized():
                    return self.reply(200, {"protocol": PROTOCOL, "received": sorted(bridge.received)})
                self.reply(403, {"error": "acesso"})

            def do_POST(self):
                self.connection.settimeout(5)
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    # Consome corpos pequenos antes de responder, para evitar RST no Windows.
                    raw = self.rfile.read(min(length, 65537)) if length > 0 else b""
                    if self.path != "/bridge/access" or not self.authorized():
                        return self.reply(403, {"error": "acesso"})
                    if not 0 < length <= 65536:
                        return self.reply(413, {"error": "tamanho"})
                    if self.headers.get_content_type() != "application/json":
                        return self.reply(415, {"error": "formato"})
                    if len(raw) != length:
                        return self.reply(400, {"error": "incompleto"})
                    service, value = credential_from_payload(json.loads(raw))
                except (ValueError, TypeError, SyncError, OSError):
                    return self.reply(400, {"error": "acesso_invalido"})
                with bridge.lock:
                    fresh = service not in bridge.received
                    if fresh:
                        bridge.received.add(service)
                self.reply(200, {"accepted": service})
                if fresh:
                    bridge.on_access(service, value)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = None

    @property
    def expired(self):
        return time.monotonic() >= self.deadline

    @property
    def url(self):
        # O segredo fica no fragmento: nao e enviado no GET nem em Referer.
        return f"http://127.0.0.1:{self.port}/conectar#{self.key}"

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .1}, daemon=True)
        self.thread.start()
        return self.url

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.thread:
            self.server.shutdown()
        self.server.server_close()
        self.key = ""


def chrome_path():
    if os.name == "nt":
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,
                         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                         0, winreg.KEY_READ | view) as key:
                        path = winreg.QueryValue(key, None)
                    if Path(path).is_file():
                        return path
                except OSError:
                    pass
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                path = Path(base) / "Google/Chrome/Application/chrome.exe"
                if path.is_file():
                    return str(path)
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise SyncError("Chrome nao localizado. Abra o Chrome e use o endereco de conexao mostrado no programa.")


def open_chrome(url):
    # Abre a pagina de conexao; nao encerra nem reinicia o Chrome existente.
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen([chrome_path(), "--new-tab", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags)
