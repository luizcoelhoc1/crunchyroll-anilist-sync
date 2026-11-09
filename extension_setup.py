"""Configuração guiada da extensão local, pelo aplicativo ou após o MSI."""
import os
import tkinter as tk
from tkinter import messagebox
import webbrowser

from app_paths import RESOURCE_ROOT
from browser_bridge import open_chrome
from sync_anilist import SyncError


def show_extension_setup(parent=None):
    own_root = parent is None
    if own_root:
        parent = tk.Tk()
        parent.withdraw()
    try:
        folder = RESOURCE_ROOT / "extensao_chrome"
        if not (folder / "manifest.json").is_file():
            messagebox.showerror(
                "Extensão não encontrada",
                "Reinstale o aplicativo para recuperar a pasta da extensão.\n\n" + str(folder),
                parent=parent,
            )
            return
        warnings = []
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                webbrowser.open(folder.as_uri())
        except OSError:
            warnings.append("Não foi possível abrir a pasta automaticamente. Use o caminho abaixo.")
        try:
            open_chrome("chrome://extensions")
        except (SyncError, OSError):
            warnings.append("Abra ou instale o Google Chrome para continuar.")
        messagebox.showinfo(
            "Instalar extensão no Chrome",
            "No perfil do Chrome que você usa com o Crunchyroll e o AniList:\n\n"
            "1. Abra chrome://extensions.\n"
            "2. Ative Modo do desenvolvedor.\n"
            "3. Clique em Carregar sem compactação.\n"
            "4. Selecione a pasta indicada abaixo.\n\n"
            "Pasta da extensão:\n" + str(folder) + "\n\n"
            "Mantenha a pasta no lugar. Depois, no aplicativo, use "
            "Opções avançadas → Conectar pela extensão."
            + ("\n\n" + "\n".join(warnings) if warnings else ""),
            parent=parent,
        )
    finally:
        if own_root:
            parent.destroy()
