"""Sessões locais protegidas pelo usuário atual do Windows (DPAPI)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.cookies import SimpleCookie

from sync_anilist import ApiError, PinnedRedirect, SyncError, jwt_claims


def app_data_dir():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "CrunchyrollAniListSync"


def protect(data, decrypt=False):
    if os.name != "nt":
        raise SyncError("Salvar login com proteção do sistema está disponível no Windows. O acesso continua em memória.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt.CryptUnprotectData
        second = None
    else:
        function = crypt.CryptProtectData
        second = "Crunchyroll AniList Sync"
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
                         ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN, sem LOCAL_MACHINE: somente o usuário atual.
    if not function(ctypes.byref(source), second, None, None, None, 1, ctypes.byref(dest)):
        raise SyncError("O Windows não conseguiu acessar o login protegido. Conecte a conta novamente.")
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        kernel.LocalFree(dest.data)


class SessionStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else app_data_dir() / "sessions.dat"
        self.lock = threading.RLock()
        self.records = {}

    def load(self):
        with self.lock:
            if not self.path.exists():
                return {}
            try:
                data = json.loads(protect(self.path.read_bytes(), decrypt=True))
                if data.get("version") != 1 or not isinstance(data.get("accounts"), dict):
                    raise ValueError()
                self.records = data["accounts"]
                return dict(self.records)
            except (OSError, ValueError, TypeError, AttributeError):
                raise SyncError("Não foi possível ler o login salvo. Conecte as contas novamente.") from None

    def put(self, service, record):
        if service not in ("cr", "al"):
            raise ValueError("Serviço inválido")
        with self.lock:
            records = {**self.records, service: dict(record)}
            data = protect(json.dumps({"version": 1, "accounts": records}).encode("utf-8"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            try:
                temp.write_bytes(data)
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
            self.records = records

    def clear(self):
        with self.lock:
            self.path.unlink(missing_ok=True)
            self.records = {}


class ClientSecretStore:
    """Configuração do aplicativo pessoal, separada dos tokens das contas."""
    def __init__(self, path=None):
        self.store = SessionStore(path or app_data_dir() / "client-credentials.dat")

    def get(self, client_id):
        record = self.store.load().get("al", {})
        if not isinstance(record, dict) or record.get("client_id") != str(client_id):
            return None
        secret = record.get("client_secret")
        return secret if isinstance(secret, str) and secret else None

    def save(self, client_id, secret):
        if not isinstance(secret, str) or not secret.strip() or len(secret) > 4096 or any(c in secret for c in "\r\n\x00"):
            raise SyncError("Informe o Client Secret do aplicativo AniList neste campo.")
        self.store.put("al", {"client_id": str(client_id), "client_secret": secret.strip()})

    def clear(self):
        self.store.clear()


def token_identity(token):
    claims = jwt_claims(token)
    account = (claims.get("scopes", {}).get("cr", {}).get("acc_id")
               or claims.get("etp_user_id"))
    profile = claims.get("profile_id")
    if not isinstance(account, str) or not account or not isinstance(profile, str) or not profile:
        raise SyncError("O acesso do Crunchyroll não identifica conta e perfil. Entre e selecione seu perfil novamente.")
    return account, profile


def exchange_cr(record, grant, refresh_cookie):
    """Cliente público web: cookie persistente, nunca senha ou segredo de outro app."""
    form = {"grant_type": grant, "scope": "offline_access",
            "device_id": record["device_id"], "device_type": "Chrome"}
    if grant == "refresh_token_profile_id":
        form.update(profile_id=record["profile_id"], refresh_token=refresh_cookie)
    headers = {"Authorization": record["client_authorization"],
               "Cookie": "etp_rt=" + refresh_cookie,
               "Content-Type": "application/x-www-form-urlencoded",
               "Accept": "application/json", "User-Agent": record.get("user_agent", "Mozilla/5.0")}
    req = urllib.request.Request("https://www.crunchyroll.com/auth/v1/token",
                                 data=urllib.parse.urlencode(form).encode(), headers=headers, method="POST")
    try:
        with urllib.request.build_opener(PinnedRedirect()).open(req, timeout=30) as response:
            data = json.loads(response.read(1048576))
            if not isinstance(data, dict):
                raise ValueError()
            cookies = SimpleCookie()
            for value in response.headers.get_all("Set-Cookie", []):
                cookies.load(value)
            rotated = cookies["etp_rt"].value if "etp_rt" in cookies else data.get("refresh_token")
    except urllib.error.HTTPError as exc:
        raise ApiError(f"Crunchyroll: não foi possível renovar o acesso (HTTP {exc.code}). "
                       "Use Entrar no Crunchyroll novamente.", exc.code) from None
    except (OSError, ValueError, TypeError):
        raise SyncError("Não foi possível renovar o Crunchyroll. Confira a conexão ou entre novamente.") from None
    token = data.get("access_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise SyncError("O Crunchyroll retornou uma renovação inválida. Entre novamente.")
    if not isinstance(rotated, str) or not rotated:
        rotated = refresh_cookie
    if any(c in rotated for c in "\r\n;"):
        raise SyncError("O Crunchyroll retornou uma sessão inválida.")
    return token, rotated


class CrunchyrollSession:
    """Renova antes de expirar, mantendo a conta e o perfil que foram conferidos."""
    def __init__(self, record, on_change=None):
        self.record = dict(record)
        self.on_change = on_change or (lambda record: None)
        self.lock = threading.RLock()
        if token_identity(self.record["access_token"]) != (self.record["account_id"], self.record["profile_id"]):
            raise SyncError("O login salvo do Crunchyroll não corresponde à conta/perfil. Entre novamente.")
        self.direct = self.record.get("auth_method") == "password"
        refresh_key = "refresh_token" if self.direct else "refresh_cookie"
        for key in (refresh_key, "client_authorization", "device_id", "user_agent") + (("device_type",) if self.direct else ()):
            value = self.record.get(key)
            # User-Agent contém comentários como "(Android 13.0; en-US; ...)".
            # O separador de cookie não é proibido nesse header independente.
            forbidden = "\r\n\x00" if key == "user_agent" else "\r\n\x00;"
            if not isinstance(value, str) or not value or any(c in value for c in forbidden):
                raise SyncError("Login salvo incompleto. Entre no Crunchyroll novamente.")
        if not self.record["client_authorization"].startswith("Basic "):
            raise SyncError("Cliente de autenticação inválido. Entre novamente.")

    def __repr__(self):
        return "<CrunchyrollSession>"

    def access(self, force=False):
        with self.lock:
            expiry = jwt_claims(self.record["access_token"]).get("exp", 0)
            if not force and float(expiry) > time.time() + 60:
                return self.record["access_token"]
            if self.direct:
                from cr_direct_login import refresh_session
                token, cookie = refresh_session(self.record)
            else:
                token, cookie = exchange_cr(self.record, "etp_rt_cookie", self.record["refresh_cookie"])
            claims = jwt_claims(token)
            # Alguns tokens de conta não vêm vinculados ao perfil. Solicita o perfil escolhido.
            account = claims.get("scopes", {}).get("cr", {}).get("acc_id") or claims.get("etp_user_id")
            if account != self.record["account_id"]:
                raise SyncError("A renovação retornou outra conta Crunchyroll. Conecte novamente.")
            if not self.direct and claims.get("profile_id") != self.record["profile_id"]:
                token, cookie = exchange_cr(self.record, "refresh_token_profile_id", cookie)
            if token_identity(token) != (self.record["account_id"], self.record["profile_id"]):
                raise SyncError("A renovação retornou outro perfil Crunchyroll. Conecte novamente.")
            if float(jwt_claims(token).get("exp", 0)) <= time.time() + 5:
                raise SyncError("O Crunchyroll retornou um acesso já expirado. Entre novamente.")
            self.record.update(access_token=token)
            self.record["refresh_token" if self.direct else "refresh_cookie"] = cookie
            self.on_change(dict(self.record))
            return token


def cr_record(token, cookie, client_authorization, user_agent="Mozilla/5.0", device_id=None):
    account, profile = token_identity(token)
    return {"access_token": token, "refresh_cookie": cookie,
            "client_authorization": client_authorization, "device_id": device_id or str(uuid.uuid4()),
            "user_agent": user_agent, "account_id": account, "profile_id": profile}
