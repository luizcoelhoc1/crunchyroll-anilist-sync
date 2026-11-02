"""Versão única do projeto e limites aceitos pelo instalador MSI."""
from pathlib import Path
import re

PROJECT = Path(__file__).resolve().parents[1]


def parse_version(value):
    if not re.fullmatch(r"(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,4})", value):
        raise ValueError("VERSION deve ter o formato X.Y.Z (limites MSI: 255.255.65535).")
    parts = tuple(map(int, value.split(".")))
    if any(part > limit for part, limit in zip(parts, (255, 255, 65535))):
        raise ValueError("VERSION excede os limites MSI: 255.255.65535.")
    return parts


def read_version(project=PROJECT):
    value = (project / "VERSION").read_text(encoding="utf-8").strip()
    parse_version(value)
    return value


def next_version(current, requested=""):
    major, minor, patch = parse_version(current)
    if requested:
        if parse_version(requested) <= (major, minor, patch):
            raise ValueError(f"VERSION deve ser maior que a versão atual {current}.")
        return requested
    if patch == 65535:
        raise ValueError("Limite de correções atingido. Informe uma versão maior com VERSION=X.Y.Z.")
    return f"{major}.{minor}.{patch + 1}"
