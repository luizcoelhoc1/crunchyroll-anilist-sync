"""Tabela de revisao: marcacao persistente, edicao e exclusao reversivel."""
import copy
import tkinter as tk
from tkinter import messagebox, ttk

from plan_editor import edit_change, refreshed, remove_changes, selected_plan, consume_verified
from sync_anilist import STATUS_PT, SyncError, match_label


class ReviewPane(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.on_change = on_change
        self.plan = None
        self.original = None
        self.included = set()
        self.applied = set()
        self.busy = False
        self.buttons = []
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(4, 8))
        for text, command in (
            ("Marcar todos", lambda: self.mark_all(True)),
            ("Desmarcar todos", lambda: self.mark_all(False)),
            ("Somente selecionados", self.only_selection),
            ("Editar alvo", self.edit_selected),
            ("Excluir do plano", self.exclude_selected),
            ("Restaurar plano", self.restore)):
            button = ttk.Button(bar, text=text, command=command, state="disabled")
            button.pack(side="left", padx=(0, 5))
            self.buttons.append(button)
        self.detail = tk.StringVar(value="Gere uma prévia para revisar.")
        ttk.Label(self, textvariable=self.detail, wraplength=1080).pack(anchor="w", pady=(0, 8))
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(frame, columns=("include", "title", "before", "after", "match"),
                                  show="headings", selectmode="extended")
        for key, label, width in (("include", "Aplicar", 62), ("title", "Anime / temporada", 420),
                                  ("before", "Antes", 150), ("after", "Depois", 150),
                                  ("match", "Correspondência", 150)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, stretch=key == "title",
                              anchor="center" if key == "include" else "w")
        self.table.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.tag_configure("edited", foreground="#005c9e")
        self.table.bind("<Button-1>", self.click)
        self.table.bind("<space>", self.toggle_selected)
        self.table.bind("<Double-1>", lambda e: self.edit_selected()
                        if self.table.identify_column(e.x) != "#1" else "break")
        self.table.bind("<Delete>", lambda _: self.exclude_selected())

    def clear(self):
        self.plan = self.original = None
        self.included.clear()
        self.applied.clear()
        self.table.delete(*self.table.get_children())
        self.detail.set("Gere uma prévia para revisar.")
        self.set_busy(self.busy)

    def load(self, plan):
        self.original = copy.deepcopy(plan)
        self.plan = copy.deepcopy(plan)
        self.applied.clear()
        self.included = {c["mediaId"] for c in plan["changes"]}
        self.refresh()

    def set_busy(self, value):
        self.busy = value
        for button in self.buttons:
            button.configure(state="disabled" if value or self.plan is None else "normal")

    def refresh(self):
        if self.plan is None:
            return
        refreshed(self.plan)
        old_selection = set(self.table.selection())
        self.table.delete(*self.table.get_children())
        valid = {c["mediaId"] for c in self.plan["changes"]}
        self.included.intersection_update(valid)
        for c in self.plan["changes"]:
            b, a, mid = c.get("before"), c["after"], c["mediaId"]
            before = f"{STATUS_PT[b['status']]} · {b['progress']}" if b else "Ausente"
            after = f"{STATUS_PT[a['status']]} · {a['progress']}"
            if c.get("user_edited"):
                after += " *"
            elif c.get("continuation"):
                after += " (restante)"
            self.table.insert("", "end", iid=str(mid),
                              values=("☑" if mid in self.included else "☐", c["title"],
                                      before, after, match_label(c)),
                              tags=("edited",) if c.get("user_edited") else ())
        keep = old_selection.intersection(map(str, valid))
        if keep:
            self.table.selection_set(*keep)
        self.detail.set(f"{len(self.included)} marcados de {len(valid)} itens restantes. "
                        "Clique na caixa para marcar. Ctrl/Shift selecionam várias linhas. "
                        "* alvo editado. Excluir retira apenas do plano.")
        self.set_busy(self.busy)
        self.on_change(self.plan, set(self.included))

    def selected_ids(self):
        return {int(i) for i in self.table.selection()}

    def click(self, event):
        if self.busy or self.plan is None or self.table.identify_column(event.x) != "#1":
            return
        row = self.table.identify_row(event.y)
        if row:
            mid = int(row)
            self.included.symmetric_difference_update({mid})
            self.refresh()
            return "break"

    def toggle_selected(self, event=None):
        if not self.busy and self.plan is not None:
            self.included.symmetric_difference_update(self.selected_ids())
            self.refresh()
        return "break"

    def mark_all(self, value):
        if self.busy or self.plan is None:
            return
        self.included = {c["mediaId"] for c in self.plan["changes"]} if value else set()
        self.refresh()

    def only_selection(self):
        if self.busy or self.plan is None:
            return
        self.included = self.selected_ids()
        self.refresh()

    def exclude_selected(self):
        if self.busy or self.plan is None:
            return
        ids = self.selected_ids()
        if ids:
            self.plan = remove_changes(self.plan, ids)
            self.included.difference_update(ids)
            self.refresh()

    def restore(self):
        if self.busy or self.original is None:
            return
        self.plan = copy.deepcopy(self.original)
        self.plan["changes"] = [c for c in self.plan["changes"] if c["mediaId"] not in self.applied]
        self.included = {c["mediaId"] for c in self.plan["changes"]}
        self.refresh()

    def consume(self, media_ids, confirmed_entries):
        ids = set(media_ids)
        self.plan, self.original, finished = consume_verified(
            self.plan, self.original, ids, confirmed_entries)
        self.applied.update(finished)
        self.included.difference_update(ids)
        self.refresh()

    def subset(self):
        if self.plan is None:
            raise SyncError("Gere uma prévia primeiro.")
        return selected_plan(self.plan, self.included)

    def edit_selected(self):
        if self.busy or self.plan is None:
            return
        ids = self.selected_ids()
        if len(ids) != 1:
            messagebox.showinfo("Editar alvo", "Selecione uma linha para editar o status e o progresso.")
            return
        mid = next(iter(ids))
        change = next(c for c in self.plan["changes"] if c["mediaId"] == mid)
        before = change.get("before") or {}
        ceiling = (change.get("suggested_after") or change["after"])["progress"]
        dialog = tk.Toplevel(self)
        dialog.title("Editar alteração do plano")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        outer = ttk.Frame(dialog, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=change["title"], font=("Segoe UI", 12, "bold"), wraplength=520).pack(anchor="w")
        ttk.Label(outer, text=f"Progresso atual: {before.get('progress', 0)} · "
                             f"Confirmado pelo histórico: {ceiling} · Total: {change.get('episodes') or '?'}",
                  wraplength=520).pack(anchor="w", pady=(8, 12))
        label = tk.StringVar(value=STATUS_PT[change["after"]["status"]])
        status = ttk.Combobox(outer, textvariable=label, values=list(STATUS_PT.values()), state="readonly", width=28)
        status.pack(anchor="w", pady=5)
        progress = tk.StringVar(value=str(change["after"]["progress"]))
        ttk.Label(outer, text="Episódios no alvo:").pack(anchor="w")
        spin = ttk.Spinbox(outer, from_=before.get("progress", 0), to=ceiling,
                           textvariable=progress, width=12)
        spin.pack(anchor="w", pady=(4, 12))
        ttk.Label(outer, text="A edição vale somente para esta prévia. Notas, datas e listas pessoais são preservadas.",
                  wraplength=520).pack(anchor="w", pady=(0, 12))

        def accept():
            try:
                target_status = next(k for k, v in STATUS_PT.items() if v == label.get())
                updated = edit_change(self.plan, mid, target_status, int(progress.get()))
            except (ValueError, StopIteration, SyncError) as exc:
                messagebox.showerror("Alvo inválido", str(exc), parent=dialog)
                return
            self.plan = updated
            self.refresh()
            dialog.destroy()
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Salvar no plano", command=accept).pack(side="left")
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="left", padx=8)
