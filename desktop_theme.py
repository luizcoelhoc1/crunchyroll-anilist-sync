"""Tema escuro da interface desktop, sem dependências adicionais."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

BG = "#1f1f1f"
SIDEBAR = "#181818"
PANEL = "#252526"
FIELD = "#2b2b2b"
BORDER = "#353535"
TEXT = "#e6e6e6"
MUTED = "#9da5b4"
ACCENT = "#007acc"
BLUE = "#69b7ff"
GREEN = "#89d185"


def install_dark_theme(root):
    root.configure(background=BG)
    tkfont.nametofont("TkDefaultFont", root).configure(family="Segoe UI", size=10)
    tkfont.nametofont("TkTextFont", root).configure(family="Segoe UI", size=10)
    root.option_add("*Toplevel.background", BG)
    root.option_add("*Text.background", BG)
    root.option_add("*Text.font", ("Segoe UI", 10))
    root.option_add("*Text.foreground", TEXT)
    root.option_add("*Text.insertBackground", TEXT)
    root.option_add("*Text.selectBackground", "#264f78")
    root.option_add("*Text.selectForeground", "#ffffff")
    root.option_add("*Text.highlightBackground", BORDER)
    root.option_add("*Text.highlightColor", ACCENT)
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 0)
    root.option_add("*Text.padX", 12)
    root.option_add("*Text.padY", 10)
    root.option_add("*Listbox.background", FIELD)
    root.option_add("*Listbox.foreground", TEXT)
    root.option_add("*Listbox.selectBackground", "#264f78")
    root.option_add("*Menu.background", PANEL)
    root.option_add("*Menu.foreground", TEXT)
    root.option_add("*Menu.activeBackground", "#094771")
    root.option_add("*Menu.activeForeground", "#ffffff")
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.activeBorderWidth", 0)
    root.option_add("*Menu.relief", "flat")
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10),
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    focuscolor=ACCENT, troughcolor=SIDEBAR, selectbackground="#264f78")
    style.configure("TFrame", background=BG)
    style.configure("Rail.TFrame", background=SIDEBAR)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Rail.TLabel", background=SIDEBAR, foreground=TEXT)
    style.configure("RailMuted.TLabel", background=SIDEBAR, foreground=MUTED, font=("Segoe UI", 9))
    style.configure("Eyebrow.TLabel", foreground=BLUE, font=("Segoe UI", 9, "bold"))
    style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
    style.configure("TLabelframe", background=BG, bordercolor=BG, relief="flat", borderwidth=0)
    style.configure("TLabelframe.Label", foreground=MUTED, background=BG, font=("Segoe UI", 9, "bold"))
    style.configure("TButton", padding=(12, 8), background=FIELD, foreground=TEXT, borderwidth=0,
                    bordercolor=FIELD, relief="flat", focusthickness=0)
    style.map("TButton", background=[("disabled", "#242424"), ("pressed", "#404040"), ("active", "#363636")],
              foreground=[("disabled", "#737373")], bordercolor=[("focus", ACCENT)])
    style.configure("Primary.TButton", background=ACCENT, bordercolor=ACCENT, foreground="#ffffff")
    style.map("Primary.TButton", background=[("disabled", "#263340"), ("pressed", "#005c99"), ("active", "#168cda")],
              foreground=[("disabled", "#8095a7")], bordercolor=[("disabled", "#263340"), ("focus", BLUE)])
    style.configure("Small.TButton", padding=(9, 5), font=("Segoe UI", 9))
    style.configure("Top.TButton", background=SIDEBAR, padding=(10, 7))
    style.map("Top.TButton", background=[("active", PANEL), ("focus", PANEL)])
    style.configure("Caption.TButton", background=SIDEBAR, padding=(10, 9), font=("Segoe UI", 11))
    style.map("Caption.TButton", background=[("active", FIELD), ("focus", FIELD)])
    style.configure("Close.TButton", background=SIDEBAR, padding=(10, 9), font=("Segoe UI", 11))
    style.map("Close.TButton", background=[("active", "#c42b1c"), ("focus", "#c42b1c")])
    style.configure("MenuItem.TButton", background=PANEL, padding=(12, 8), anchor="w")
    style.map("MenuItem.TButton", background=[("active", "#094771"), ("focus", "#094771")])
    style.configure("Nav.TButton", background=SIDEBAR, bordercolor=SIDEBAR, padding=(14, 12), anchor="w", foreground=MUTED)
    style.map("Nav.TButton", background=[("active", PANEL)], foreground=[("active", TEXT)])
    style.configure("Active.Nav.TButton", background="#203448", bordercolor="#203448", foreground="#ffffff")
    style.map("Active.Nav.TButton", background=[("active", "#26415a")], foreground=[("active", "#ffffff")])
    style.configure("Top.TMenubutton", background=SIDEBAR, foreground=TEXT, arrowcolor=MUTED,
                    padding=(10, 7), relief="flat", borderwidth=0)
    style.map("Top.TMenubutton", background=[("active", PANEL)])
    style.configure("Action.TMenubutton", background=FIELD, foreground=TEXT, arrowcolor=MUTED,
                    padding=(9, 5), relief="flat", borderwidth=0, font=("Segoe UI", 9))
    style.map("Action.TMenubutton", background=[("active", "#363636")], foreground=[("disabled", "#737373")])
    style.configure("TCheckbutton", padding=(0, 5), background=BG, foreground=MUTED,
                    indicatorbackground=FIELD, indicatorforeground=TEXT)
    style.map("TCheckbutton", background=[("active", BG)], foreground=[("disabled", "#737373"), ("active", TEXT)],
              indicatorbackground=[("selected", ACCENT), ("active", "#444444")])
    for control in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(control, fieldbackground=FIELD, foreground=TEXT, background=FIELD,
                        insertcolor=TEXT, bordercolor=BORDER, padding=7, arrowsize=14, arrowcolor=TEXT)
        style.map(control, fieldbackground=[("readonly", FIELD), ("disabled", PANEL)],
                  foreground=[("disabled", MUTED), ("readonly", TEXT)], bordercolor=[("focus", ACCENT)])
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 8))
    style.configure("TNotebook.Tab", background=SIDEBAR, foreground=MUTED, padding=(18, 10), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", PANEL), ("active", FIELD)],
              foreground=[("selected", TEXT), ("active", TEXT)])
    style.configure("Treeview", background=BG, fieldbackground=BG, foreground=TEXT, borderwidth=0,
                    rowheight=38, font=("Segoe UI", 10))
    style.configure("Treeview.Heading", background=PANEL, foreground=MUTED, padding=(10, 10),
                    relief="flat", font=("Segoe UI", 9, "bold"), borderwidth=0)
    style.map("Treeview", background=[("selected", "#264f78")], foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", FIELD)])
    style.configure("TScrollbar", background="#424242", troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, arrowsize=12, relief="flat")
    style.map("TScrollbar", background=[("active", "#626262")])
    style.configure("TSeparator", background=BORDER)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG,
                    borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT, thickness=3)
    # Keep selection visible through background color, without native bevels or focus rings.
    style.layout("TButton", [("Button.border", {"sticky": "nswe", "children": [
        ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})]})])
    style.layout("Top.TMenubutton", [("Menubutton.padding", {"sticky": "nswe", "children": [
        ("Menubutton.label", {"sticky": "nswe"})]})])
    style.layout("TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    style.layout("TNotebook.Tab", [("Notebook.tab", {"sticky": "nswe", "children": [
        ("Notebook.padding", {"sticky": "nswe", "children": [("Notebook.label", {"sticky": "nswe"})]})]})])
    for option in ("bordercolor", "lightcolor", "darkcolor"):
        style.map("TNotebook.Tab", **{option: [("selected", PANEL), ("active", FIELD), ("!selected", SIDEBAR)]})
    for element in ("TNotebook", "Treeview", "Horizontal.TProgressbar", "TScrollbar"):
        style.configure(element, lightcolor=BG, darkcolor=BG, bordercolor=BG, borderwidth=0)
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.map("TButton", background=[("disabled", "#242424"), ("pressed", "#404040"),
                                    ("active", "#363636"), ("focus", "#363636")])
    return style


def dark_titlebar(window):
    """Usa a decoração escura do Windows quando disponível."""
    import os
    if os.name != "nt":
        return
    try:
        import ctypes
        value = ctypes.c_int(1)
        user = ctypes.windll.user32
        user.GetParent.argtypes = [ctypes.c_void_p]
        user.GetParent.restype = ctypes.c_void_p
        hwnd = user.GetParent(window.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(value), 4)
    except (OSError, AttributeError, tk.TclError):
        pass


def center_dialog(dialog, parent):
    """Place app dialogs inside the owning window, including on secondary monitors."""
    dialog.update_idletasks()
    owner = parent.winfo_toplevel()
    width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
    x = owner.winfo_rootx() + max(0, (owner.winfo_width() - width) // 2)
    y = owner.winfo_rooty() + max(0, (owner.winfo_height() - height) // 2)
    dialog.geometry(f"+{x}+{y}")
