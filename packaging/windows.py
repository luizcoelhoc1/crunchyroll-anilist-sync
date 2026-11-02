"""Build Windows x64: task compile [VERSION=1.6.0]."""
import os
from pathlib import Path
import re
import shutil
import sys

from cx_Freeze import Executable, setup

PROJECT = Path(__file__).resolve().parents[1]
VERSION = os.environ.get("APP_BUILD_VERSION", "1.6.0")
if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,5}", VERSION) or any(
        int(part) > limit for part, limit in zip(VERSION.split("."), (255, 255, 65535))):
    raise SystemExit("VERSION deve ter o formato X.Y.Z (limites MSI: 255.255.65535).")
if sys.platform != "win32" or sys.maxsize <= 2**32:
    raise SystemExit("Compile usando Python 64 bits no Windows.")
os.chdir(PROJECT)

# Only these public assets are bundled. Never include the workspace wholesale.
ASSETS = [
    "mapeamentos_lumimao.json", "auth_config.json", ".env.example",
    "LEIA-ME.md", "README.md", "CONEXAO_CHROME.md",
    "ATUALIZACAO_1_2.md", "ATUALIZACAO_1_3.md", "ATUALIZACAO_1_4.md", "ATUALIZACAO_1_5.md",
    "extensao_chrome/background.mjs", "extensao_chrome/protocol.mjs",
    "extensao_chrome/connect.js", "extensao_chrome/manifest.json",
]

# Prevent stale files from earlier builds from entering the installer.
build_root = PROJECT / "build"
app_dir = build_root / "app"
if build_root.resolve() != build_root or app_dir.resolve() != app_dir:
    raise SystemExit("build/app não pode apontar para fora da pasta do projeto.")
if app_dir.exists():
    shutil.rmtree(app_dir)

setup(
    name="CrunchyrollAniListSync",
    version=VERSION,
    description="Crunchyroll - AniList Sync",
    author="Crunchyroll AniList Sync",
    options={
        "build_exe": {
            "build_exe": str(app_dir),
            "path": [str(PROJECT), *sys.path],
            "silent_level": 1,
            "packages": ["tkinter", "PIL"],
            "include_files": [(str(PROJECT / name), name) for name in ASSETS],
            "include_msvcr": True,
            "excludes": ["unittest", "pydoc", "pip", "setuptools"],
        },
        "bdist_msi": {
            "dist_dir": str(PROJECT / "dist"),
            "output_name": f"CrunchyrollAniListSync-{VERSION}-x64.msi",
            "product_name": "Crunchyroll - AniList Sync",
            "upgrade_code": "{708CB5BE-D1E8-48BA-A909-A67008BD7363}",
            "all_users": False,
            "add_to_path": False,
            "initial_target_dir": r"[LocalAppDataFolder]Programs\CrunchyrollAniListSync",
            "data": {"Directory": [("ProgramMenuFolder", "TARGETDIR", ".")]},
        },
    },
    executables=[Executable(
        "iniciar.pyw", base="gui", target_name="CrunchyrollAniListSync.exe",
        shortcut_name="Crunchyroll - AniList Sync", shortcut_dir="ProgramMenuFolder",
    )],
)
