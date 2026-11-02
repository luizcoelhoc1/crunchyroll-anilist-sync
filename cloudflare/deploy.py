"""Publica o Worker Free e envia apenas as chaves AniList pelo stdin do Wrangler."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from app_config import load_anilist_config
from oauth_service import service_url
from sync_anilist import PinnedRedirect, SyncError


def public_config(client_id, origin):
    return {"anilist_client_id": str(client_id),
            "anilist_redirect_uri": "http://127.0.0.1:8765/anilist/callback",
            "anilist_auth_service_url": service_url(origin)}


def deploy(project=PROJECT):
    config = load_anilist_config(project, environ={})
    if not config.client_secret:
        raise RuntimeError("Informe ANILIST_CLIENT_SECRET no .env local antes de publicar o Worker.")
    directory = project / "cloudflare"
    node = shutil.which("node")
    wrangler = directory / "node_modules" / "wrangler" / "bin" / "wrangler.js"
    if not node or not wrangler.is_file():
        raise RuntimeError("Instale Node.js e execute task auth:deploy para instalar o Wrangler.")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ANILIST_")}
    environment.update(WRANGLER_SEND_METRICS="false", WRANGLER_LOG="log")

    def cli(*args, stdin=None):
        result = subprocess.run([node, str(wrangler), *args], cwd=directory, env=environment,
                                input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            # Secret values and CLI input never appear in diagnostics.
            raise RuntimeError("O Wrangler não concluiu a operação " + " ".join(args[:2]) +
                               ". Confira o login com task auth:login e a conta Cloudflare Free.")
        return result.stdout

    who = json.loads(cli("whoami", "--json"))
    if not who.get("loggedIn"):
        raise RuntimeError("Faça login na conta Cloudflare Free com task auth:login.")
    print("Publicando o serviço de autorização no Cloudflare...", flush=True)
    output = cli("deploy")
    matches = re.findall(r"https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev", output)
    if not matches:
        raise RuntimeError("O Wrangler não informou o endereço workers.dev. Confira o subdomínio na conta Cloudflare.")
    origin = service_url(matches[-1])
    existing = json.loads(cli("secret", "list"))
    names = {item["name"] for item in existing}
    values = {"ANILIST_CLIENT_ID": config.client_id, "ANILIST_CLIENT_SECRET": config.client_secret}
    if "STATE_SECRET" not in names:
        values["STATE_SECRET"] = secrets.token_urlsafe(48)
    cli("secret", "bulk", stdin=json.dumps(values))
    request = urllib.request.Request(origin + "/health", headers={"Accept": "application/json",
        "User-Agent": "CrunchyrollAniListSync/1.0"})
    with urllib.request.build_opener(PinnedRedirect()).open(request, timeout=30) as response:
        result = json.loads(response.read(8192))
    if (result.get("service") != "crunchyroll-anilist-auth" or result.get("protocol") != 1 or
            result.get("client_id") != config.client_id):
        raise RuntimeError("O serviço publicado não confirmou a configuração esperada.")
    path = project / "auth_config.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(public_config(config.client_id, origin), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print("Serviço publicado e configurado no app: " + origin, flush=True)
    print("No cadastro do aplicativo AniList, defina o Redirect URL como:\n" + origin + "/v1/callback", flush=True)
    print("Depois execute task compile para publicar o instalador com essa configuração pública.", flush=True)
    return origin


if __name__ == "__main__":
    try:
        deploy()
    except (RuntimeError, SyncError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError):
        print("A publicação não terminou. Confira a conta Free, execute task auth:login e tente "
              "task auth:deploy novamente. Nenhum segredo foi copiado para auth_config.json.", file=sys.stderr)
        sys.exit(1)
