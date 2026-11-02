"""Publica o código e o MSI sem depender do GitHub CLI ou salvar credenciais."""
import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def git(project, *args, env=None, check=True):
    return subprocess.run(["git", *args], cwd=project, env=env, check=check,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def repository_name(remote):
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                         r"([\w.-]+/[\w.-]+?)(?:\.git)?/?", remote)
    if not match:
        raise RuntimeError("O remoto origin deve apontar para um repositório no github.com.")
    return match[1]


def source_digest(project):
    """Inclui arquivos novos e exclusões; ignora saídas de build e o VERSION gerado."""
    names = git(project, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
    digest = hashlib.sha256()
    for name in sorted(set(names.split("\0")) - {"", "VERSION"}):
        path = project / name
        if not path.is_file():
            continue
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def save_pending(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward authorization to a redirected host.


class GitHub:
    def __init__(self, project):
        self.repository = repository_name(git(project, "remote", "get-url", "origin").stdout.strip())
        self.branch = git(project, "branch", "--show-current").stdout.strip()
        if not self.branch:
            raise RuntimeError("A publicação precisa de uma branch local; HEAD está destacado.")
        self.token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
            result = subprocess.run(["git", "credential", "fill"], cwd=project,
                                    input="protocol=https\nhost=github.com\n\n", env=environment,
                                    capture_output=True, text=True)
            fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            self.token = fields.get("password")
        if not self.token:
            raise RuntimeError("Autentique o Git no GitHub ou defina GH_TOKEN/GITHUB_TOKEN "
                               "com permissão Contents: write. Para build local, use PUBLISH=false.")
        self.base = "https://api.github.com/repos/" + self.repository
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, url, payload=None, content_type="application/json"):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ("api.github.com", "uploads.github.com"):
            raise RuntimeError("Destino inesperado na API de releases do GitHub.")
        data = payload if isinstance(payload, bytes) or payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "crunchyroll-anilist-sync-build", "Authorization": "Bearer " + self.token}
        if data is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with self.opener.open(request, timeout=90) as response:
            return json.load(response)

    def git_environment(self):
        environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        index = int(environment.get("GIT_CONFIG_COUNT", "0"))
        environment["GIT_CONFIG_COUNT"] = str(index + 1)
        environment[f"GIT_CONFIG_KEY_{index}"] = "http.https://github.com/.extraheader"
        credential = base64.b64encode(("x-access-token:" + self.token).encode()).decode("ascii")
        environment[f"GIT_CONFIG_VALUE_{index}"] = "AUTHORIZATION: basic " + credential
        return environment

    def release(self, version):
        try:
            return self.request("GET", self.base + "/releases/tags/v" + version)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def prepare(self, project, version, resume=False):
        repository = self.request("GET", self.base)
        if not repository.get("permissions", {}).get("push"):
            raise RuntimeError("A conta autenticada não tem permissão para publicar neste repositório.")
        if git(project, "ls-files", "-u").stdout:
            raise RuntimeError("Resolva os conflitos de merge antes de compilar uma release.")
        if not resume:
            tag = git(project, "show-ref", "--verify", "--quiet", "refs/tags/v" + version, check=False)
            if tag.returncode == 0 or self.release(version) is not None:
                raise RuntimeError(f"A versão v{version} já existe; nenhuma tag/release será sobrescrita.")
        # Fail before compiling when the remote branch has diverged.
        git(project, "fetch", "--quiet", "origin", self.branch, env=self.git_environment())
        ancestor = git(project, "merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD", check=False)
        if ancestor.returncode:
            raise RuntimeError("A branch remota avançou. Atualize a branch local antes de publicar.")


def check_asset(asset, data):
    expected = "sha256:" + hashlib.sha256(data).hexdigest()
    if (asset.get("state") != "uploaded" or asset.get("size") != len(data)
            or asset.get("digest") != expected):
        raise RuntimeError(f"O anexo {asset.get('name')} não corresponde ao arquivo local; "
                           "a release não será sobrescrita.")


def publish(project, state, pending, github):
    version = state["version"]
    tag = "v" + version
    if state["repository"] != github.repository or state["branch"] != github.branch:
        raise RuntimeError("O repositório/branch mudou desde a compilação pendente.")
    if source_digest(project) != state["source_digest"]:
        raise RuntimeError("O código mudou desde a compilação pendente. Restaure esse código "
                           "antes de retomar a publicação.")
    installer = project / "dist" / f"CrunchyrollAniListSync-{version}-x64.msi"
    data = installer.read_bytes()
    if hashlib.sha256(data).hexdigest() != state["sha256"]:
        raise RuntimeError("O instalador pendente foi alterado; a publicação foi interrompida.")
    if state.get("commit"):
        if git(project, "rev-parse", "HEAD").stdout.strip() != state["commit"]:
            raise RuntimeError("HEAD mudou desde a publicação pendente; restaure a branch para retomá-la.")
    else:
        git(project, "add", "--all")
        if git(project, "diff", "--cached", "--quiet", check=False).returncode:
            git(project, "commit", "-m", "release: " + tag)
        state["commit"] = git(project, "rev-parse", "HEAD").stdout.strip()
        save_pending(pending, state)
    if git(project, "status", "--porcelain").stdout:
        raise RuntimeError("O código mudou durante o commit; a publicação foi interrompida.")
    existing = git(project, "rev-parse", "--verify", "refs/tags/" + tag + "^{commit}", check=False)
    if existing.returncode:
        git(project, "tag", "-a", tag, "-m", "Release " + tag, state["commit"])
    elif existing.stdout.strip() != state["commit"]:
        raise RuntimeError(f"A tag {tag} aponta para outro commit; ela não será sobrescrita.")
    git(project, "push", "--atomic", "origin", f"HEAD:refs/heads/{github.branch}",
        "refs/tags/" + tag, env=github.git_environment())
    release = github.release(version)
    if release is None:
        release = github.request("POST", github.base + "/releases", {
            "tag_name": tag, "target_commitish": state["commit"], "name": tag,
            "body": "Instalador Windows x64 com Python, Tkinter e Pillow incluídos.\n\n"
                    "Baixe o arquivo MSI abaixo. O SHA-256 está em SHA256SUMS.txt.",
            "generate_release_notes": True, "draft": True, "prerelease": False,
        })
    assets_url = github.base + "/releases/" + str(release["id"]) + "/assets"
    assets = {asset["name"]: asset for asset in github.request("GET", assets_url)}
    checksums = (state["sha256"] + "  " + installer.name + "\n").encode("utf-8")
    upload = release["upload_url"].split("{")[0]
    for name, content, content_type in ((installer.name, data, "application/x-msi"),
                                         ("SHA256SUMS.txt", checksums, "text/plain")):
        asset = assets.get(name)
        if asset is None:
            if not release["draft"]:
                raise RuntimeError("A release publicada está incompleta; não será alterada automaticamente.")
            asset = github.request("POST", upload + "?name=" + urllib.parse.quote(name),
                                   content, content_type)
        check_asset(asset, content)
    if release["draft"]:
        github.request("PATCH", github.base + "/releases/" + str(release["id"]),
                       {"draft": False, "make_latest": "true"})
    verified = github.release(version)
    if verified is None or verified["draft"] or verified["prerelease"]:
        raise RuntimeError("O GitHub ainda não confirmou a publicação da release.")
    uploaded = {asset["name"]: asset for asset in verified["assets"]}
    check_asset(uploaded.get(installer.name, {}), data)
    check_asset(uploaded.get("SHA256SUMS.txt", {}), checksums)
    pending.unlink()
    print("Release publicada: " + verified["html_url"], flush=True)
    return verified["html_url"]
