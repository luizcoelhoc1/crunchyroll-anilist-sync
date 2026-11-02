"""Barra de título integrada mantendo a janela normal do Windows e seu resize.

Frame handling follows https://learn.microsoft.com/windows/win32/dwm/customframe.
"""
import os
import ctypes
from ctypes import wintypes
from tkinter import ttk


class IntegratedTitlebar:
    def __init__(self, root, bar, title, close):
        self.root = root
        self.hwnd = None
        self.original = None
        self.callback = None
        self.controls = ttk.Frame(bar, style="Rail.TFrame")
        self.controls.pack(side="right")
        ttk.Button(self.controls, text="—", width=4, style="Caption.TButton",
                   command=root.iconify).pack(side="left")
        self.maximize_button = ttk.Button(self.controls, text="□", width=4, style="Caption.TButton",
                                          command=self.toggle_maximize)
        self.maximize_button.pack(side="left")
        ttk.Button(self.controls, text="×", width=4, style="Close.TButton", command=close).pack(side="left")
        title.pack(side="left", fill="both", expand=True, padx=16)
        for widget in (title, bar):
            widget.bind("<ButtonPress-1>", self.drag)
            widget.bind("<Double-Button-1>", lambda event: self.toggle_maximize())
        root.bind("<Configure>", self.update_maximize_icon, add="+")
        root.bind("<Destroy>", self.on_destroy, add="+")
        root.bind("<Map>", lambda event: self.install() if event.widget is root else None, add="+")

    def toggle_maximize(self):
        self.root.state("normal" if self.root.state() == "zoomed" else "zoomed")

    def update_maximize_icon(self, event):
        if event.widget is self.root:
            self.maximize_button.configure(text="❐" if self.root.state() == "zoomed" else "□")

    def drag(self, event):
        if self.hwnd:
            self.user.ReleaseCapture()
            # Return to Tcl before Windows enters its modal move loop. SendMessage
            # here can reenter Tk callbacks with no saved Python thread state.
            position = (event.x_root & 0xffff) | ((event.y_root & 0xffff) << 16)
            self.user.PostMessageW(self.hwnd, 0x00A1, 2, position)  # Native caption drag / snap.

    def install(self):
        if self.original:
            return
        if os.name != "nt":
            self.controls.pack_forget()
            return
        user = self.user = ctypes.WinDLL("user32", use_last_error=True)
        pointer = ctypes.c_void_p
        user.GetParent.argtypes = [pointer]
        user.GetParent.restype = pointer
        user.CallWindowProcW.argtypes = [pointer, pointer, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        user.CallWindowProcW.restype = ctypes.c_ssize_t
        self.set_proc = getattr(user, "SetWindowLongPtrW", user.SetWindowLongW)
        self.set_proc.argtypes = [pointer, ctypes.c_int, pointer]
        self.set_proc.restype = pointer
        user.SetWindowPos.argtypes = [pointer, pointer, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user.IsZoomed.argtypes = [pointer]
        user.GetWindowRect.argtypes = [pointer, ctypes.POINTER(wintypes.RECT)]
        user.MonitorFromWindow.argtypes = [pointer, wintypes.DWORD]
        user.MonitorFromWindow.restype = pointer
        user.GetMonitorInfoW.argtypes = [pointer, pointer]
        user.ReleaseCapture.argtypes = []
        user.ReleaseCapture.restype = wintypes.BOOL
        user.PostMessageW.argtypes = [pointer, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        user.PostMessageW.restype = wintypes.BOOL
        self.hwnd = user.GetParent(self.root.winfo_id())

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

        prototype = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, pointer, wintypes.UINT,
                                       ctypes.c_size_t, ctypes.c_ssize_t)

        @prototype
        def window_proc(hwnd, message, wparam, lparam):
            if message == 0x0083:  # WM_NCCALCSIZE: client fills the former caption.
                if wparam and user.IsZoomed(hwnd):
                    info = MonitorInfo()
                    info.size = ctypes.sizeof(info)
                    if user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
                        rect = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT))
                        rect[0] = info.work
                return 0
            if message == 0x0084:  # WM_NCHITTEST: preserve resizing on all eight edges.
                if not user.IsZoomed(hwnd):
                    rect = wintypes.RECT()
                    user.GetWindowRect(hwnd, ctypes.byref(rect))
                    x, y = ctypes.c_short(lparam & 0xffff).value, ctypes.c_short((lparam >> 16) & 0xffff).value
                    left, right = x < rect.left + 6, x >= rect.right - 6
                    top, bottom = y < rect.top + 6, y >= rect.bottom - 6
                    if top:
                        return 13 if left else 14 if right else 12
                    if bottom:
                        return 16 if left else 17 if right else 15
                    if left or right:
                        return 10 if left else 11
                return 1  # HTCLIENT: the Tk buttons handle the integrated caption.
            return user.CallWindowProcW(self.original, hwnd, message, wparam, lparam)

        self.callback = window_proc  # Keep the native callback alive until restoration.
        self.original = self.set_proc(self.hwnd, -4, ctypes.cast(self.callback, pointer))
        if not self.original:
            self.hwnd = None
            self.controls.pack_forget()
            return
        user.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 0x0027)  # FRAMECHANGED, no move/size/z-order.

    def on_destroy(self, event):
        if event.widget is not self.root:
            return
        if self.hwnd and self.original:
            self.set_proc(self.hwnd, -4, self.original)
            self.hwnd = None
