"""Login nos próprios sites, em navegador isolado, sem extensão/dependências extras.

CDP é aberto apenas em loopback e em um perfil temporário criado pelo app.
Nunca conecta ao navegador pessoal nem lê bancos de cookies/senhas.
"""
from __future__ import annotations

import base64
from collections import deque
import hashlib
from http.cookies import CookieError, SimpleCookie
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from browser_bridge import chrome_path
from session_store import cr_record, token_identity
from sync_anilist import Cancelled, SyncError, jwt_claims, parse_fetch

PUBLIC_CR_CLIENT = "Basic " + base64.b64encode(b"noaihdevm_6iyg0a8l0q:").decode()
CR_LOGIN_URL = "https://www.crunchyroll.com/login"
CR_HISTORY_URL = "https://www.crunchyroll.com/history"


def browser_path(preferred="auto"):
    if preferred not in ("auto", "edge"):
        raise SyncError("Navegador de login inválido.")
    if preferred == "auto":
        try:
            return chrome_path()
        except SyncError:
            pass
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            path = Path(base) / "Microsoft/Edge/Application/msedge.exe"
            if path.is_file():
                return str(path)
    names = ("microsoft-edge", "msedge") if preferred == "edge" else (
        "microsoft-edge", "msedge", "chromium", "chromium-browser")
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    if preferred == "edge":
        raise SyncError("O Microsoft Edge não foi encontrado. Use Entrar no Crunchyroll para tentar com Chrome.")
    raise SyncError("Instale Chrome ou Edge para entrar sem extensão.")


class DevTools:
    """WebSocket/CDP pequeno, com frames fragmentados, ping e limites de tamanho."""
    def __init__(self, port, path, timeout=5, cancelled=None):
        if not path.startswith("/devtools/browser/") or any(c in path for c in "\r\n "):
            raise SyncError("Endereço do navegador inválido.")
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.cancelled = cancelled or (lambda: False)
        self.buffer = bytearray()
        self.fragments = bytearray()
        self.fragment_opcode = None
        self.events = deque(maxlen=2048)
        self.sequence = 0
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        request = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                   f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   "Sec-WebSocket-Version: 13\r\n\r\n")
        try:
            self.socket.sendall(request.encode())
            deadline = time.monotonic() + timeout
            while b"\r\n\r\n" not in self.buffer:
                if self.cancelled():
                    raise Cancelled("Conexão com o Chrome cancelada.")
                if time.monotonic() >= deadline:
                    raise SyncError("O Chrome não autorizou a conexão a tempo. Confira a permissão na janela do navegador.")
                self.socket.settimeout(min(.25, max(.001, deadline - time.monotonic())))
                try:
                    chunk = self.socket.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    raise SyncError("Não foi possível conectar à janela de login.")
                self.buffer.extend(chunk)
                if len(self.buffer) > 65536:
                    raise SyncError("Resposta inesperada do navegador.")
            header, remainder = bytes(self.buffer).split(b"\r\n\r\n", 1)
            self.buffer = bytearray(remainder)
            lines = header.decode("latin1").split("\r\n")
            headers = {key.lower(): value.strip() for key, value in
                       (line.split(":", 1) for line in lines[1:] if ":" in line)}
            expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if " 101 " not in lines[0] or headers.get("sec-websocket-accept") != expected:
                raise SyncError("Não foi possível conectar à janela de login.")
        except Exception:
            self.socket.close()
            raise

    def send(self, payload, opcode=1):
        raw = payload.encode() if isinstance(payload, str) else payload
        mask = secrets.token_bytes(4)
        length = len(raw)
        head = bytes([0x80 | opcode])
        if length < 126:
            head += bytes([0x80 | length])
        elif length <= 65535:
            head += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", length)
        self.socket.sendall(head + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(raw)))

    def receive(self, timeout=.25):
        deadline = time.monotonic() + timeout
        while True:
            if self.cancelled():
                raise Cancelled("Conexão com o Chrome cancelada.")
            if len(self.buffer) >= 2:
                first, second = self.buffer[:2]
                size, offset = second & 127, 2
                if size == 126 and len(self.buffer) >= 4:
                    size, offset = struct.unpack("!H", self.buffer[2:4])[0], 4
                elif size == 127 and len(self.buffer) >= 10:
                    size, offset = struct.unpack("!Q", self.buffer[2:10])[0], 10
                elif size >= 126:
                    size = None
                if size is not None:
                    if size > 16 * 1024 * 1024 or second & 128:
                        raise SyncError("Resposta inesperada do navegador.")
                    if len(self.buffer) >= offset + size:
                        raw = bytes(self.buffer[offset:offset + size])
                        del self.buffer[:offset + size]
                        opcode = first & 15
                        if opcode == 8:
                            raise SyncError("A janela de login foi fechada. Tente entrar novamente.")
                        if opcode == 9:
                            self.send(raw, opcode=10)
                            continue
                        if opcode == 10:
                            continue
                        if opcode == 1:
                            self.fragments = bytearray(raw)
                            self.fragment_opcode = 1
                        elif opcode == 0 and self.fragment_opcode == 1:
                            self.fragments.extend(raw)
                        else:
                            raise SyncError("Resposta inesperada do navegador.")
                        if len(self.fragments) > 16 * 1024 * 1024:
                            raise SyncError("Resposta muito grande do navegador.")
                        if first & 128:
                            value = json.loads(self.fragments)
                            self.fragments.clear()
                            self.fragment_opcode = None
                            return value
                        continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.socket.settimeout(remaining)
            try:
                chunk = self.socket.recv(65536)
            except socket.timeout:
                return None
            if not chunk:
                raise SyncError("A janela de login foi fechada. Tente entrar novamente.")
            self.buffer.extend(chunk)

    def command(self, method, params=None, session=None, timeout=10):
        self.sequence += 1
        number = self.sequence
        payload = {"id": number, "method": method, "params": params or {}}
        if session:
            payload["sessionId"] = session
        self.send(json.dumps(payload))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive(min(.25, max(.001, deadline - time.monotonic())))
            if message is None:
                continue
            if message.get("id") == number:
                if "error" in message:
                    # Não inclui respostas CDP, que podem conter dados de sessão.
                    raise SyncError("O navegador não conseguiu concluir a etapa de login.")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)
        raise SyncError("O navegador demorou para responder. Tente entrar novamente.")

    def event(self):
        return self.events.popleft() if self.events else self.receive()


class LoginBrowser:
    def __init__(self, cancelled=None, headless=False, preferred_browser="auto"):
        self.cancelled = cancelled or (lambda: False)
        self.headless = headless
        self.preferred_browser = preferred_browser
        self.temp = None
        self.process = None
        self.cdp = None
        self.session = None

    def check(self):
        if self.cancelled():
            raise Cancelled("Login cancelado.")
        if self.process and self.process.poll() is not None:
            raise SyncError("A janela de login foi fechada. Tente entrar novamente.")

    def __enter__(self):
        executable = browser_path(self.preferred_browser)
        self.temp = tempfile.TemporaryDirectory(prefix="cral-login-", ignore_cleanup_errors=True)
        folder = Path(self.temp.name)
        # Evita oferecer salvar senhas nesse perfil descartável.
        (folder / "Default").mkdir()
        (folder / "Default/Preferences").write_text(json.dumps({
            "credentials_enable_service": False, "profile": {"password_manager_enabled": False}}))
        args = [executable, "--user-data-dir=" + str(folder), "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check",
                "--disable-background-mode", "--disable-sync", "--new-window", "--start-maximized", "about:blank"]
        if self.headless:
            args.insert(1, "--headless=new")
        try:
            self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                self.check()
                try:
                    port, path, *_ = (folder / "DevToolsActivePort").read_text().splitlines()
                    self.cdp = DevTools(int(port), path)
                    break
                except (FileNotFoundError, ConnectionError, ValueError):
                    time.sleep(.1)
            if not self.cdp:
                raise SyncError("Não foi possível abrir a janela de login. Confira se o navegador está atualizado.")
            targets = self.cdp.command("Target.getTargets")["targetInfos"]
            target = next(t for t in targets if t["type"] == "page" and t["url"] == "about:blank")
            self.session = self.cdp.command("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})["sessionId"]
            self.command("Page.enable")
            self.command("Network.enable")
            return self
        except Exception:
            self.close()
            raise

    def command(self, method, params=None):
        return self.cdp.command(method, params, session=self.session)

    def navigate(self, url):
        self.command("Page.navigate", {"url": url})

    def events(self, ttl=600):
        deadline = time.monotonic() + ttl
        while time.monotonic() < deadline:
            self.check()
            event = self.cdp.event()
            if (event and event.get("method") == "Target.detachedFromTarget" and
                    event.get("params", {}).get("sessionId") == self.session):
                raise SyncError("A janela de login foi fechada. Tente entrar novamente.")
            if event and event.get("sessionId") == self.session:
                yield event
        raise SyncError("O prazo do login terminou. Clique em Entrar para tentar novamente.")

    def close(self):
        if self.cdp:
            try:
                self.cdp.command("Browser.close", timeout=2)
            except (SyncError, OSError, ValueError):
                pass
            self.cdp.socket.close()
        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()  # Apenas a instância com perfil temporário criada aqui.
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        if self.temp:
            self.temp.cleanup()

    def __exit__(self, *args):
        self.close()


def history_request(url):
    p = urlsplit(url)
    return (p.scheme == "https" and p.netloc == "www.crunchyroll.com" and
            re.fullmatch(r"/content/v2/[^/]+/watch-history", p.path) is not None)


def cr_record_from_fetch(credential):
    """A extensão existente já entrega Cookie; aproveita só o necessário à renovação."""
    try:
        _, headers = parse_fetch(credential, "cr")
        cookies = SimpleCookie()
        cookies.load(headers.get("cookie", ""))
        if "etp_rt" not in cookies:
            return None
        record = cr_record(headers["authorization"].removeprefix("Bearer "),
                           cookies["etp_rt"].value, PUBLIC_CR_CLIENT,
                           headers.get("user-agent", "Mozilla/5.0"),
                           cookies["device_id"].value if "device_id" in cookies else None)
        # Valida os campos sem renovar nem consultar a rede.
        from session_store import CrunchyrollSession
        CrunchyrollSession(record)
        return record
    except (CookieError, SyncError, KeyError, ValueError, TypeError):
        return None


def recaptcha_frame(url):
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and
            parsed.netloc in ("www.google.com", "www.recaptcha.net", "recaptcha.net") and
            re.fullmatch(r"/recaptcha/(?:api2|enterprise)/(?:anchor|bframe)", parsed.path) is not None)


def login_crunchyroll(cancelled=None, on_status=None, use_existing=False, preferred_browser="auto"):
    notify = on_status or (lambda message: None)
    if use_existing:
        from chrome_profile import CurrentChrome
        factory = CurrentChrome
        notify("Conectando ao seu perfil do Chrome. Permita a conexão se o navegador pedir.")
    else:
        factory = LoginBrowser
    options = {"preferred_browser": preferred_browser} if not use_existing and preferred_browser != "auto" else {}
    with factory(cancelled, **options) as browser:
        # Começa pelo login mesmo no perfil normal, caso a conta do site esteja desconectada.
        notify("Entre no Crunchyroll na janela aberta e selecione seu perfil. O histórico abrirá depois do login.")
        browser.navigate(CR_LOGIN_URL)
        requests, extras, successful = {}, {}, set()
        client = PUBLIC_CR_CLIENT
        top_url, top_frame = CR_LOGIN_URL, None
        profile_seen, history_opened, login_retried = False, False, False
        captcha_notified = False
        cloudflare_notified = False

        def open_history_when_ready():
            nonlocal history_opened
            location = urlsplit(top_url)
            if (profile_seen and not history_opened and location.scheme == "https" and
                    location.netloc == "www.crunchyroll.com" and
                    not location.path.rstrip("/").endswith(("/login", "/callback")) and
                    not location.path.startswith("/cdn-cgi/")):
                history_opened = True
                notify("Perfil ativo detectado. Abrindo o histórico do Crunchyroll para conferir o acesso…")
                browser.navigate(CR_HISTORY_URL)

        for event in browser.events():
            params = event.get("params", {})
            request_id = params.get("requestId")
            if event["method"] == "Page.frameNavigated":
                frame = params.get("frame", {})
                if not frame.get("parentId"):
                    top_url, top_frame = frame.get("url", ""), frame.get("id")
                    if urlsplit(top_url).path.rstrip("/").endswith("/history"):
                        history_opened = True
                    open_history_when_ready()
                continue
            if event["method"] == "Page.navigatedWithinDocument":
                if not top_frame or params.get("frameId") == top_frame:
                    top_url = params.get("url", "")
                    open_history_when_ready()
                continue
            if event["method"] == "Network.requestWillBeSent":
                request = params.get("request", {})
                url = request.get("url", "")
                if not captcha_notified and recaptcha_frame(url):
                    captcha_notified = True
                    notify("O site carregou uma verificação reCAPTCHA. Conclua na janela do navegador. "
                           "Se ela se repetir, clique em Interromper e tente com outro navegador; "
                           "a opção Tentar Crunchyroll com Edge fica na tela de login.")
                parsed = urlsplit(url)
                if (parsed.scheme == "https" and parsed.netloc == "www.crunchyroll.com" and
                        parsed.path.startswith(("/accounts/", "/content/", "/auth/v1/token"))):
                    requests[request_id] = (url, request.get("headers", {}))
                if history_request(url):
                    history_opened = True
            elif event["method"] == "Network.requestWillBeSentExtraInfo":
                extras[request_id] = params.get("headers", {})
            elif event["method"] == "Network.responseReceived":
                response = params.get("response", {})
                response_url = urlsplit(response.get("url", ""))
                response_headers = {k.lower(): str(v).lower() for k, v in response.get("headers", {}).items()}
                if (response_url.scheme == "https" and
                        response_url.netloc in ("www.crunchyroll.com", "sso.crunchyroll.com") and
                        response_headers.get("cf-mitigated") == "challenge"):
                    successful.discard(request_id)
                    if not cloudflare_notified:
                        cloudflare_notified = True
                        notify("A Cloudflare está verificando o navegador; o login ainda não terminou. "
                               "Conclua a verificação na janela. Se ela continuar repetindo, interrompa "
                               "e confira se o login funciona no seu navegador habitual.")
                    continue
                if history_request(response.get("url", "")) and response.get("status") == 401:
                    if login_retried:
                        raise SyncError("O Crunchyroll ainda não aceitou o login. Confira a entrada na conta "
                                        "e a seleção do perfil na janela do site e tente novamente.")
                    login_retried = True
                    profile_seen, history_opened = False, False
                    requests.clear()
                    extras.clear()
                    successful.clear()
                    top_url = CR_LOGIN_URL
                    notify("O histórico pediu autenticação. Faça login e selecione o perfil na janela do Crunchyroll.")
                    browser.navigate(CR_LOGIN_URL)
                    continue
                if history_request(response.get("url", "")) and 200 <= response.get("status", 0) < 300:
                    successful.add(request_id)
            else:
                continue
            # ExtraInfo pode chegar antes ou depois de requestWillBeSent.
            for rid, (url, headers) in requests.items():
                clean = {k.lower(): str(v) for k, v in {**headers, **extras.get(rid, {})}.items()}
                auth = clean.get("authorization", "")
                if url == "https://www.crunchyroll.com/auth/v1/token" and auth.startswith("Basic "):
                    client = auth
                if not profile_seen and auth.startswith("Bearer "):
                    token = auth.removeprefix("Bearer ")
                    valid_profile = False
                    try:
                        token_identity(token)
                        valid_profile = float(jwt_claims(token).get("exp", 0)) > time.time() + 5
                    except (SyncError, TypeError, ValueError, AttributeError):
                        pass  # Tokens anônimos/de conta não escolhem um perfil pelo usuário.
                    if valid_profile:
                        profile_seen = True
                        open_history_when_ready()
                if rid not in successful or not history_request(url) or not auth.startswith("Bearer "):
                    continue
                cookies = browser.command("Network.getCookies", {"urls": ["https://www.crunchyroll.com/"]})["cookies"]
                cookie = next((c["value"] for c in cookies if c["name"] == "etp_rt" and
                               c.get("domain", "").lstrip(".") in ("crunchyroll.com", "www.crunchyroll.com")), None)
                if not cookie:
                    continue
                device_id = next((c["value"] for c in cookies if c["name"] == "device_id" and
                                  c.get("domain", "").lstrip(".") in ("crunchyroll.com", "www.crunchyroll.com")), None)
                return cr_record(auth.removeprefix("Bearer "), cookie, client,
                                 clean.get("user-agent", "Mozilla/5.0"), device_id)
            # Não conserva headers de navegação por todo o prazo do login.
            if len(extras) > 256:
                extras = {rid: headers for rid, headers in extras.items() if rid in requests}
        raise SyncError("O login Crunchyroll terminou sem confirmar o acesso ao histórico. Tente novamente.")
