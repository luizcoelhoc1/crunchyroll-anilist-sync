"""Imagens publicas das contas: nenhuma credencial e enviada ao CDN."""
from __future__ import annotations
import io
import math
import re
import urllib.parse
import urllib.request

MAX_BYTES = 2 * 1024 * 1024


def allowed_avatar_url(url, service):
    if service not in ("al", "cr") or not isinstance(url, str):
        return False
    try:
        p = urllib.parse.urlsplit(url)
        host = p.hostname or ""
        allowed = ((host == "anilist.co" or host.endswith(".anilist.co")) if service == "al"
                   else host in ("static.crunchyroll.com", "www.crunchyroll.com",
                                 "crunchyroll.com", "images.crunchyroll.com"))
        return (p.scheme == "https" and allowed and p.port in (None, 443)
                and not p.username and not p.password and not p.fragment)
    except ValueError:
        return False


def avatar_url(service, info):
    info = info or {}
    value = info.get("avatar")
    if isinstance(value, dict):
        value = (value.get("medium") or value.get("large") or value.get("url")
                 or value.get("source"))
    value = value or info.get("avatar_url")
    if service == "cr" and isinstance(value, str) and re.fullmatch(r"[\w.-]+\.(?:png|jpe?g|webp)", value, re.I):
        value = "https://static.crunchyroll.com/assets/avatar/170x170/" + value
    return value if allowed_avatar_url(value, service) else None


class AvatarRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, service):
        self.service = service

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_avatar_url(newurl, self.service):
            raise ValueError("Destino de avatar inesperado.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_avatar(url, service):
    if not allowed_avatar_url(url, service):
        raise ValueError("URL de avatar invalida.")
    # Opener novo: sem Cookie, Authorization ou headers de sessao.
    opener = urllib.request.build_opener(AvatarRedirect(service))
    request = urllib.request.Request(url, headers={"User-Agent": "CrunchyrollAniListSync/1.4",
                                                   "Accept": "image/png,image/jpeg,image/*;q=0.8"})
    with opener.open(request, timeout=10) as response:
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            raise ValueError("O avatar nao retornou imagem.")
        data = response.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Tamanho de avatar invalido.")
    return data


def avatar_photo(root, data, size=56):
    """Chamado na thread Tk. Pillow e opcional; Tk puro aceita PNG/GIF."""
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError("Imagem invalida.")
    try:
        from PIL import Image, ImageDraw, ImageOps, ImageTk
    except ImportError:
        import tkinter as tk
        image = tk.PhotoImage(master=root, data=data)
        if image.width() * image.height() > 4_194_304:
            raise ValueError("Avatar grande demais.")
        factor = max(1, math.ceil(max(image.width(), image.height()) / size))
        return image.subsample(factor, factor)
    with Image.open(io.BytesIO(data)) as original:
        if original.width * original.height > 4_194_304:
            raise ValueError("Avatar grande demais.")
        picture = ImageOps.fit(original.convert("RGBA"), (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).ellipse((0, 0, size-1, size-1), fill=255)
    picture.putalpha(mask)
    return ImageTk.PhotoImage(picture, master=root)
