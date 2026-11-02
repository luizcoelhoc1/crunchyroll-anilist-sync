"""Dropdowns planos, sem a moldura do menu nativo do Windows."""
import tkinter as tk
from tkinter import ttk

from desktop_theme import PANEL


class MenuButton(ttk.Button):
    def __init__(self, parent, *, entries, **kwargs):
        super().__init__(parent, command=self.toggle, **kwargs)
        self.entries = entries
        self.popup = None
        self.bind("<Down>", lambda event: self.toggle())
        self.bind("<Destroy>", lambda event: self.dismiss())

    def dismiss(self, restore_focus=False):
        popup, self.popup = self.popup, None
        if popup is not None:
            popup.grab_release()
            popup.destroy()
        if restore_focus and self.winfo_exists():
            self.focus_set()

    def toggle(self):
        if self.instate(["disabled"]):
            return
        if self.popup is not None:
            self.dismiss(restore_focus=True)
            return
        popup = self.popup = tk.Toplevel(self)
        popup.withdraw()
        popup.transient(self.winfo_toplevel())
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(background=PANEL, borderwidth=0)
        rows = []

        def invoke(command):
            self.dismiss(restore_focus=True)
            command()

        for entry in self.entries:
            if entry is None:
                continue
            label, command = entry
            row = ttk.Button(popup, text=label, style="MenuItem.TButton",
                             command=lambda action=command: invoke(action))
            row.pack(fill="x", padx=4, pady=2)
            rows.append(row)
        if not rows:
            self.dismiss()
            return

        def move(delta):
            focus = popup.focus_get()
            index = rows.index(focus) if focus in rows else 0
            rows[(index + delta) % len(rows)].focus_set()
            return "break"

        def outside(event):
            x, y = event.x_root, event.y_root
            if not (popup.winfo_rootx() <= x < popup.winfo_rootx() + popup.winfo_width()
                    and popup.winfo_rooty() <= y < popup.winfo_rooty() + popup.winfo_height()):
                self.dismiss(restore_focus=True)
                return "break"

        popup.bind("<Up>", lambda event: move(-1))
        popup.bind("<Down>", lambda event: move(1))
        popup.bind("<Escape>", lambda event: self.dismiss(restore_focus=True))
        popup.bind("<Tab>", lambda event: self.dismiss(restore_focus=True))
        popup.bind("<ButtonPress-1>", outside)
        popup.bind("<FocusOut>", lambda event: popup.after_idle(check_focus))

        def check_focus():
            if self.popup is popup and popup.focus_get() not in rows:
                self.dismiss()

        popup.update_idletasks()
        width = max(self.winfo_width(), popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        x = min(self.winfo_rootx(), popup.winfo_screenwidth() - width)
        y = self.winfo_rooty() + self.winfo_height()
        if y + height > popup.winfo_screenheight():
            y = self.winfo_rooty() - height
        popup.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        popup.deiconify()
        popup.lift()
        popup.grab_set()
        rows[0].focus_force()
