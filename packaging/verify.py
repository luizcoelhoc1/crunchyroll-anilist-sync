"""Confere o MSI sem instalá-lo e abre o executável com dados locais vazios."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import tempfile
import time

import msilib

PROJECT = Path(__file__).resolve().parents[1]
version = os.environ.get("APP_BUILD_VERSION", "1.6.0")
installer = PROJECT / "dist" / f"CrunchyrollAniListSync-{version}-x64.msi"
database = msilib.OpenDatabase(str(installer), msilib.MSIDBOPEN_READONLY)


def rows(table, columns):
    view = database.OpenView("SELECT " + ", ".join(f"`{c}`" for c in columns) + f" FROM `{table}`")
    view.Execute(None)
    result = []
    while record := view.Fetch():
        result.append(tuple(record.GetString(i + 1) for i in range(len(columns))))
    view.Close()
    return result


properties = dict(rows("Property", ["Property", "Value"]))
assert properties["ProductVersion"] == version, "Versão MSI divergente"
assert properties["UpgradeCode"] == "{708CB5BE-D1E8-48BA-A909-A67008BD7363}", "UpgradeCode divergente"
assert properties.get("ALLUSERS", "") != "1", "O MSI deve instalar por usuário"
assert properties.get("MSIINSTALLPERUSER") == "1", "Falta a configuração de instalação por usuário"
names = {name.split("|")[-1].lower() for name, in rows("File", ["FileName"])}
assert {"crunchyrollanilistsync.exe", "mapeamentos_lumimao.json", "leia-me.md",
        "manifest.json", "background.mjs", "protocol.mjs", "connect.js", ".env.example"} <= names
assert not names.intersection({".env", "sessions.dat", "client-credentials.dat", "historico-crunchyroll.json"})
assert rows("Shortcut", ["Shortcut"]), "Falta o atalho do menu Iniciar"
database.Close()

user = ctypes.WinDLL("user32", use_last_error=True)
user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]

with tempfile.TemporaryDirectory(prefix="cral-msi-check-") as folder:
    environ = {key: value for key, value in os.environ.items() if not key.startswith("ANILIST_")}
    environ["LOCALAPPDATA"] = folder
    process = subprocess.Popen([str(PROJECT / "build" / "app" / "CrunchyrollAniListSync.exe")],
                               cwd=folder, env=environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    windows = []
    titles = set()

    @callback_type
    def find_window(hwnd, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process.pid and user.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(hwnd, title, len(title))
            titles.add(title.value)
            if title.value == "Crunchyroll → AniList":
                windows.append(hwnd)
        return True

    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and process.poll() is None:
            user.EnumWindows(find_window, 0)
            if windows:
                break
            time.sleep(.1)
        error = Path(folder) / "CrunchyrollAniListSync" / "erro-inicializacao.txt"
        if error.exists():
            raise RuntimeError(error.read_text(encoding="utf-8"))
        if not windows:
            detail = ""
            if process.poll() is not None:
                out, err = process.communicate()
                detail = (out + err).decode("utf-8", errors="replace")[-2500:]
            raise RuntimeError(f"O executável não abriu a janela principal (código {process.poll()}, "
                               f"janelas {titles}). {detail}")
        # Exercise the native move loop while the app's Tk timers keep running.
        hwnd = windows[0]
        rect = wintypes.RECT()
        assert user.GetWindowRect(hwnd, ctypes.byref(rect))
        position = (rect.left & 0xffff) | ((rect.top & 0xffff) << 16)
        assert user.PostMessageW(hwnd, 0x00A1, 2, position)
        for step in range(1, 7):
            time.sleep(.08)
            assert process.poll() is None, "O executável encerrou durante o movimento"
            assert user.SetWindowPos(hwnd, None, rect.left + step * 5, rect.top + step * 3,
                                      0, 0, 0x0015), "Não foi possível mover a janela de teste"
        assert user.PostMessageW(hwnd, 0x001F, 0, 0)  # WM_CANCELMODE
        # Only close the test process's verified main window.
        time.sleep(.5)
        user.PostMessageW(windows[0], 0x0010, 0, 0)
        assert process.wait(timeout=10) == 0, "O executável terminou com erro"
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)

print(f"MSI, inicialização e movimento conferidos: {installer.name} ({installer.stat().st_size / 1024**2:.1f} MiB)")
