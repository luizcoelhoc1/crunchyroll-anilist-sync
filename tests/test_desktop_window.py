"""Exercita o loop nativo de arrasto em processo separado: falhas do GIL são fatais."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from desktop_window import IntegratedTitlebar


class DragMessageTests(unittest.TestCase):
    def test_drag_queues_native_caption_message_with_screen_coordinates(self):
        # Only expose queued dispatch: synchronous dispatch can fatally reenter Tk.
        user = SimpleNamespace(ReleaseCapture=Mock(), PostMessageW=Mock())
        caption = SimpleNamespace(hwnd=123, user=user)
        event = SimpleNamespace(x_root=-250, y_root=140)
        IntegratedTitlebar.drag(caption, event)
        user.ReleaseCapture.assert_called_once_with()
        user.PostMessageW.assert_called_once_with(123, 0x00A1, 2, (140 << 16) | (-250 & 0xffff))

    def test_drag_without_native_window_is_ignored(self):
        IntegratedTitlebar.drag(SimpleNamespace(hwnd=None), SimpleNamespace())


def exercise_caption():
    import ctypes
    from ctypes import wintypes
    import faulthandler
    import threading
    import time
    import tkinter as tk
    from tkinter import ttk

    sys.path.insert(0, str(PROJECT))
    from desktop_window import IntegratedTitlebar

    faulthandler.enable()
    root = tk.Tk()
    root.geometry("640x300+100+100")
    bar = ttk.Frame(root)
    bar.pack(fill="x")
    title = ttk.Label(bar, text="Teste de arrasto")
    caption = IntegratedTitlebar(root, bar, title, root.destroy)
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  ctypes.c_size_t, ctypes.c_ssize_t]
    user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    finished = threading.Event()
    timer_ran = []
    moved = []
    errors = []

    def callback_error(*error):
        errors.append(error)
        root.quit()

    root.report_callback_exception = callback_error

    def drag():
        assert caption.hwnd and caption.original, "Barra nativa não foi instalada"
        hwnd = caption.hwnd

        def move():
            # Move only this test window, without touching the user's cursor.
            try:
                for step in range(1, 7):
                    time.sleep(.08)
                    if not user.SetWindowPos(hwnd, None, 100 + step * 10, 100 + step * 5,
                                             0, 0, 0x0015):  # NOSIZE | NOZORDER | NOACTIVATE
                        errors.append("SetWindowPos falhou")
            finally:
                user.PostMessageW(hwnd, 0x001F, 0, 0)  # WM_CANCELMODE exits the modal drag.
                finished.set()

        threading.Thread(target=move, daemon=True).start()
        root.after(50, lambda: timer_ran.append(True))
        title.event_generate("<ButtonPress-1>", x=30, y=12)

    def check():
        if finished.is_set():
            rect = wintypes.RECT()
            assert user.GetWindowRect(caption.hwnd, ctypes.byref(rect))
            moved.append((rect.left, rect.top))
            root.quit()
        else:
            root.after(30, check)

    root.after(300, drag)
    root.after(1500, check)
    root.after(5000, root.quit)
    try:
        root.mainloop()
        assert not errors, errors
        assert finished.is_set(), "O arrasto não terminou"
        assert timer_ran, "Eventos Tk não foram processados durante o arrasto"
        assert moved == [(160, 130)], moved
    finally:
        root.destroy()


@unittest.skipUnless(os.name == "nt", "Arrasto nativo do Windows")
class DesktopWindowTests(unittest.TestCase):
    def test_native_drag_processes_tk_events_without_crashing(self):
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", str(Path(__file__).resolve()), "--exercise-caption"],
            cwd=PROJECT, capture_output=True, text=True, timeout=12,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    if "--exercise-caption" in sys.argv:
        exercise_caption()
    else:
        unittest.main()
