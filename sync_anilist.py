"""Crunchyroll -> AniList. Python 3.10+, biblioteca padrao.
Credenciais ficam apenas em memoria. Nenhuma alteracao remota durante a previa.
"""
from __future__ import annotations
import argparse
import base64
import copy
import csv
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
AL_API = "https://graphql.anilist.co"
AL_WEB = "https://anilist.co/graphql"
CR_ORIGIN = "https://www.crunchyroll.com"
EMPTY_DATE = {"year": None, "month": None, "day": None}
PROTECTED = ("score", "repeat", "private", "notes", "hiddenFromStatusLists",
             "customLists", "advancedScores", "startedAt", "completedAt")
ENTRY_FIELDS = """id mediaId status progress score repeat private notes
hiddenFromStatusLists customLists advancedScores startedAt{year month day}
completedAt{year month day} updatedAt"""
MEDIA_FIELDS = """id type title{romaji english native} synonyms episodes status format
startDate{year month day} endDate{year month day} externalLinks{site url}"""
STATUS_PT = {"CURRENT": "Assistindo", "COMPLETED": "Concluido", "PLANNING": "Planejado",
             "DROPPED": "Abandonado", "PAUSED": "Em pausa", "REPEATING": "Reassistindo"}


class SyncError(Exception):
    pass


class ApiError(SyncError):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


class Cancelled(SyncError):
    pass


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def protected(entry):
    return {key: entry.get(key) for key in PROTECTED}


def title_of(media):
    t = media.get("title") or {}
    return t.get("english") or t.get("romaji") or str(media["id"])


def normal(text):
    text = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"[^a-z0-9]", "", text.encode("ascii", "ignore").decode().lower())


def jwt_claims(token):
    """Leitura de claims para localizar conta/perfil; a API valida a autenticidade."""
    try:
        part = token.removeprefix("Bearer ").split(".")[1]
        value = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return value if isinstance(value, dict) else {}
    except (ValueError, IndexError, UnicodeError):
        return {}


def _strip_comments(text):
    # Remove comentarios JS fora de strings. Nunca executa o texto copiado.
    out, i, quote, escape = [], 0, None, False
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
        elif ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
        elif text[i:i+2] == "//":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text[i:i+2] == "/*":
            end = text.find("*/", i+2)
            if end < 0:
                raise SyncError("Comentario incompleto na requisicao copiada.")
            i = end + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_fetch(text, service):
    """Le Copy as fetch do Chrome, incluindo Cookie comentado, sem eval."""
    clean = _strip_comments(text)
    match = re.search(r"\bfetch\s*\(\s*(\"(?:\\.|[^\"\\])*\")", clean)
    if not match:
        raise SyncError("Cole uma requisicao 'Copy as fetch' do Chrome ou um token.")
    try:
        url = json.loads(match.group(1))
        pos = re.search(r'["\x27]?headers["\x27]?\s*:\s*', clean[match.end():])
        if not pos:
            raise ValueError()
        start = match.end() + pos.end()
        headers, _ = json.JSONDecoder().raw_decode(clean[start:].lstrip())
    except (ValueError, TypeError):
        raise SyncError("Nao foi possivel ler os headers. Use Copy > Copy as fetch.")
    parsed = urllib.parse.urlsplit(url)
    good = (parsed.scheme == "https" and
            ((service == "cr" and parsed.hostname == "www.crunchyroll.com"
              and re.fullmatch(r"/content/v2/[^/]+/watch-history", parsed.path))
             or (service == "al" and parsed.hostname in ("anilist.co", "graphql.anilist.co")
                 and parsed.path.rstrip("/") in ("", "/graphql"))))
    if not good:
        raise SyncError("Requisicao de dominio/endpoint inesperado. Nao sera utilizada.")
    if not isinstance(headers, dict):
        raise SyncError("Headers invalidos.")
    headers = {str(k).lower(): str(v) for k, v in headers.items()}
    cookie = re.search(r'^\s*//\s*"cookie"\s*:\s*("(?:\\.|[^"\\])*")',
                       text, re.MULTILINE | re.IGNORECASE)
    if cookie and "cookie" not in headers:
        headers["cookie"] = json.loads(cookie.group(1))
    allowed = {"authorization", "cookie", "x-csrf-token", "user-agent", "accept-language"}
    result = {k: v for k, v in headers.items() if k in allowed}
    if any("\r" in v or "\n" in v for v in result.values()):
        raise SyncError("Header com quebra de linha recusado.")
    return url, result


class PinnedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Uma resposta nunca pode encaminhar cookies/tokens para outro destino.
        raise ApiError("Redirecionamento da API recusado; renove a sessao.", code)


class HttpClient:
    def __init__(self, origin, headers=None, delay=0.0, log=print, cancelled=None):
        self.origin = origin.rstrip("/")
        self.headers = dict(headers or {})
        self.delay, self.log = delay, log
        self.cancelled = cancelled or (lambda: False)
        self.opener = urllib.request.build_opener(PinnedRedirect())
        self.last_request = 0.0
        self.not_before = 0.0
        self.rate = {}

    def check_cancelled(self):
        if self.cancelled():
            raise Cancelled("Operacao interrompida. As alteracoes ja confirmadas foram registradas.")

    def wait(self, seconds):
        end = time.monotonic() + max(0, seconds)
        while time.monotonic() < end:
            self.check_cancelled()
            remaining = end - time.monotonic()
            if remaining > 0:
                time.sleep(min(.2, remaining))

    def _safe_url(self, url):
        target = urllib.parse.urlsplit(urllib.parse.urljoin(self.origin + "/", url))
        origin = urllib.parse.urlsplit(self.origin)
        if (target.scheme != "https" or target.netloc != origin.netloc or
                target.username or target.password or target.fragment):
            raise SyncError("A API tentou acessar um destino inesperado.")
        return urllib.parse.urlunsplit(target)

    def request(self, method, url, body=None, mutation=False):
        url = self._safe_url(url)
        for attempt in range(4):
            self.check_cancelled()
            self.wait(max(self.last_request + self.delay, self.not_before) - time.monotonic())
            data = None if body is None else json.dumps(body).encode("utf-8")
            headers = {"Accept": "application/json",
                       "User-Agent": "CrunchyrollAniListSync/1.0", **self.headers}
            if data is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            self.last_request = time.monotonic()
            try:
                with self.opener.open(req, timeout=40) as response:
                    self.rate = dict(response.headers.items())
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    reset = response.headers.get("X-RateLimit-Reset")
                    if remaining == "0" and reset:
                        self.not_before = time.monotonic() + max(0, float(reset)-time.time()+1)
                    raw = response.read()
                try:
                    return json.loads(raw)
                except (ValueError, UnicodeError):
                    raise ApiError("A API nao retornou JSON. Verifique a sessao ou um bloqueio do site.")
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status == 429 and attempt < 3:
                    raw_retry = exc.headers.get("Retry-After", "60")
                    try:
                        retry = max(1.0, float(raw_retry))
                    except ValueError:
                        retry = 60.0
                    self.log(f"Limite da API: aguardando {retry:.0f}s.")
                    self.wait(retry)
                    continue
                if status in (401, 403):
                    raise ApiError(f"HTTP {status}: sessao expirada ou acesso recusado. "
                                   "Copie uma requisicao recente do site.", status) from None
                if not mutation and status in (500, 502, 503, 504) and attempt < 3:
                    self.wait(2 ** attempt)
                    continue
                raise ApiError(f"HTTP {status} na API; nenhuma repeticao automatica da gravacao.", status) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if not mutation and attempt < 3:
                    self.wait(2 ** attempt)
                    continue
                # Nao inclui headers, cookies ou texto da requisicao no erro.
                raise ApiError("Falha de conexao com a API. A gravacao pode ter sido recebida; "
                               "o estado sera consultado antes de continuar.") from None
        raise ApiError("Nao foi possivel consultar a API.")


class Crunchyroll:
    def __init__(self, credential, account_id=None, profile=None, **kwargs):
        text = credential.strip()
        if "fetch(" in text or "fetch (" in text:
            url, headers = parse_fetch(text, "cr")
            account_id = urllib.parse.urlsplit(url).path.split("/")[3]
            token = headers.get("authorization", "").removeprefix("Bearer ")
        else:
            token = text.removeprefix("Bearer ").strip()
            headers = {"authorization": "Bearer " + token}
        if not token:
            raise SyncError("Token do Crunchyroll ausente na requisicao.")
        claims = jwt_claims(token)
        account_id = account_id or (claims.get("scopes", {}).get("cr", {}).get("acc_id")
                                    or claims.get("etp_user_id"))
        if not account_id or not re.fullmatch(r"[A-Za-z0-9-]+", account_id):
            raise SyncError("Informe o ID da conta ou copie a requisicao watch-history completa.")
        if claims.get("exp") and float(claims["exp"]) <= time.time() + 5:
            raise SyncError("O token do Crunchyroll expirou. Copie uma requisicao recente.")
        self.account_id, self.claims, self.profile = account_id, claims, (profile or "").strip()
        self.auto_profile = profile is None
        self.http = HttpClient(CR_ORIGIN, headers, **kwargs)

    def verify_profile(self):
        pid = self.claims.get("profile_id")
        if not isinstance(pid, str) or not pid.strip():
            raise SyncError("O token nao informa o perfil ativo do Crunchyroll. "
                            "Selecione o perfil no navegador e conecte novamente.")
        pid = pid.strip()
        info = {"profile_id": pid, "verified_name": None, "identity_source": "token_profile"}
        # Compatibilidade: "" solicita apenas o ID; None detecta tambem o nome.
        if not self.profile and not self.auto_profile:
            return info
        if self.profile and self.profile.casefold() == pid.casefold():
            return info
        try:
            data = self.http.request("GET", "/accounts/v1/me/multiprofile")
        except ApiError:
            if self.profile:
                raise
            # O nome e opcional; a API de historico ainda valida a sessao e o perfil.
            info["name_lookup"] = "unavailable"
            return info
        profiles = (data.get("profiles") or data.get("data") or []) if isinstance(data, dict) else []
        if isinstance(profiles, dict):
            profiles = profiles.get("profiles", [])
        if not isinstance(profiles, list):
            profiles = []
        for p in profiles:
            if not isinstance(p, dict):
                continue
            ident = p.get("profile_id") or p.get("id")
            name = p.get("profile_name") or p.get("name") or ""
            if not isinstance(name, str):
                name = ""
            if isinstance(ident, str) and ident.casefold() == pid.casefold():
                if self.profile and name.casefold() != self.profile.casefold():
                    break
                info.update(verified_name=name or None, identity_source="profile_api",
                            avatar=p.get("avatar") or p.get("avatar_url"))
                return info
        if not self.profile:
            info["name_lookup"] = "not_found"
            return info
        raise SyncError("O perfil do token nao corresponde ao perfil esperado ou nao pode ser "
                        f"conferido. ID do perfil do token: {pid}. "
                        "Selecione o perfil correto no site e conecte novamente.")


    def identify(self):
        """Identifica o perfil sem percorrer todo o historico."""
        info = self.verify_profile()
        if info["identity_source"] != "profile_api":
            page = self.http.request("GET",
                f"/content/v2/{self.account_id}/watch-history?page_size=1&locale=en-US")
            if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                raise SyncError("Nao foi possivel validar o perfil ativo do Crunchyroll.")
        info["session_verified"] = True
        return info

    def history(self):
        profile_info = self.verify_profile()
        path = f"/content/v2/{self.account_id}/watch-history"
        current = path + "?page_size=100&locale=en-US"
        seen, rows, page = set(), [], 0
        while current:
            if current in seen or page >= 10000:
                raise SyncError("Paginacao repetida ou excessiva. Historico incompleto; previa cancelada.")
            seen.add(current)
            full_url = self.http._safe_url(current)
            if urllib.parse.urlsplit(full_url).path != path:
                raise SyncError("Cursor de historico de outra conta/endpoint recusado.")
            data = self.http.request("GET", full_url)
            if not isinstance(data.get("data"), list):
                raise SyncError("Formato inesperado do historico. Nenhuma alteracao aplicada.")
            rows.extend(data["data"])
            page += 1
            self.http.log(f"Crunchyroll: pagina {page}, {len(rows)} registros.")
            current = (data.get("meta") or {}).get("next_page")
        profile_info["history_verified"] = True
        return {"pages": page, "complete": True, "profile": profile_info,
                "groups": normalize_history(rows)}


def normalize_history(data):
    """Aceita exportacao deste programa, exportacao da conversa ou paginas brutas."""
    if isinstance(data, dict) and "groups" in data:
        if data.get("complete") is not True:
            raise SyncError("Exportacao de historico incompleta.")
        return copy.deepcopy(data["groups"])
    if isinstance(data, dict) and "data" in data:
        if data.get("meta", {}).get("next_page"):
            raise SyncError("O JSON contem apenas uma pagina. Exporte o historico inteiro.")
        data = data["data"]
    if not isinstance(data, list):
        raise SyncError("Formato de historico JSON desconhecido.")
    groups = {}
    for h in data:
        panel = h.get("panel") or {}
        m = panel.get("episode_metadata") or panel.get("movie_metadata") or {}
        identifier = m.get("identifier") or ""
        key = "|".join(identifier.split("|")[:2]) if identifier else (
            m.get("season_id") or h.get("parent_id") or "unknown")
        g = groups.setdefault(key, {
            "key": key, "title": m.get("series_title") or m.get("movie_listing_title") or panel.get("title"),
            "series": m.get("series_id") or h.get("parent_id"),
            "season": m.get("season_title") or "", "sn": m.get("season_number"),
            "seasonId": m.get("season_id"), "rows": []})
        g["rows"].append({
            "id": h.get("id"), "date": h.get("date_played"), "full": h.get("fully_watched") is True,
            "play": h.get("playhead"), "duration": m.get("duration_ms"),
            "seq": m.get("sequence_number"), "ep": m.get("episode_number"),
            "epText": m.get("episode"), "title": panel.get("title"),
            "versions": [v.get("guid") for v in m.get("versions", []) if v.get("guid")],
            "type": panel.get("type")})
    return list(groups.values())


class AniList:
    def __init__(self, credential, **kwargs):
        text = credential.strip()
        if "fetch(" in text or "fetch (" in text:
            url, headers = parse_fetch(text, "al")
            if urllib.parse.urlsplit(url).hostname == "anilist.co":
                if not headers.get("cookie") or not headers.get("x-csrf-token"):
                    raise SyncError("A requisicao web do AniList precisa de Cookie e X-CSRF-TOKEN. "
                                    "Use Copy as fetch (incluindo os comentarios), ou um token OAuth.")
                origin, self.endpoint = "https://anilist.co", AL_WEB
            else:
                origin, self.endpoint = AL_API, AL_API
                if not headers.get("authorization"):
                    raise SyncError("A requisicao da API precisa de Authorization.")
        else:
            if not text:
                raise SyncError("Informe um token OAuth ou uma requisicao autenticada do AniList.")
            headers = {"authorization": "Bearer " + text.removeprefix("Bearer ").strip()}
            origin, self.endpoint = AL_API, AL_API
        kwargs.setdefault("delay", 2.2)
        self.http = HttpClient(origin, headers, **kwargs)
        self.viewer = None

    def gql(self, query, variables=None, mutation=False):
        out = self.http.request("POST", self.endpoint,
                                {"query": query, "variables": variables or {}}, mutation=mutation)
        if out.get("errors"):
            # Mensagens GraphQL nao incluem as credenciais dos headers.
            messages = "; ".join(str(e.get("message", "erro")) for e in out["errors"])
            raise ApiError("AniList: " + messages[:300])
        if not isinstance(out.get("data"), dict):
            raise ApiError("Resposta inesperada do AniList.")
        return out["data"]

    def identify(self, expected_user=None):
        viewer = self.gql("query{Viewer{id name avatar{large medium}}}").get("Viewer")
        if not viewer:
            raise SyncError("A sessao do AniList nao esta autenticada.")
        if expected_user and viewer["name"].casefold() != expected_user.casefold():
            raise SyncError(f"Conta diferente da esperada: {viewer['name']}.")
        self.viewer = viewer
        return viewer

    def collection(self):
        if not self.viewer:
            self.identify()
        query = ("query($userId:Int!,$chunk:Int!){MediaListCollection(userId:$userId,"
                 "type:ANIME,chunk:$chunk,perChunk:500){hasNextChunk lists{entries{"
                 + ENTRY_FIELDS + " media{" + MEDIA_FIELDS + "}}}}}")
        entries, chunk = {}, 1
        while True:
            c = self.gql(query, {"userId": self.viewer["id"], "chunk": chunk})["MediaListCollection"]
            if c is None:
                raise SyncError("Lista do AniList indisponivel.")
            for group in c.get("lists", []):
                for e in group.get("entries", []):
                    entries[e["mediaId"]] = e
            if not c.get("hasNextChunk"):
                return list(entries.values())
            chunk += 1
            if chunk > 100:
                raise SyncError("Lista excessivamente paginada.")

    def _catalog_ids(self, media, ids):
        needed = sorted(set(ids) - media.keys())
        for i in range(0, len(needed), 50):
            q = "query($ids:[Int]){Page(perPage:50){media(type:ANIME,id_in:$ids){" + MEDIA_FIELDS + "}}}"
            for m in self.gql(q, {"ids": needed[i:i+50]})["Page"]["media"]:
                media[m["id"]] = m

    def catalog(self, groups, mappings, entries):
        media = {e["mediaId"]: e["media"] for e in entries if e.get("media")}
        self._catalog_ids(media, {r["mediaId"] for m in mappings["groups"].values()
                                 for r in m.get("rules", [])})
        # A busca descobre candidatos; o ID do link externo decide a franquia.
        searches = sorted({g["title"] for g in groups if g.get("title")
                           and g["key"] not in mappings["groups"]
                           and any(r.get("full") for r in g["rows"])})
        related = set()
        search_fields = MEDIA_FIELDS + " relations{edges{relationType node{id type}}}"
        for i in range(0, len(searches), 5):
            aliases = []
            for j, text in enumerate(searches[i:i+5]):
                aliases.append(f"s{j}:Page(perPage:25){{media(type:ANIME,search:"
                               + json.dumps(text, ensure_ascii=False) + "){" + search_fields + "}}")
            for page in self.gql("query{" + "".join(aliases) + "}").values():
                for m in page["media"]:
                    media[m["id"]] = m
                    for edge in (m.get("relations") or {}).get("edges", []):
                        node = edge.get("node") or {}
                        if (edge.get("relationType") in ("PREQUEL", "SEQUEL")
                                and node.get("type") == "ANIME"
                                and isinstance(node.get("id"), int)):
                            related.add(node["id"])
            self.http.log(f"Catalogo: {min(i+5,len(searches))}/{len(searches)} buscas.")
        # Uma rodada de prequelas/sequelas evita depender apenas do ranking da busca.
        self._catalog_ids(media, related)
        return media


    def entry(self, media_id):
        q = "query($u:Int!,$m:Int!){MediaList(userId:$u,mediaId:$m){" + ENTRY_FIELDS + "}}"
        return self.gql(q, {"u": self.viewer["id"], "m": media_id}).get("MediaList")

    def save(self, change, current):
        # Omitir id completamente na criacao: id:null e rejeitado pelo AniList web.
        declarations = "$m:Int!,$s:MediaListStatus!,$p:Int!,$start:FuzzyDateInput,$end:FuzzyDateInput"
        args = "mediaId:$m,status:$s,progress:$p,startedAt:$start,completedAt:$end"
        variables = {"m": change["mediaId"], "s": change["after"]["status"],
                     "p": change["after"]["progress"],
                     "start": current.get("startedAt") if current else EMPTY_DATE,
                     "end": current.get("completedAt") if current else EMPTY_DATE}
        if current:
            declarations += ",$id:Int!"
            args += ",id:$id"
            variables["id"] = current["id"]
        query = "mutation(" + declarations + "){SaveMediaListEntry(" + args + "){" + ENTRY_FIELDS + "}}"
        return self.gql(query, variables, mutation=True)["SaveMediaListEntry"]


def load_mappings(path=None):
    path = Path(path) if path else ROOT / "mapeamentos_lumimao.json"
    data = load_json(path)
    if data.get("schema_version") != 1 or not isinstance(data.get("groups"), dict):
        raise SyncError("Arquivo de mapeamentos invalido.")
    for key, group in data["groups"].items():
        for rule in group.get("rules", []):
            if not isinstance(rule.get("mediaId"), int) or rule["mediaId"] <= 0:
                raise SyncError(f"ID invalido no mapeamento {key}.")
            if rule.get("mode", "ep") not in ("ep", "seq", "one"):
                raise SyncError(f"Modo invalido no mapeamento {key}.")
            if rule.get("title"):
                try:
                    re.compile(rule["title"])
                except re.error:
                    raise SyncError(f"Expressao invalida no mapeamento {key}.")
    return data


def episode_for(row, rule):
    if rule.get("title") and not re.search(rule["title"], row.get("title") or "", re.I):
        return None
    mode = rule.get("mode", "ep")
    if mode == "one":
        value = 1
    elif mode == "seq":
        value = row.get("seq")
    else:
        text = row.get("epText")
        if text is None:
            text = row.get("ep")
        if not re.fullmatch(r"\d+", str(text)):
            return None
        value = int(text)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        return None
    value = int(value)
    if value < rule.get("lo", 1) or (rule.get("hi") is not None and value > rule["hi"]):
        return None
    value -= rule.get("offset", 0)
    return value if value >= 1 else None


def crunchyroll_series_id(url):
    """Extrai o ID estavel; idioma, slug e parametros nao alteram a serie."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme not in ("http", "https")
                or parsed.hostname not in ("crunchyroll.com", "www.crunchyroll.com")
                or parsed.username or parsed.password
                or parsed.port not in (None, 80 if parsed.scheme == "http" else 443)):
            return None
        match = re.fullmatch(r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?series/([A-Za-z0-9]{6,32})(?:/.*)?",
                             parsed.path, re.I)
        return match.group(1).upper() if match else None
    except ValueError:
        return None


def source_series_id(group):
    for value in (group.get("series"), (group.get("key") or "").split("|")[0]):
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9]{6,32}", value):
            return value.upper()
    return None


def crunchyroll_links(media):
    links = {}
    for link in media.get("externalLinks") or []:
        if not isinstance(link, dict):
            continue
        sid = crunchyroll_series_id(link.get("url"))
        if sid:
            links.setdefault(sid, []).append(link["url"])
    return links


def _season_numbers(text):
    values = re.findall(r"(?:season|temporada)\s*(\d+)\b", text or "", flags=re.I)
    values += re.findall(r"\b(\d+)(?:st|nd|rd|th)\s+season\b", text or "", flags=re.I)
    return {int(n) for n in values}


def _part_numbers(text):
    values = re.findall(r"\b(?:part|parte|cour)\s*(\d+)\b", text or "", flags=re.I)
    values += re.findall(r"\b(\d+)(?:st|nd|rd|th)\s+(?:part|cour)\b", text or "", flags=re.I)
    numbers = {int(n) for n in values}
    roman = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
             "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
    for value in re.findall(r"\b(?:part|parte|cour)\s+([IVX]+)\b", text or "", flags=re.I):
        if value.upper() in roman:
            numbers.add(roman[value.upper()])
    return numbers


def _compatible_part(source_season, primary_names):
    source_parts = _part_numbers(source_season)
    target_parts = set().union(*(_part_numbers(n) for n in primary_names))
    if source_parts:
        return len(source_parts) == 1 and target_parts == source_parts
    # Uma parte 2+ nao pode virar a temporada inteira so porque o catalogo e parcial.
    return not target_parts or target_parts == {1}


def auto_rule(group, catalog):
    """Prioriza o ID do link externo. O link compartilhado nao prova a temporada."""
    base, season = group.get("title") or "", group.get("season") or ""
    if not base:
        return None, "Metadados do episodio indisponiveis."
    season = re.sub(r"\s*\([^)]*(?:dub|version)[^)]*\)\s*$", "", season, flags=re.I).strip()
    season_numbers = _season_numbers(season)
    if len(season_numbers) > 1:
        return None, "Numero/nome de temporada ambiguo; crie um mapeamento."
    season_number = next(iter(season_numbers), None)
    labels = set()
    if season_number is not None:
        n = season_number
        suffix = "st" if n == 1 else "nd" if n == 2 else "rd" if n == 3 else "th"
        labels.update((base + f" Season {n}", base + f" {n}{suffix} Season"))
        if n == 1:
            labels.add(base)
        if _part_numbers(season):
            labels = {label + f" Part {part}" for label in labels for part in _part_numbers(season)}
    elif group.get("sn") in (None, 0, 1):
        labels.update((base, season))
    elif season and normal(season) != normal(base):
        labels.add(season)
    else:
        return None, "Numero/nome de temporada ambiguo; crie um mapeamento."
    labels = {normal(v) for v in labels if v}
    sid = source_series_id(group)
    linked, fallback = [], []
    linked_count, conflicts = 0, 0
    movie = group.get("sn") == 0 or any(r.get("type") == "movie" for r in group["rows"])
    for media in catalog.values():
        if media.get("type", "ANIME") != "ANIME":
            continue
        if movie:
            if media.get("format") not in ("MOVIE", "SPECIAL", "OVA") or media.get("episodes") != 1:
                continue
        elif media.get("format") not in ("TV", "TV_SHORT", "ONA"):
            continue
        primary_names = [v for v in (media.get("title") or {}).values() if v]
        names = primary_names + (media.get("synonyms") or [])
        title_match = bool(labels.intersection(normal(v) for v in names if v))
        urls = crunchyroll_links(media)
        has_link = bool(sid and sid in urls)
        linked_count += bool(has_link)
        # Um ID explicitamente diferente e uma contradicao, mesmo com nome igual.
        if sid and urls and not has_link:
            conflicts += bool(title_match)
            continue
        primary_seasons = set().union(*(_season_numbers(v) for v in primary_names))
        if season_number is not None and primary_seasons and primary_seasons != {season_number}:
            continue
        if not movie and not _compatible_part(season, primary_names):
            continue
        # Com a franquia confirmada pelo ID, um rotulo explicito de temporada
        # permite diferencas de idioma no nome base. Nao infere temporada 1 por ausencia.
        plain_season_name = any(re.search(
            r"(?:(?:season|temporada)\s*\d+|\d+(?:st|nd|rd|th)\s+season)"
            r"(?:\s+(?:part|parte|cour)\s+(?:\d+|[IVX]+))?\s*$",
            name, flags=re.I) for name in primary_names)
        explicit_season = (not movie and season_number is not None
                           and primary_seasons == {season_number} and plain_season_name)
        if has_link and (title_match or explicit_season):
            linked.append((media, urls[sid], "title" if title_match else "explicit_season"))
        elif title_match and not has_link:
            fallback.append((media, [], "title"))

    candidates = linked if linked else fallback
    if len(candidates) != 1:
        if linked:
            return None, f"Link Crunchyroll compartilhado: {len(linked)} candidatos de temporada/parte."
        if linked_count:
            return None, "Serie localizada pelo link, mas a temporada/parte nao foi confirmada."
        if conflicts:
            return None, "O nome coincide, mas o link Crunchyroll aponta para outra serie."
        return None, f"Correspondencia nao unica ({len(candidates)} candidatos)."
    media, urls, season_check = candidates[0]
    evidence = {"method": "crunchyroll_link" if urls else "title",
                "source_series_id": sid, "season_check": season_check}
    if urls:
        evidence["crunchyroll_url"] = sorted(urls)[0]
    rule = {"mediaId": media["id"], "mode": "one" if movie else "ep", "evidence": evidence}
    if not movie:
        numbers = [episode_for(r, rule) for r in group["rows"]]
        numbers = [n for n in numbers if n is not None]
        if not numbers or min(numbers) != 1:
            return None, "Numeracao cumulativa/temporada parcial; mapeamento necessario."
        if media.get("episodes") and max(numbers) > media["episodes"]:
            return None, "Uma temporada do Crunchyroll abrange mais de uma entrada do AniList."
    return rule, None


def profile_label(info):
    info = info or {}
    if info.get("identity_source") == "imported_history":
        return "Historico importado (JSON)"
    return info.get("verified_name") or info.get("profile_id") or "Perfil nao informado"


def match_label(change):
    labels = {"mapping": "Mapeamento", "crunchyroll_link": "ID Crunchyroll", "title": "Titulo"}
    methods = {m.get("method") for m in change.get("matches", [])}
    return " / ".join(labels[m] for m in labels if m in methods) or "Plano anterior"


def build_plan(groups, entries, catalog, mappings, user):
    existing = {e["mediaId"]: e for e in entries}
    selected, pending, ignored = {}, [], []
    for group in groups:
        if not any(r.get("full") is True for r in group["rows"]):
            continue
        configured = mappings["groups"].get(group["key"])
        if configured is not None and configured.get("skip_reason"):
            ignored.append({"source_key": group["key"], "title": group.get("title"),
                            "reason": configured["skip_reason"]})
            continue
        rules = (configured or {}).get("rules", [])
        if configured is None:
            auto, reason = auto_rule(group, catalog)
            if not auto:
                pending.append({"source_key": group["key"], "title": group.get("title") or group["key"],
                                "season": group.get("season"), "reason": reason})
                continue
            rules = [auto]
        used = set()
        row_targets = {}
        for rule in rules:
            media_id = rule["mediaId"]
            media = catalog.get(media_id)
            if media is None or media.get("type", "ANIME") != "ANIME":
                pending.append({"source_key": group["key"], "mediaId": media_id,
                                "reason": "Entrada do catalogo indisponivel."})
                continue
            item = selected.setdefault(media_id, {
                "media": media, "source_keys": [], "full": set(), "matches": []})
            item["source_keys"].append(group["key"])
            evidence = copy.deepcopy(rule.get("evidence") or {"method": "mapping"})
            evidence.update(source_key=group["key"], mediaId=media_id)
            sid = source_series_id(group)
            if sid in crunchyroll_links(media):
                evidence.setdefault("crunchyroll_url", sorted(crunchyroll_links(media)[sid])[0])
            if evidence not in item["matches"]:
                item["matches"].append(evidence)
            for index, row in enumerate(group["rows"]):
                number = episode_for(row, rule)
                if number is None or (media.get("episodes") and number > media["episodes"]):
                    continue
                if row.get("full") is True:
                    other = row_targets.get(index)
                    if other is not None and other != media_id:
                        raise SyncError(f"Um episodio corresponde a duas entradas em {group['key']}.")
                    row_targets[index] = media_id
                    item["full"].add(number)
                    used.add(index)
        leftovers = [r for i, r in enumerate(group["rows"]) if r.get("full") is True and i not in used]
        if leftovers:
            labels = sorted({str(r.get("epText") or r.get("title") or r.get("id")) for r in leftovers})
            pending.append({"source_key": group["key"], "title": group.get("title"),
                            "reason": "Episodios/especiais fora das regras de numeracao.",
                            "episodes": labels})
    changes, preserved = [], []
    for media_id, item in selected.items():
        if not item["full"]:
            continue
        before, media = existing.get(media_id), item["media"]
        progress = (before or {}).get("progress") or 0
        target, full = progress, item["full"]
        while target + 1 in full:
            target += 1
        maximum = max(full, default=0)
        if maximum > target and (before or {}).get("status") != "COMPLETED":
            pending.append({"mediaId": media_id, "title": title_of(media),
                            "reason": "Lacunas: so foi considerado o progresso confirmado em sequencia.",
                            "progress": target, "last_full": maximum,
                            "missing": [i for i in range(progress+1, maximum+1) if i not in full]})
        if not before and target == 0:
            continue
        if before and before["status"] == "COMPLETED":
            preserved.append(media_id)
            continue
        total = media.get("episodes")
        if total and target >= total and maximum >= total:
            status = "COMPLETED"
        elif before and before["status"] in ("DROPPED", "PAUSED", "REPEATING"):
            status = before["status"]
        else:
            status = "CURRENT"
        if before and target == progress and status == before["status"]:
            preserved.append(media_id)
            continue
        if target < progress:
            raise SyncError("O plano tentou diminuir progresso.")
        changes.append({"mediaId": media_id, "title": title_of(media), "episodes": total,
                        "before": copy.deepcopy(before), "after": {"status": status, "progress": target},
                        "source_keys": sorted(set(item["source_keys"])),
                        "matches": item["matches"]})
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "user": user, "changes": changes, "preserved": preserved,
            "pending": pending, "ignored": ignored,
            "summary": {"changes": len(changes),
                        "new": sum(c["before"] is None for c in changes),
                        "updated": sum(c["before"] is not None for c in changes),
                        "completed": sum(c["after"]["status"] == "COMPLETED" for c in changes),
                        "pending": len(pending)}}


def write_preview(folder, plan, entries, history=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    save_json(folder / "plano.json", plan)
    save_json(folder / "anilist-antes.json", {"user": plan["user"], "entries": entries})
    if history is not None:
        save_json(folder / "historico-crunchyroll.json", history)
    with (folder / "alteracoes.csv").open("w", newline="", encoding="utf-8-sig") as out:
        writer = csv.writer(out, delimiter=";")
        writer.writerow(["Anime", "Acao", "Status antes", "Episodios antes",
                         "Status depois", "Episodios depois", "Total", "Link", "Correspondencia"])
        for c in plan["changes"]:
            b = c["before"] or {}
            writer.writerow([c["title"], "Adicionar" if not b else "Atualizar",
                             STATUS_PT.get(b.get("status"), "Ausente"), b.get("progress", ""),
                             STATUS_PT[c["after"]["status"]], c["after"]["progress"], c["episodes"],
                             f"https://anilist.co/anime/{c['mediaId']}", match_label(c)])
    lines = ["# Previa da sincronizacao", "",
             "AniList: " + str(plan["user"].get("name") or "offline") +
             " (ID " + str(plan["user"].get("id")) + ")",
             "Crunchyroll: " + profile_label(plan.get("cr_profile")), "",
             json.dumps(plan["summary"], ensure_ascii=False), "",
             "Nenhuma mudanca remota foi feita ao gerar esta previa.", "",
             "## Pendencias", ""]
    for p in plan["pending"]:
        lines.append("- " + str(p.get("title") or p.get("mediaId") or p.get("source_key")) +
                     ": " + p["reason"] + (" " + str(p["missing"]) if "missing" in p else ""))
    (folder / "resumo.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def preview_live(cr, al, mappings, folder, expected_user=None, on_identity=None):
    # Coleta primeiro o historico: o token do CR normalmente tem validade curta.
    history = cr.history()
    user = al.identify(expected_user)
    if on_identity:
        on_identity(user, history.get("profile"))
    entries = al.collection()
    catalog = al.catalog(history["groups"], mappings, entries)
    plan = build_plan(history["groups"], entries, catalog, mappings, user)
    plan["cr_profile"] = history.get("profile")
    write_preview(folder, plan, entries, history)
    return plan


def _same_baseline(a, b):
    if not a or not b:
        return a is None and b is None
    return (a["id"] == b["id"] and a["status"] == b["status"]
            and a["progress"] == b["progress"] and protected(a) == protected(b))


def _matches_target(entry, change):
    return bool(entry and entry["status"] == change["after"]["status"]
                and entry["progress"] == change["after"]["progress"])


def apply_plan(al, plan, folder):
    if plan.get("review_state_only"):
        raise SyncError("Este arquivo e o estado da revisao e inclui itens nao marcados. "
                        "Aplique plano-revisado.json, que contem somente os itens selecionados.")
    if plan.get("offline"):
        raise SyncError("Previa offline nao pode ser aplicada. Gere uma previa autenticada atual.")
    if plan.get("schema_version") != 1 or not isinstance(plan.get("changes"), list):
        raise SyncError("Plano invalido.")
    viewer = al.identify(plan["user"]["name"])
    if viewer["id"] != plan["user"]["id"]:
        raise SyncError("O plano pertence a outra conta.")
    live_entries = al.collection()
    live = {e["mediaId"]: e for e in live_entries}
    todo, skipped, conflicts = [], [], []
    for c in plan["changes"]:
        if (not isinstance(c.get("mediaId"), int) or c["mediaId"] <= 0
                or not isinstance(c.get("after", {}).get("progress"), int)
                or isinstance(c["after"]["progress"], bool) or c["after"]["progress"] < 0
                or c["after"].get("status") not in STATUS_PT):
            raise SyncError("Alteracao invalida no plano.")
        current, target = live.get(c["mediaId"]), c["after"]
        if current and (current["status"] == "COMPLETED" or _matches_target(current, c)
                        or current["progress"] > target["progress"]):
            skipped.append({"mediaId": c["mediaId"], "reason": "Ja aplicado ou progresso maior."})
            continue
        if not _same_baseline(current, c.get("before")):
            conflicts.append(c["mediaId"])
        else:
            todo.append(c)
    if conflicts:
        raise SyncError("A lista mudou desde a previa. Gere outra previa antes de gravar. IDs: "
                        + ", ".join(map(str, conflicts)))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(time.time_ns())[-6:]
    save_json(folder / f"backup-aplicacao-{stamp}.json", {"user": viewer, "entries": live_entries})
    results = []
    attempted = []
    journal_path = folder / "diario-aplicacao.jsonl"
    try:
        for c in todo:
            al.http.check_cancelled()
            current = live.get(c["mediaId"])
            attempted.append(c["mediaId"])
            with journal_path.open("a", encoding="utf-8") as journal:
                journal.write(json.dumps({"phase": "attempt", "mediaId": c["mediaId"],
                                          "after": c["after"]}) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
            try:
                saved = al.save(c, current)
            except ApiError:
                # Uma conexao interrompida pode esconder uma gravacao bem-sucedida.
                # Consulta o estado, em vez de repetir cegamente a mutation.
                recovered = al.entry(c["mediaId"])
                if not _matches_target(recovered, c):
                    raise
                saved = recovered
            if not _matches_target(saved, c):
                raise SyncError(f"Resultado divergente para {c['mediaId']}; confira o diario.")
            if current and protected(saved) != protected(current):
                raise SyncError(f"Campos protegidos divergentes em {c['mediaId']}; "
                                "a execucao foi interrompida. Consulte o backup.")
            results.append(saved)
            with journal_path.open("a", encoding="utf-8") as journal:
                journal.write(json.dumps({"phase": "confirmed", "time": datetime.now(timezone.utc).isoformat(),
                                          "mediaId": c["mediaId"], "result": saved},
                                         ensure_ascii=False) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
            al.http.log(f"Confirmado {len(results)}/{len(todo)}: {c['title']} "
                        f"-> {saved['status']} {saved['progress']}")
        after_entries = al.collection()
        after = {e["mediaId"]: e for e in after_entries}
        target_errors = [c["mediaId"] for c in todo if not _matches_target(after.get(c["mediaId"]), c)]
        protected_errors = [e["mediaId"] for e in live_entries
                            if e["mediaId"] not in after
                            or protected(e) != protected(after[e["mediaId"]])]
        applied_ids = {c["mediaId"] for c in todo}
        unexpected = [e["mediaId"] for e in live_entries if e["mediaId"] not in applied_ids
                      and (e["mediaId"] not in after
                           or e["status"] != after[e["mediaId"]]["status"]
                           or e["progress"] != after[e["mediaId"]]["progress"])]
        report = {"user": viewer, "applied": len(results), "skipped": skipped,
                  "target_errors": target_errors, "protected_errors": protected_errors,
                  "unexpected_changes": unexpected, "total_before": len(live_entries),
                  "total_after": len(after_entries), "success": not (target_errors or protected_errors or unexpected),
                  "confirmed_entries": [{k: v for k, v in after[c["mediaId"]].items() if k != "media"}
                                        for c in plan["changes"] if c["mediaId"] in after]}
        save_json(folder / "verificacao.json", report)
        save_json(folder / "anilist-depois.json", {"user": viewer, "entries": after_entries})
        if not report["success"]:
            raise SyncError("Ha divergencias na conferencia final. Consulte verificacao.json.")
        return report
    except Exception as exc:
        save_json(folder / "execucao-interrompida.json",
                  {"confirmed": [r["mediaId"] for r in results],
                   "attempted": attempted,
                   "uncertain": [i for i in attempted if i not in {r["mediaId"] for r in results}],
                   "reason": str(exc)})
        raise


def snapshot_entries(data):
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return data["entries"]
    if isinstance(data, list):
        return list({e["mediaId"]: e for c in data for g in c["lists"] for e in g["entries"]}.values())
    raise SyncError("Snapshot de AniList desconhecido.")


def new_run_folder():
    return ROOT / "execucoes" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def credentials(env_name, label):
    value = os.environ.get(env_name)
    if value:
        return value
    import getpass
    return getpass.getpass(label + ": ")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sincroniza Crunchyroll -> AniList por API.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="Abrir interface grafica (padrao).")
    p = commands.add_parser("preview", help="Gerar previa sem alterar o AniList.")
    p.add_argument("--history", type=Path, help="Historico JSON completo, em vez da API do CR.")
    p.add_argument("--snapshot", type=Path, help="Snapshot do AniList: modo offline.")
    p.add_argument("--catalog", action="append", type=Path, default=[], help="Catalogo JSON para modo offline.")
    p.add_argument("--mappings", type=Path)
    p.add_argument("--user", help="Opcional: conferir usuario esperado; por padrao detecta pela sessao.")
    p.add_argument("--profile", help="Opcional: conferir perfil esperado; por padrao usa o perfil ativo do token.")
    p.add_argument("--account-id")
    p.add_argument("--out", type=Path)
    a = commands.add_parser("apply", help="Aplicar um plano salvo, apos conferencia.")
    a.add_argument("--plan", type=Path, required=True)
    a.add_argument("--yes", action="store_true", help="Confirmar a aplicacao do plano.")
    args = parser.parse_args(argv)
    if args.command in (None, "gui"):
        from interface import start_gui
        start_gui()
        return 0
    if args.command == "apply":
        if not args.yes:
            parser.error("Confira o plano e acrescente --yes para autorizar a gravacao.")
        plan = load_json(args.plan)
        al = AniList(credentials("ANILIST_AUTH", "Token OAuth ou Copy as fetch do AniList"))
        report = apply_plan(al, plan, args.plan.parent)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    mappings = load_mappings(args.mappings)
    folder = args.out or new_run_folder()
    if args.snapshot:
        if not args.history:
            parser.error("--snapshot requer --history para a previa offline.")
        groups = normalize_history(load_json(args.history))
        entries = snapshot_entries(load_json(args.snapshot))
        catalog = {e["mediaId"]: e["media"] for e in entries if e.get("media")}
        for path in args.catalog:
            for m in load_json(path):
                catalog[m["id"]] = m
        user = {"id": None, "name": args.user or "offline"}
        plan = build_plan(groups, entries, catalog, mappings, user)
        plan["offline"] = True
        write_preview(folder, plan, entries)
    else:
        al = AniList(credentials("ANILIST_AUTH", "Token OAuth ou Copy as fetch do AniList"))
        if args.history:
            history_data = load_json(args.history)
            groups = normalize_history(history_data)
            user = al.identify(args.user)
            entries = al.collection()
            catalog = al.catalog(groups, mappings, entries)
            plan = build_plan(groups, entries, catalog, mappings, user)
            plan["cr_profile"] = {"identity_source": "imported_history"}
            write_preview(folder, plan, entries, history_data)
        else:
            cr = Crunchyroll(credentials("CRUNCHYROLL_AUTH", "Token ou Copy as fetch do Crunchyroll"),
                             account_id=args.account_id, profile=args.profile)
            plan = preview_live(cr, al, mappings, folder, args.user)
    print(json.dumps(plan["summary"], ensure_ascii=False, indent=2))
    print("Arquivos:", folder.resolve())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SyncError, OSError, ValueError) as exc:
        print("Erro:", str(exc), file=sys.stderr)
        sys.exit(1)
