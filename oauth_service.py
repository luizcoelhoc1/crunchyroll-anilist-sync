"""Login público AniList com segredo mantido no serviço HTTPS, fora do app."""
import base64
import hashlib
import json
import re
import secrets
from urllib.parse import urlencode, urlsplit
import urllib.error
import urllib.request

from oauth_login import OAuthCallback, REDIRECT_URI, open_regular_browser, token_response
from sync_anilist import ApiError, Cancelled, PinnedRedirect, SyncError


def service_url(value):
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or
                url.port not in (None, 443) or url.path not in ("", "/") or url.query or url.fragment or
                not re.fullmatch(r"[a-zA-Z0-9.-]+", url.hostname) or "." not in url.hostname or
                url.hostname.endswith(".") or re.fullmatch(r"[0-9.]+", url.hostname)):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise SyncError("Confira ANILIST_AUTH_SERVICE_URL: use a origem HTTPS do serviço de autorização.") from None
    return "https://" + url.hostname


def service_request(origin, path, body):
    request = urllib.request.Request(origin + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "CrunchyrollAniListSync/1.0"}, method="POST")
    try:
        with urllib.request.build_opener(PinnedRedirect()).open(request, timeout=30) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            message = "O serviço de autorização atingiu o limite de tentativas. Aguarde e tente novamente."
        elif exc.code in (400, 403):
            message = "A autorização expirou ou foi recusada. Clique em Autorizar AniList novamente."
        else:
            message = "O serviço de autorização está temporariamente indisponível. Tente novamente mais tarde."
        raise SyncError(message) from None
    except ApiError:
        raise SyncError("Redirecionamento do serviço de autorização recusado.") from None
    except (OSError, ValueError):
        raise SyncError("Não foi possível acessar o serviço de autorização. Confira a conexão e tente novamente.") from None


def login_via_service(client_id, origin, cancelled=None, redirect_uri=REDIRECT_URI):
    origin = service_url(origin)
    cancelled = cancelled or (lambda: False)
    if not re.fullmatch(r"[0-9]+", str(client_id)):
        raise SyncError("Confira o Client ID do AniList.")
    if cancelled():
        raise Cancelled("Login cancelado.")
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    with OAuthCallback(redirect_uri) as callback:
        result = service_request(origin, "/v1/session", {"client_id": str(client_id), "state": callback.state,
            "code_challenge": challenge, "redirect_uri": redirect_uri})
        session = result.get("session")
        if (result.get("client_id") != str(client_id) or not isinstance(session, str) or len(session) > 4096 or
                not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", session)):
            raise SyncError("O serviço retornou uma configuração de autorização inválida.")
        if cancelled():
            raise Cancelled("Login cancelado.")
        url = "https://anilist.co/api/v2/oauth/authorize?" + urlencode({
            "client_id": str(client_id), "response_type": "code", "redirect_uri": origin + "/v1/callback",
            "state": session})
        open_regular_browser(url)
        code = callback.wait(cancelled)
    if cancelled():
        raise Cancelled("Login cancelado.")
    return token_response(service_request(origin, "/v1/token", {
        "session": session, "code_verifier": verifier, "code": code}))
