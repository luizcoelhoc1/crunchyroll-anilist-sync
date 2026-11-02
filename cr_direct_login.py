"""Cliente Python próprio para login por senha e refresh token do Crunchyroll.

Protocolo observado em crunchyroll-rs/src/auth/{builder,login}.rs (29/10/2026).
Não importa essa biblioteca. O cliente de plataforma publicado pode ser revogado.
"""
from __future__ import annotations

from http.cookiejar import CookieJar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from sync_anilist import ApiError, Cancelled, PinnedRedirect, SyncError, jwt_claims

ORIGIN = "https://www.crunchyroll.com"
TOKEN_PATH = "/auth/v1/token"
PROFILES_PATH = "/accounts/v1/me/multiprofile"
# Identificação de plataforma publicada em crunchy-labs/artifacts/credentials.json
# (Android TV 3.76.0); não é a senha do usuário. Nenhum download em tempo de login.
CLIENT_AUTHORIZATION = "Basic ZXI5bmdnMmtvNW9oaXJsYTUxaTI6VmwxVDBQbjhRWko2d3o0NnhYRGxIekRGUDV0Wlgxb3E="
USER_AGENT = "Crunchyroll/ANDROIDTV/3.76.0_22366 (Android 13.0; en-US; TCL-S5400AF Build/TP1A.220624.014)"
DEVICE_TYPE = "ANDROIDTV"
MAX_RESPONSE = 1048576


def account_identity(token):
    try:
        claims = jwt_claims(token)
        account = claims.get("scopes", {}).get("cr", {}).get("acc_id") or claims.get("etp_user_id")
        if (not isinstance(account, str) or not re.fullmatch(r"[A-Za-z0-9-]+", account) or
                not time.time() + 5 < float(claims.get("exp", 0)) < float("inf")):
            raise ValueError()
        return account
    except (ValueError, TypeError, AttributeError, SyncError):
        raise SyncError("O Crunchyroll retornou um token sem conta válida ou já expirado.") from None


def token_result(data, previous_refresh=None):
    if not isinstance(data, dict) or str(data.get("token_type", "bearer")).lower() != "bearer":
        raise SyncError("Resposta de autenticação inválida do Crunchyroll.")
    token, refresh = data.get("access_token"), data.get("refresh_token", previous_refresh)
    for value in (token, refresh):
        if (not isinstance(value, str) or not value or len(value) > 32768 or
                any(c in value for c in "\r\n\x00")):
            raise SyncError("O Crunchyroll não retornou os tokens necessários para manter o login.")
    account = account_identity(token)
    if data.get("account_id") not in (None, account):
        raise SyncError("A conta retornada pelo Crunchyroll não corresponde ao token.")
    return token, refresh, account


class DirectClient:
    def __init__(self, record=None, cancelled=None):
        self.cancelled = cancelled or (lambda: False)
        self.device = {key: (record or {}).get(key, default) for key, default in {
            "client_authorization": CLIENT_AUTHORIZATION, "user_agent": USER_AGENT,
            "device_id": str(uuid.uuid4()), "device_type": DEVICE_TYPE}.items()}
        if any(not isinstance(v, str) or not v or len(v) > 4096 or
               any(c in v for c in "\r\n\x00") for v in self.device.values()):
            raise SyncError("Configuração de login Crunchyroll inválida.")
        if not self.device["client_authorization"].startswith("Basic "):
            raise SyncError("Cliente de login Crunchyroll inválido.")
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(PinnedRedirect(), urllib.request.HTTPCookieProcessor(self.cookies))

    def __repr__(self):
        return "<CrunchyrollDirectClient>"

    def check(self):
        if self.cancelled():
            raise Cancelled("Login Crunchyroll cancelado.")

    def request(self, path, form=None, token=None):
        self.check()
        if path not in (TOKEN_PATH, PROFILES_PATH):
            raise SyncError("Destino de autenticação inesperado.")
        headers = {"Accept": "application/json", "User-Agent": self.device["user_agent"]}
        body = None
        if form is not None:
            headers.update({"Authorization": self.device["client_authorization"],
                            "Content-Type": "application/x-www-form-urlencoded"})
            if form.get("grant_type") == "password":
                headers["ETP-Anonymous-ID"] = self.device["device_id"]
            body = urllib.parse.urlencode({**form, "scope": "offline_access",
                "device_id": self.device["device_id"], "device_type": self.device["device_type"]}).encode()
        elif token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(ORIGIN + path, data=body, headers=headers,
                                     method="POST" if form is not None else "GET")
        try:
            with self.opener.open(req, timeout=30) as response:
                if response.headers.get("cf-mitigated") == "challenge":
                    raise ApiError("O Crunchyroll exigiu uma verificação Cloudflare. O login direto não foi concluído.", 403)
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError()
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read(16384)
                error = json.loads(raw).get("error", "")
            except (ValueError, AttributeError, OSError):
                error = ""
            finally:
                exc.close()
            if error in ("invalid_client", "unauthorized_client", "unsupported_grant_type"):
                message = "O Crunchyroll recusou o cliente de login direto. A integração precisa ser atualizada."
            elif status == 429:
                message = "Muitas tentativas no Crunchyroll. Aguarde antes de tentar novamente."
            elif status == 403:
                message = "O Crunchyroll bloqueou o login direto (HTTP 403). Pode ser uma verificação de segurança."
            elif error == "invalid_grant" or status == 401:
                message = ("O Crunchyroll recusou o login. Confira e-mail e senha; pode haver uma confirmação pendente no site."
                           if form and form.get("grant_type") == "password" else
                           "O Crunchyroll recusou a sessão. Entre novamente.")
            else:
                message = f"Não foi possível autenticar no Crunchyroll (HTTP {status})."
            raise ApiError(message, status) from None
        except (OSError, ValueError, TypeError):
            raise SyncError("O Crunchyroll não respondeu com dados válidos. Confira a conexão ou um bloqueio do serviço.") from None
        finally:
            # Não retém a senha no objeto de requisição após a chamada.
            req.data = None
            body = None
        self.check()
        return data


class PendingLogin:
    """Tokens em memória até a escolha explícita do perfil; nunca contém senha."""
    def __init__(self, client, record, profiles):
        self.client, self.record, self.profiles = client, record, profiles

    def __repr__(self):
        return "<CrunchyrollPendingLogin>"

    def clear(self):
        self.record.clear()
        self.profiles.clear()
        self.client.cookies.clear()

    def select(self, profile_id):
        self.client.check()
        profile = next((p for p in self.profiles if p["id"] == profile_id), None)
        if not profile:
            raise SyncError("Selecione um perfil retornado pelo Crunchyroll.")
        record = dict(self.record)
        if jwt_claims(record["access_token"]).get("profile_id") != profile_id:
            if not profile["can_switch"]:
                raise SyncError("Esse perfil exige confirmação no Crunchyroll e não pode ser selecionado por este login.")
            token, refresh, account = token_result(self.client.request(TOKEN_PATH, {
                "grant_type": "refresh_token_profile_id", "profile_id": profile_id,
                "refresh_token": record["refresh_token"]}), record["refresh_token"])
            if account != record["account_id"]:
                raise SyncError("A seleção de perfil retornou outra conta. Entre novamente.")
            record.update(access_token=token, refresh_token=refresh)
        if jwt_claims(record["access_token"]).get("profile_id") != profile_id:
            raise SyncError("O Crunchyroll não confirmou o perfil escolhido.")
        record["profile_id"] = profile_id
        self.client.check()
        return record


def login_with_password(email, password, cancelled=None):
    if not isinstance(email, str) or not email.strip() or len(email) > 320:
        raise SyncError("Informe seu e-mail Crunchyroll.")
    if not isinstance(password, str) or not password or len(password) > 4096:
        raise SyncError("Informe sua senha Crunchyroll.")
    client = DirectClient(cancelled=cancelled)
    form = {"grant_type": "password", "username": email.strip(), "password": password}
    try:
        data = client.request(TOKEN_PATH, form)
    finally:
        form.clear()
        email = password = None
    token, refresh, account = token_result(data)
    data = client.request(PROFILES_PATH, token=token)
    entries = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise SyncError("Não foi possível obter os perfis do Crunchyroll. O login não foi salvo.")
    profiles, ids = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SyncError("O Crunchyroll retornou uma lista de perfis inválida.")
        pid = entry.get("profile_id")
        if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9-]+", pid) or pid in ids:
            raise SyncError("O Crunchyroll retornou uma lista de perfis inválida.")
        ids.add(pid)
        name = entry.get("profile_name")
        profiles.append({"id": pid, "name": name if isinstance(name, str) and name else pid,
                         "can_switch": entry.get("can_switch", True) is True})
    record = {**client.device, "auth_method": "password", "access_token": token,
              "refresh_token": refresh, "account_id": account}
    return PendingLogin(client, record, profiles)


def refresh_session(record):
    client = DirectClient(record)
    token, refresh, account = token_result(client.request(TOKEN_PATH, {
        "grant_type": "refresh_token", "refresh_token": record["refresh_token"]}), record["refresh_token"])
    if account != record["account_id"]:
        raise SyncError("A renovação retornou outra conta Crunchyroll. Entre novamente.")
    if jwt_claims(token).get("profile_id") != record["profile_id"]:
        token, refresh, account = token_result(client.request(TOKEN_PATH, {
            "grant_type": "refresh_token_profile_id", "refresh_token": refresh,
            "profile_id": record["profile_id"]}), refresh)
    return token, refresh
