"""Conexão consentida ao Chrome normal; só cria/controla a aba de login do app."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlsplit

from browser_bridge import open_chrome
from browser_login import DevTools, LoginBrowser
from sync_anilist import Cancelled, SyncError

SETUP_URL = "chrome://inspect/#remote-debugging"


class ChromeSetupRequired(SyncError):
    pass


def user_data_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise ChromeSetupRequired("Não foi possível localizar o perfil normal do Chrome.")
        return Path(base) / "Google/Chrome/User Data"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    return Path.home() / ".config/google-chrome"


def last_profile(folder):
    """Lê somente a seleção de perfil; não abre cookies, senhas ou dados das páginas."""
    try:
        state = json.loads((folder / "Local State").read_text(encoding="utf-8-sig"))
        profile = state.get("profile", {}).get("last_used", "Default")
    except FileNotFoundError:
        profile = "Default"
    except (OSError, ValueError, AttributeError, TypeError):
        raise ChromeSetupRequired("Não foi possível identificar o último perfil do Chrome. Abra o perfil desejado e tente novamente.") from None
    if not isinstance(profile, str) or not re.fullmatch(r"Default|Profile [0-9]+", profile):
        raise ChromeSetupRequired("Abra um perfil normal do Chrome e tente novamente.")
    return profile


def open_connection_settings():
    open_chrome(SETUP_URL, profile_directory=last_profile(user_data_dir()))


class CurrentChrome(LoginBrowser):
    """Usa o recurso de conexão com permissão do Chrome 144+, sem reiniciar o navegador."""
    def __init__(self, cancelled=None, folder=None):
        super().__init__(cancelled=cancelled)
        self.folder = Path(folder) if folder is not None else user_data_dir()
        self.target_id = None
        self.marker = "about:blank#cral-login-" + secrets.token_hex(16)

    def __enter__(self):
        profile = last_profile(self.folder)
        try:
            descriptor = (self.folder / "DevToolsActivePort").read_text(encoding="ascii")
            if len(descriptor) > 4096:
                raise ValueError()
            port_text, path, *_ = descriptor.strip().splitlines()
            port = int(port_text)
            if not 0 < port < 65536 or not path.startswith("/devtools/browser/"):
                raise ValueError()
        except (OSError, ValueError, UnicodeError):
            raise ChromeSetupRequired("Abra seu perfil do Chrome e ative a conexão em " + SETUP_URL + ".") from None
        try:
            self.cdp = DevTools(port, path, timeout=60, cancelled=self.cancelled)
            # O launcher escolhe explicitamente o último perfil; o marcador identifica só a aba criada aqui.
            open_chrome(self.marker, profile_directory=profile)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                self.check()
                targets = self.cdp.command("Target.getTargets", timeout=60).get("targetInfos", [])
                matches = [target for target in targets if target.get("type") == "page" and target.get("url") == self.marker]
                if len(matches) == 1:
                    self.target_id = matches[0]["targetId"]
                    break
                if len(matches) > 1:
                    raise SyncError("Não foi possível identificar uma única aba de login do sincronizador.")
                time.sleep(.1)
            if self.target_id is None:
                raise ChromeSetupRequired("Não foi possível conectar ao perfil desejado. Confira a permissão e a conexão no Chrome.")
            self.session = self.cdp.command("Target.attachToTarget", {
                "targetId": self.target_id, "flatten": True}, timeout=60)["sessionId"]
            self.command("Page.enable")
            self.command("Network.enable")
            self.command("Page.bringToFront")
            return self
        except Cancelled:
            self.close()
            raise
        except (OSError, SyncError, ValueError, KeyError):
            self.close()
            raise ChromeSetupRequired("O Chrome não permitiu a conexão. Confira " + SETUP_URL +
                                      " e permita a conexão quando o navegador pedir.") from None

    def close(self):
        # Nunca chama Browser.close, encerra processos ou apaga arquivos do navegador pessoal.
        connection, self.cdp = self.cdp, None
        if not connection:
            return
        connection.cancelled = lambda: False  # Permite apenas a limpeza curta da aba própria após cancelar.
        try:
            if self.target_id:
                info = connection.command("Target.getTargetInfo", {"targetId": self.target_id}, timeout=2).get("targetInfo", {})
                url = info.get("url", "")
                parsed = urlsplit(url)
                own_page = url == self.marker or (
                    parsed.scheme == "https" and parsed.netloc in ("www.crunchyroll.com", "sso.crunchyroll.com") and
                    re.fullmatch(r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:history|login|profiles|select-profile)?/?", parsed.path))
                if own_page:
                    connection.command("Target.closeTarget", {"targetId": self.target_id}, timeout=2)
                elif self.session:
                    connection.command("Target.detachFromTarget", {"sessionId": self.session}, timeout=2)
        except (OSError, SyncError, ValueError):
            pass
        finally:
            connection.socket.close()
            self.target_id = None
            self.session = None
