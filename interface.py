"""Interface Tkinter. Tokens colados ficam somente em memoria."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from browser_bridge import LocalBridge, open_chrome
from avatars import avatar_url, avatar_photo, download_avatar
from plan_editor import save_review
from review_pane import ReviewPane
from sync_anilist import (AniList, Crunchyroll, ROOT, STATUS_PT, SyncError, Cancelled,
                          apply_plan, build_plan, load_json, load_mappings,
                          new_run_folder, normalize_history, preview_live, write_preview, match_label, profile_label, save_json)


class Window:
    def __init__(self, root):
        self.root = root
        root.title("Crunchyroll → AniList")
        root.geometry(f"{min(1200, max(950, root.winfo_screenwidth()-80))}x"
                      f"{min(920, max(650, root.winfo_screenheight()-110))}")
        root.minsize(850, 650)
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.auth = {"cr": "", "al": ""}
        self.plan = None
        self.busy = False
        self.bridge = None
        self.closing = False
        self.folder = None
        self.save_timer = None
        self.operation = None
        self.active_batch = None
        self.identity_generation = 0
        self.avatar_urls = {"al": None, "cr": None}
        self.avatar_images = {}
        self.user = tk.StringVar(value="Detectado ao gerar a prévia")
        self.profile = tk.StringVar(value="Detectado ao gerar a prévia")
        self.history_file = tk.StringVar()
        self.status = tk.StringVar(value="Conecte pelo Chrome e gere uma prévia. Nenhuma alteração será feita nessa etapa.")
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Crunchyroll → AniList", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Histórico por API · temporadas e especiais separados · notas e avanços preservados",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 16))
        auth_frame = ttk.LabelFrame(outer, text="1. Acessos temporários", padding=12)
        auth_frame.pack(fill="x")
        self.auth_labels = {}
        self.option_widgets = []
        auto_row = ttk.Frame(auth_frame)
        auto_row.pack(fill="x", pady=(0, 10))
        self.connect_button = ttk.Button(auto_row, text="Conectar pelo Chrome", command=self.connect_chrome)
        self.connect_button.pack(side="left")
        install_button = ttk.Button(auto_row, text="Instalar extensão (uma vez)", command=self.install_extension)
        install_button.pack(side="left", padx=8)
        self.option_widgets.append(install_button)
        ttk.Label(auto_row, text="Usa o login já aberto no navegador").pack(side="left", padx=8)
        for service, name in (("cr", "Crunchyroll"), ("al", "AniList")):
            row = ttk.Frame(auth_frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=name, width=15).pack(side="left")
            ttk.Button(row, text="Colar acesso", command=lambda s=service: self.paste(s)).pack(side="left")
            ttk.Button(row, text="Digitar token", command=lambda s=service: self.token_dialog(s)).pack(side="left", padx=5)
            self.auth_labels[service] = ttk.Label(row, text="Não carregado")
            self.auth_labels[service].pack(side="left", padx=10)
        opts = ttk.Frame(auth_frame)
        opts.pack(fill="x", pady=(10, 0))
        opts.columnconfigure((0, 1), weight=1, uniform="accounts")
        self.avatar_canvases = {}
        for index, (service, title, variable) in enumerate((
            ("al", "AniList — destino", self.user), ("cr", "Crunchyroll — origem", self.profile))):
            card = ttk.LabelFrame(opts, text=title, padding=8)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 8) if index == 0 else 0)
            canvas = tk.Canvas(card, width=56, height=56, highlightthickness=0, background="white")
            canvas.pack(side="left", padx=(0, 10))
            self.avatar_canvases[service] = canvas
            ttk.Label(card, textvariable=variable, font=("Segoe UI", 11, "bold"),
                      wraplength=350).pack(side="left", fill="x", expand=True)
            self.reset_avatar(service)
        source = ttk.Frame(auth_frame)
        source.pack(fill="x", pady=(8, 0))
        ttk.Button(source, text="Importar histórico JSON", command=self.choose_file).pack(side="left")
        ttk.Label(source, textvariable=self.history_file).pack(side="left", padx=8)
        api_button = ttk.Button(source, text="Usar API", command=lambda: self.history_file.set(""))
        api_button.pack(side="right")
        self.option_widgets.append(api_button)
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=14)
        self.preview_button = ttk.Button(controls, text="2. Gerar prévia", command=self.preview)
        self.preview_button.pack(side="left")
        self.apply_button = ttk.Button(controls, text="3. Aplicar alterações", state="disabled", command=self.apply)
        self.apply_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(controls, text="Interromper", state="disabled", command=self.stop.set)
        self.cancel_button.pack(side="left")
        ttk.Button(controls, text="Ajuda", command=self.help).pack(side="right")
        ttk.Button(controls, text="Abrir pasta da execução", command=self.open_folder).pack(side="right", padx=8)
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=1020,
                                      font=("Segoe UI", 10, "bold"))
        self.status_label.pack(anchor="w", fill="x")
        outer.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(400, e.width)))
        self.bar = ttk.Progressbar(outer, mode="indeterminate")
        self.bar.pack(fill="x", pady=(8, 12))
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        self.review = ReviewPane(notebook, self.review_changed)
        notebook.add(self.review, text="Revisar plano")
        self.table = self.review.table
        self.pending = tk.Text(notebook, wrap="word", state="disabled", font=("Segoe UI", 10))
        notebook.add(self.pending, text="Pendências e itens ignorados")
        self.logs = tk.Text(notebook, wrap="word", state="disabled", font=("Consolas", 10))
        notebook.add(self.logs, text="Progresso")
        self.history_file.trace_add("write", lambda *_: self.invalidate())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.drain_timer = root.after(100, self.drain)

    def invalidate(self):
        self.plan = None
        self.active_batch = None
        self.apply_button.configure(state="disabled")
        if hasattr(self, "review"):
            self.review.clear()

    def clear_identities(self):
        self.identity_generation += 1
        self.avatar_urls = {"al": None, "cr": None}
        self.avatar_images.clear()
        for service in self.avatar_canvases:
            self.reset_avatar(service)
        self.user.set("Detectado ao gerar a prévia")
        self.profile.set("Detectado ao gerar a prévia")

    def show_identity(self, user, cr_profile):
        self.user.set(f"{user['name']} (ID {user['id']})")
        self.profile.set(profile_label(cr_profile))
        self.request_avatar("al", user)
        self.request_avatar("cr", cr_profile)

    def reset_avatar(self, service):
        canvas = self.avatar_canvases[service]
        canvas.delete("all")
        color = "#2b68b7" if service == "al" else "#dd6a17"
        canvas.create_oval(2, 2, 54, 54, fill=color, outline="")
        canvas.create_text(28, 28, text="AL" if service == "al" else "CR",
                           fill="white", font=("Segoe UI", 13, "bold"))

    def request_avatar(self, service, info):
        url = avatar_url(service, info)
        if url == self.avatar_urls.get(service):
            return
        self.avatar_urls[service] = url
        self.avatar_images.pop(service, None)
        self.reset_avatar(service)
        if not url:
            return
        generation = self.identity_generation
        def work():
            try:
                raw = download_avatar(url, service)
            except Exception:
                raw = None
            self.q.put(("avatar", generation, service, url, raw))
        threading.Thread(target=work, daemon=True).start()

    def receive_avatar(self, event):
        _, generation, service, url, raw = event
        if generation != self.identity_generation or self.avatar_urls.get(service) != url or not raw:
            return
        try:
            photo = avatar_photo(self.root, raw)
        except Exception:
            return
        self.avatar_images[service] = photo
        canvas = self.avatar_canvases[service]
        canvas.delete("all")
        canvas.create_image(28, 28, image=photo)

    def maybe_identify_accounts(self):
        if self.busy or self.bridge or not self.auth["al"]:
            return
        imported = bool(self.history_file.get())
        if not imported and not self.auth["cr"]:
            return
        auth = dict(self.auth)
        self.status.set("Identificando os nicks das contas conectadas…")
        def job():
            log = lambda text: self.q.put(("log", text))
            profile = ({"identity_source": "imported_history"} if imported else
                       Crunchyroll(auth["cr"], log=log, cancelled=self.stop.is_set).identify())
            user = AniList(auth["al"], log=log, cancelled=self.stop.is_set).identify()
            return user, profile
        self.run_worker(job, self.accounts_ready, kind="identity")

    def accounts_ready(self, accounts):
        self.show_identity(*accounts)
        self.status.set(f"Conectado: AniList {accounts[0]['name']} · "
                        f"Crunchyroll {profile_label(accounts[1])}. Clique em Gerar prévia.")

    def review_changed(self, plan, included):
        self.plan = plan
        self.apply_button.configure(text=f"Aplicar marcados ({len(included)})",
                                    state="normal" if included and not self.busy else "disabled")
        if not self.busy:
            self.status.set(f"Prévia: {len(included)} marcados de {len(plan['changes'])} itens restantes. "
                            "Você pode editar ou excluir linhas antes de aplicar.")
        if self.save_timer:
            self.root.after_cancel(self.save_timer)
        self.save_timer = self.root.after(250, self.persist_review)

    def persist_review(self):
        if self.save_timer:
            try:
                self.root.after_cancel(self.save_timer)
            except tk.TclError:
                pass
        self.save_timer = None
        if self.plan is None or not self.folder:
            return
        try:
            save_review(self.folder, self.plan, self.review.included, self.review.applied)
        except OSError:
            self.status.set("Não foi possível salvar a revisão. Confira a pasta antes de aplicar.")

    def clear_access(self):
        self.clear_identities()
        self.auth = {"cr": "", "al": ""}
        for label in self.auth_labels.values():
            label.configure(text="Não carregado")
        self.invalidate()

    def end_connection(self, clear=False):
        bridge, self.bridge = self.bridge, None
        if bridge:
            bridge.close()
        self.connect_button.configure(text="Conectar pelo Chrome", state="normal")
        self.preview_button.configure(state="normal" if not self.busy else "disabled")
        self.bar.stop()
        if clear:
            self.clear_access()

    def connect_chrome(self):
        if self.busy:
            return
        if self.bridge:
            self.end_connection(clear=True)
            self.status.set("Conexão cancelada.")
            return
        self.clear_access()
        bridge = LocalBridge(lambda service, value: self.q.put(("browser_access", bridge, service, value)))
        self.bridge = bridge
        url = bridge.start()
        self.connect_button.configure(text="Cancelar conexão")
        self.preview_button.configure(state="disabled")
        self.bar.start(15)
        self.status.set("Aguardando o Chrome. Instale a extensão uma vez; as abas de apoio carregarão os acessos.")
        try:
            open_chrome(url)
        except (SyncError, OSError):
            dialog = tk.Toplevel(self.root)
            dialog.title("Abrir conexão no Chrome")
            ttk.Label(dialog, text="Abra o Chrome no mesmo perfil da extensão e cole este endereço:",
                      padding=12).pack()
            entry = ttk.Entry(dialog, width=95)
            entry.insert(0, url)
            entry.configure(state="readonly")
            entry.pack(padx=12, pady=12)
            ttk.Button(dialog, text="Fechar", command=dialog.destroy).pack(pady=12)

    def install_extension(self):
        if self.busy or self.bridge:
            return
        folder = ROOT / "extensao_chrome"
        try:
            if os.name == "nt":
                os.startfile(folder)
            else:
                import webbrowser
                webbrowser.open(folder.as_uri())
            open_chrome("chrome://extensions")
        except (SyncError, OSError):
            pass
        messagebox.showinfo("Instalar extensão uma vez",
                            "No Chrome, abra chrome://extensions.\n"
                            "Ative Modo do desenvolvedor e clique em Carregar sem compactação.\n"
                            "Selecione a pasta extensao_chrome que veio no ZIP.\n\n"
                            "Depois clique em Conectar pelo Chrome no programa.\n\n"
                            "Pasta da extensão:\n" + str(folder))

    def paste(self, service):
        if self.busy:
            return
        if self.bridge:
            self.end_connection(clear=True)
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            messagebox.showerror("Área de transferência", "Copie a requisição ou o token primeiro.")
            return
        if not value:
            messagebox.showerror("Acesso vazio", "A área de transferência está vazia.")
            return
        self.auth[service] = value
        self.clear_identities()
        self.auth_labels[service].configure(text="Carregado somente em memória")
        self.invalidate()
        self.maybe_identify_accounts()

    def token_dialog(self, service):
        if self.busy:
            return
        if self.bridge:
            self.end_connection(clear=True)
        dialog = tk.Toplevel(self.root)
        dialog.title("Token temporário")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Token OAuth do AniList" if service == "al" else "Bearer token do Crunchyroll",
                  padding=12).pack()
        entry = ttk.Entry(dialog, show="*", width=65)
        entry.pack(padx=12, pady=6)
        entry.focus_set()
        def accept():
            self.auth[service] = entry.get().strip()
            self.clear_identities()
            self.auth_labels[service].configure(text="Carregado somente em memória")
            self.invalidate()
            dialog.destroy()
            self.maybe_identify_accounts()
        ttk.Button(dialog, text="Usar este token", command=accept).pack(pady=12)

    def choose_file(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[("Histórico JSON", "*.json"), ("Todos", "*.*")])
        if path:
            self.history_file.set(path)
            self.maybe_identify_accounts()

    def run_worker(self, job, callback, kind="preview"):
        self.operation = kind
        self.busy = True
        self.review.set_busy(True)
        self.connect_button.configure(state="disabled")
        self.stop.clear()
        for widget in self.option_widgets:
            widget.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.bar.start(15)
        def work():
            try:
                self.q.put(("done", callback, job()))
            except Exception as exc:
                self.q.put(("error", str(exc)))
        threading.Thread(target=work, daemon=False).start()

    def preview(self):
        if self.busy or self.bridge:
            return
        if not self.auth["al"] or (not self.history_file.get() and not self.auth["cr"]):
            messagebox.showerror("Acessos", "Carregue o acesso do AniList e o do Crunchyroll, ou importe o histórico JSON.")
            return
        auth = dict(self.auth)
        history = self.history_file.get()
        self.clear_identities()
        folder = new_run_folder()
        self.folder = folder
        self.invalidate()
        self.status.set("Consultando as APIs e preparando a prévia…")
        def job():
            log = lambda text: self.q.put(("log", text))
            al = AniList(auth["al"], log=log, cancelled=self.stop.is_set)
            mappings = load_mappings()
            if history:
                raw = load_json(history)
                groups = normalize_history(raw)
                viewer = al.identify()
                profile_info = {"identity_source": "imported_history"}
                self.q.put(("identity", viewer, profile_info))
                entries = al.collection()
                catalog = al.catalog(groups, mappings, entries)
                plan = build_plan(groups, entries, catalog, mappings, viewer)
                plan["cr_profile"] = profile_info
                write_preview(folder, plan, entries, raw)
                return plan
            cr = Crunchyroll(auth["cr"], log=log, cancelled=self.stop.is_set)
            return preview_live(cr, al, mappings, folder,
                                on_identity=lambda user, profile: self.q.put(("identity", user, profile)))
        self.run_worker(job, self.show_plan)

    def show_plan(self, plan):
        self.show_identity(plan["user"], plan.get("cr_profile"))
        self.plan = plan
        self.review.load(plan)
        text = json.dumps({"pendências": plan["pending"], "ignorados": plan["ignored"]},
                          ensure_ascii=False, indent=2)
        self.pending.configure(state="normal")
        self.pending.delete("1.0", "end")
        self.pending.insert("end", text)
        self.pending.configure(state="disabled")
        s = plan["summary"]
        self.status.set(f"Prévia pronta: {s['new']} adições, {s['updated']} atualizações, "
                        f"{s['pending']} pendências. Nenhuma alteração remota aplicada.")
        self.apply_button.configure(text=f"Aplicar marcados ({len(self.review.included)})",
                                    state="normal" if self.review.included else "disabled")

    def apply(self):
        if self.busy or self.plan is None:
            return
        plan = self.review.subset()
        count = len(plan["changes"])
        if not count:
            return
        if not messagebox.askyesno("Aplicar itens marcados",
                                  f"Aplicar somente os {count} itens marcados em {plan['user']['name']}?\n"
                                  f"Origem Crunchyroll: {profile_label(plan.get('cr_profile'))}\n\n"
                                  "Os itens não marcados continuam na prévia para outro lote."):
            return
        folder = self.folder / "aplicacoes" / new_run_folder().name
        try:
            save_review(self.folder, self.plan, self.review.included, self.review.applied)
            save_json(folder / "plano.json", plan)
        except OSError as exc:
            messagebox.showerror("Não foi possível salvar o lote", str(exc))
            return
        self.active_batch = {"plan": plan, "folder": folder}
        auth = self.auth["al"]
        self.status.set(f"Aplicando {count} itens marcados e verificando o resultado…")
        def job():
            al = AniList(auth, log=lambda text: self.q.put(("log", text)), cancelled=self.stop.is_set)
            return apply_plan(al, plan, folder)
        self.run_worker(job, self.show_result, kind="apply")

    def show_result(self, result):
        ids = {c["mediaId"] for c in self.active_batch["plan"]["changes"]}
        self.review.consume(ids, result.get("confirmed_entries", []))
        self.persist_review()
        remaining = len(self.plan["changes"])
        self.show_identity(result["user"], self.plan.get("cr_profile"))
        self.status.set(f"Lote verificado: {result['applied']} alterações; "
                        f"{len(result['skipped'])} já aplicadas/preservadas. "
                        f"{remaining} itens continuam no plano para outro lote. "
                        f"Total na lista: {result['total_after']}.")
        self.active_batch = None

    def drain(self):
        try:
            while True:
                event = self.q.get_nowait()
                if event[0] == "log":
                    self.logs.configure(state="normal")
                    self.logs.insert("end", event[1] + "\n")
                    self.logs.see("end")
                    self.logs.configure(state="disabled")
                elif event[0] == "avatar":
                    self.receive_avatar(event)
                elif event[0] == "identity":
                    self.show_identity(event[1], event[2])
                elif event[0] == "browser_access":
                    if self.bridge is not event[1]:
                        continue
                    service, value = event[2], event[3]
                    self.auth[service] = value
                    self.auth_labels[service].configure(text="Recebido do Chrome em memória")
                    self.invalidate()
                    if all(self.auth.values()):
                        self.end_connection()
                        self.maybe_identify_accounts()
                else:
                    self.busy = False
                    self.review.set_busy(False)
                    self.connect_button.configure(state="normal")
                    for widget in self.option_widgets:
                        widget.configure(state="normal")
                    self.bar.stop()
                    self.preview_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if self.closing:
                        self.destroy_root()
                        return
                    if event[0] == "done":
                        event[1](event[2])
                    else:
                        self.invalidate()
                        self.status.set("Execução interrompida. Gere outra prévia para continuar."
                                        if self.operation == "apply" else "Não foi possível concluir a consulta.")
                        if not self.closing:
                            messagebox.showerror("Não foi possível concluir", event[1])
        except queue.Empty:
            pass
        if self.bridge and self.bridge.expired:
            self.end_connection(clear=True)
            self.status.set("A conexão expirou. Confira a extensão e os logins e clique em Conectar pelo Chrome novamente.")
        self.drain_timer = self.root.after(100, self.drain)

    def help(self):
        path = ROOT / "LEIA-ME.md"
        if os.name == "nt":
            try:
                os.startfile(path)
            except OSError:
                import subprocess
                subprocess.Popen(["notepad.exe", str(path)])
        else:
            import webbrowser
            webbrowser.open(path.as_uri())

    def open_folder(self):
        folder = self.folder if self.folder and self.folder.exists() else ROOT
        if os.name == "nt":
            os.startfile(folder)
        else:
            import webbrowser
            webbrowser.open(Path(folder).as_uri())

    def destroy_root(self):
        if self.save_timer:
            self.root.after_cancel(self.save_timer)
        try:
            self.root.after_cancel(self.drain_timer)
        except tk.TclError:
            pass
        self.identity_generation += 1
        self.auth.clear()
        self.avatar_images.clear()
        self.root.destroy()

    def close(self):
        self.persist_review()
        if self.bridge:
            self.end_connection(clear=True)
        if self.busy:
            self.stop.set()
            self.closing = True
            self.status.set("Interrompendo após conferir a requisição em andamento…")
        else:
            self.destroy_root()


def start_gui():
    root = tk.Tk()
    Window(root)
    root.mainloop()
