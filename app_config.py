"""Configuração local AniList: ambiente > .env > JSON público legado."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from oauth_login import REDIRECT_URI
from sync_anilist import SyncError
from app_paths import RESOURCE_ROOT, DATA_ROOT

KEYS = {"ANILIST_CLIENT_ID", "ANILIST_CLIENT_SECRET", "ANILIST_REDIRECT_URI"}


@dataclass(frozen=True)
class AniListConfig:
    client_id: str
    redirect_uri: str
    client_secret: str | None = field(default=None, repr=False)


def read_dotenv(path):
    """Lê só as três chaves do app, sem executar/interpolar o conteúdo."""
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        raise SyncError("Não foi possível ler o arquivo .env na pasta do programa.") from None
    result = {}
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if name not in KEYS:
            continue
        if not separator:
            raise SyncError(f"Confira o formato da linha {number} do .env: use NOME=valor.")
        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].lstrip().startswith("#")):
                raise SyncError(f"Confira as aspas na linha {number} do .env.")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
            if value.startswith("#"):
                value = ""
        if any(c in value for c in "\r\n\x00"):
            raise SyncError(f"Valor inválido na linha {number} do .env.")
        result[name] = value
    return result


def load_anilist_config(root=None, environ=None):
    legacy_root = Path(root) if root is not None else RESOURCE_ROOT
    root = Path(root) if root is not None else DATA_ROOT
    environ = os.environ if environ is None else environ
    legacy_path = legacy_root / "auth_config.json"
    legacy = {}
    if legacy_path.exists():
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8-sig"))
            if not isinstance(legacy, dict):
                raise ValueError()
        except (OSError, ValueError):
            raise SyncError("Confira o formato do arquivo auth_config.json.") from None
    values = {"ANILIST_CLIENT_ID": str(legacy.get("anilist_client_id", "55193")),
              "ANILIST_REDIRECT_URI": legacy.get("anilist_redirect_uri", REDIRECT_URI)}
    values.update(read_dotenv(root / ".env"))
    values.update({key: environ[key] for key in KEYS if key in environ})
    client_id = values["ANILIST_CLIENT_ID"].strip()
    redirect = values["ANILIST_REDIRECT_URI"]
    secret = values.get("ANILIST_CLIENT_SECRET", "").strip() or None
    if not re.fullmatch(r"[0-9]+", client_id):
        raise SyncError("Confira ANILIST_CLIENT_ID no .env ou no ambiente.")
    try:
        target = urlsplit(redirect)
        valid = (target.scheme == "http" and target.hostname == "127.0.0.1" and
                 target.port and not target.username and not target.password and
                 target.path == "/anilist/callback" and not target.query and not target.fragment)
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise SyncError("Confira ANILIST_REDIRECT_URI no .env; use " + REDIRECT_URI)
    if secret and (len(secret) > 4096 or any(c in secret for c in "\r\n\x00")):
        raise SyncError("Confira ANILIST_CLIENT_SECRET no .env ou no ambiente.")
    return AniListConfig(client_id, redirect, secret)
