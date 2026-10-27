"""Inicializador sem console no Windows."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    if sys.version_info < (3, 10):
        raise RuntimeError("E necessario Python 3.10 ou superior.")
    from interface import start_gui
    start_gui()
except Exception:
    import traceback
    details = traceback.format_exc()
    try:
        (ROOT / "erro-inicializacao.txt").write_text(details, encoding="utf-8")
    except OSError:
        pass
    try:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror("Erro ao iniciar",
                             "Nao foi possivel abrir o programa.\n"
                             "Confira o Python/Tkinter e o arquivo erro-inicializacao.txt.\n\n"
                             + details[-1200:])
        root.destroy()
    except Exception:
        pass
    sys.exit(1)
