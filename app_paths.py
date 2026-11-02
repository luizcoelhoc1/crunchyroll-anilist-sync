"""Recursos de instalação separados dos arquivos gravados pelo usuário."""
import os
from pathlib import Path
import sys

FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
DATA_ROOT = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
             / "CrunchyrollAniListSync") if FROZEN else RESOURCE_ROOT
