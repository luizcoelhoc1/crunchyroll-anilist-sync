"""Interface Tkinter com login no navegador e sessões protegidas no Windows."""
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from browser_bridge import LocalBridge, open_chrome
from browser_login import login_crunchyroll, cr_record_from_fetch
from cr_direct_login import login_with_password
from oauth_login import login_anilist, open_regular_browser
from oauth_service import login_via_service
from app_config import load_anilist_config
from chrome_profile import ChromeSetupRequired, open_connection_settings
from extension_setup import show_extension_setup
from session_store import SessionStore, CrunchyrollSession, ClientSecretStore
from avatars import avatar_url, avatar_photo, download_avatar
from plan_editor import save_review
from desktop_layout import build_workspace
from desktop_theme import center_dialog
from app_paths import DATA_ROOT
from sync_anilist import (AniList, Crunchyroll, ROOT, STATUS_PT, SyncError, Cancelled,
                          apply_plan, build_plan, load_json, load_mappings,
                          new_run_folder, normalize_history, preview_live, write_preview, match_label, profile_label, save_json)


class Window:
    def __init__(self, root):
        self.root = root
        root.title("Crunchyroll → AniList")
        root.geometry(f"{min(1380, max(1050, root.winfo_screenwidth()-100))}x"
                      f"{min(940, max(720, root.winfo_screenheight()-110))}")
        root.minsize(1050, 720)
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.auth = {"cr": "", "al": ""}
        self.session_store = SessionStore()
        self.client_secret_store = ClientSecretStore()
        self.anilist_client_credentials = None
        self.session_records = {}
        self.keep_sessions = os.name == "nt"
        self.storage_warning = ""
        self.plan = None
        self.busy = False
        self.logged_in = False
        self.token_mode = False
        self.bridge = None
        self.closing = False
        self.folder = None
        self.save_timer = None
        self.operation = None
        self.active_batch = None
        self.identity_generation = 0
        self.avatar_urls = {"al": None, "cr": None}
        self.avatar_images = {}
        self.user = tk.StringVar(value="Não conectado")
        self.profile = tk.StringVar(value="Não conectado")
        self.history_file = tk.StringVar()
        self.status = tk.StringVar(value="Autorize o AniList no seu Chrome habitual e conecte o Crunchyroll; depois gere uma prévia.")
        build_workspace(self)
        self.history_file.trace_add("write", lambda *_: self.invalidate())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_login_ui()
        self.drain_timer = root.after(100, self.drain)
        self.restore_timer = root.after(200, self.restore_sessions)

    def save_session(self, service, record):
        self.session_records[service] = dict(record)
        if self.keep_sessions:
            try:
                self.session_store.put(service, record)
                self.storage_warning = ""
            except (OSError, SyncError):
                self.storage_warning = "Não foi possível salvar o login protegido. Os acessos continuam nesta execução."
                self.q.put(("log", self.storage_warning))

    def change_remember(self):
        value = self.remember.get()
        try:
            if value:
                for service, record in self.session_records.items():
                    self.session_store.put(service, record)
            else:
                self.session_store.clear()
        except (OSError, SyncError) as exc:
            self.remember.set(self.keep_sessions)
            messagebox.showerror("Login salvo", str(exc))
            return
        self.keep_sessions = value
        self.status.set("Os novos logins serão protegidos pelo Windows." if value else
                        "Login salvo removido deste computador. Os acessos atuais ficam só em memória.")

    def restore_sessions(self):
        self.restore_timer = None
        if self.busy or self.closing or not self.keep_sessions:
            return
        try:
            records = self.session_store.load()
            al = records.get("al", {})
            if isinstance(al, dict) and float(al.get("expires_at", 0)) > time.time() + 60:
                self.auth["al"] = al["access_token"]
                self.session_records["al"] = al
                self.session_labels["al"].configure(text="AniList: login salvo")
            elif al:
                self.session_labels["al"].configure(text="AniList: autorize novamente (acesso expirado)")
            if records.get("cr"):
                self.auth["cr"] = CrunchyrollSession(records["cr"], lambda record: self.save_session("cr", record))
                self.session_records["cr"] = records["cr"]
                self.session_labels["cr"].configure(text="Crunchyroll: login salvo")
        except (OSError, SyncError, ValueError, TypeError, KeyError):
            self.status.set("Não foi possível restaurar todos os acessos. Entre novamente nas contas indicadas.")
        self.maybe_identify_accounts()

    def configure_anilist(self, authorize=False):
        if self.busy or self.bridge:
            return
        try:
            config = load_anilist_config()
            client_id = config.client_id
        except SyncError as exc:
            messagebox.showerror("Configuração AniList", str(exc))
            return
        if config.auth_service_url:
            messagebox.showinfo("Configuração AniList", "O login está configurado pelo serviço de autorização.\n"
                                "Não é necessário informar um Client Secret neste computador.")
            return
        if config.client_secret:
            messagebox.showinfo("Configuração AniList", "O aplicativo AniList já está configurado pelo .env "
                                "ou pelas variáveis de ambiente. Para alterar o Client Secret, edite "
                                "ANILIST_CLIENT_SECRET nessa configuração.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Configurar aplicativo AniList")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text=f"Client Secret do aplicativo AniList {client_id}",
                  font=("Segoe UI", 11, "bold"), padding=12).pack(anchor="w")
        ttk.Label(dialog, text="Copie o Client Secret do mesmo aplicativo no cadastro do AniList e cole aqui.\n"
                              "O segredo é enviado somente ao AniList para concluir a autorização.",
                  padding=(12, 0)).pack(anchor="w")
        ttk.Button(dialog, text="Abrir cadastro do AniList", command=lambda: open_regular_browser(
            "https://anilist.co/settings/developer")).pack(anchor="w", padx=12, pady=8)
        entry = ttk.Entry(dialog, show="*", width=65)
        entry.pack(padx=12, pady=6)
        entry.focus_set()
        cached = self.anilist_client_credentials
        if cached and cached[0] == client_id:
            entry.insert(0, cached[1])
        else:
            try:
                current = self.client_secret_store.get(client_id)
                if current:
                    entry.insert(0, current)
            except (OSError, SyncError):
                pass
        remember_secret = tk.BooleanVar(value=os.name == "nt" and self.keep_sessions)
        check = ttk.Checkbutton(dialog, text="Guardar esta configuração protegida pelo Windows",
                                variable=remember_secret)
        check.pack(anchor="w", padx=12, pady=6)
        if os.name != "nt":
            check.configure(state="disabled")

        def accept():
            secret = entry.get().strip()
            if not secret or len(secret) > 4096 or any(c in secret for c in "\r\n\x00"):
                messagebox.showerror("AniList", "Cole o Client Secret do aplicativo neste campo.", parent=dialog)
                return
            try:
                if remember_secret.get():
                    self.client_secret_store.save(client_id, secret)
                else:
                    self.client_secret_store.clear()
            except (OSError, SyncError):
                messagebox.showerror("AniList", "Não foi possível guardar a configuração protegida. "
                                     "Desmarque a opção para usar só nesta execução.", parent=dialog)
                return
            self.anilist_client_credentials = (client_id, secret)
            entry.delete(0, "end")
            dialog.destroy()
            if authorize:
                self.sign_in("al")
            else:
                self.status.set("Aplicativo AniList configurado. Clique em Autorizar AniList.")

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=12, pady=12)
        ttk.Button(actions, text="Salvar e autorizar" if authorize else "Salvar configuração",
                   command=accept).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="right")

    def show_chrome_setup(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Conectar ao seu perfil do Chrome")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Use seu Chrome normal, sem instalar extensão", padding=12,
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(dialog, text="1. Abra a configuração abaixo no perfil do Chrome que deseja usar.\n"
                              "2. Ative a depuração remota em chrome://inspect/#remote-debugging.\n"
                              "3. Volte aqui, tente novamente e permita a conexão quando o Chrome pedir.\n\n"
                              "Esse recurso do Chrome 144+ permite acesso de depuração ao perfil. "
                              "O sincronizador acompanha apenas a aba de login que ele cria e mantém seu navegador aberto.",
                  padding=(12, 0), wraplength=600).pack(anchor="w")
        def settings():
            try:
                open_connection_settings()
            except (OSError, SyncError) as exc:
                messagebox.showerror("Chrome", str(exc), parent=dialog)
        def retry():
            dialog.destroy()
            self.sign_in("cr", browser_mode="current")
        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=12, pady=12)
        ttk.Button(actions, text="Abrir configuração do Chrome", command=settings).pack(side="left")
        ttk.Button(actions, text="Tentar novamente", command=retry).pack(side="left", padx=8)
        ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="right")

    def show_cr_password_login(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Entrar no Crunchyroll")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Entre na sua conta Crunchyroll", padding=12,
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(dialog, text="A senha é enviada somente ao Crunchyroll e não é salva.\n"
                              "Depois de entrar, escolha o perfil que deseja sincronizar.",
                  padding=(12, 0)).pack(anchor="w")
        ttk.Label(dialog, text="E-mail").pack(anchor="w", padx=12, pady=(10, 0))
        email = ttk.Entry(dialog, width=48)
        email.pack(padx=12, pady=4)
        ttk.Label(dialog, text="Senha").pack(anchor="w", padx=12)
        password = ttk.Entry(dialog, show="*", width=48)
        password.pack(padx=12, pady=4)
        email.focus_set()

        def discard():
            email.delete(0, "end")
            password.delete(0, "end")
            dialog.destroy()

        def submit():
            if self.busy or self.bridge:
                return
            credentials = [email.get().strip(), password.get()]
            if not credentials[0] or not credentials[1]:
                credentials.clear()
                messagebox.showerror("Crunchyroll", "Preencha e-mail e senha.", parent=dialog)
                return
            discard()
            self.persist_review()
            self.invalidate()
            self.clear_identities()
            self.set_logged_in(False)
            self.status.set("Entrando no Crunchyroll e consultando os perfis…")
            def job():
                address, secret = credentials
                credentials.clear()
                try:
                    return login_with_password(address, secret, self.stop.is_set)
                finally:
                    address = secret = None
            self.run_worker(job, self.show_cr_profiles, kind="login")

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=12, pady=12)
        ttk.Button(actions, text="Entrar", command=submit).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=discard).pack(side="right")
        dialog.bind("<Return>", lambda event: submit())
        dialog.protocol("WM_DELETE_WINDOW", discard)

    def show_cr_profiles(self, pending):
        if self.closing or self.stop.is_set():
            pending.clear()
            self.status.set("Login Crunchyroll cancelado.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Escolher perfil Crunchyroll")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Qual perfil você quer sincronizar?", padding=12).pack(anchor="w")
        choices = ttk.Combobox(dialog, state="readonly", width=48,
                              values=[p["name"] for p in pending.profiles])
        choices.pack(padx=12, pady=4)
        choices.current(0)
        submitted = False

        def cleanup(event):
            if event.widget is dialog and not submitted:
                pending.clear()
        dialog.bind("<Destroy>", cleanup)

        def select():
            nonlocal submitted
            if self.busy or choices.current() < 0:
                return
            profile_id = pending.profiles[choices.current()]["id"]
            submitted = True
            dialog.destroy()
            self.status.set("Conferindo o perfil Crunchyroll e o acesso ao histórico…")
            def job():
                try:
                    record = pending.select(profile_id)
                    value = CrunchyrollSession(record)
                    cr = Crunchyroll(value, cancelled=self.stop.is_set)
                    cr.identify()
                    page = cr.http.request("GET", f"/content/v2/{cr.account_id}/watch-history?page_size=1&locale=en-US")
                    if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                        raise SyncError("O Crunchyroll não confirmou o acesso ao histórico. O login não foi salvo.")
                    if self.stop.is_set():
                        raise Cancelled("Login Crunchyroll cancelado.")
                    self.save_session("cr", value.record)
                    value.on_change = lambda updated: self.save_session("cr", updated)
                    return "cr", value
                finally:
                    pending.clear()
            self.run_worker(job, self.login_ready, kind="login")

        def cancel():
            dialog.destroy()
            self.status.set("Login Crunchyroll cancelado. Nenhum novo acesso foi salvo.")
        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=12, pady=12)
        ttk.Button(actions, text="Usar este perfil", command=select).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=cancel).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", cancel)

    def sign_in(self, service, browser_mode="direct"):
        if self.busy or self.bridge:
            return
        if service == "cr" and browser_mode == "direct":
            self.show_cr_password_login()
            return
        try:
            config = load_anilist_config() if service == "al" else None
        except SyncError as exc:
            messagebox.showerror("Configuração AniList", str(exc))
            return
        client_secret = config.client_secret if config else None
        if service == "al" and not config.auth_service_url:
            client_id = config.client_id
            cached = self.anilist_client_credentials
            if not client_secret and cached and cached[0] == client_id:
                client_secret = cached[1]
            elif not client_secret:
                try:
                    client_secret = self.client_secret_store.get(client_id)
                except (OSError, SyncError):
                    pass
            if not client_secret:
                self.configure_anilist(authorize=True)
                return
        self.persist_review()
        self.invalidate()
        self.clear_identities()
        self.set_logged_in(False)
        self.status.set("Conectando ao seu perfil do Chrome. Permita a conexão se o navegador pedir."
                        if service == "cr" and browser_mode == "current" else
                        "Faça login na janela própria do Crunchyroll e selecione seu perfil; o acesso será conferido automaticamente." if service == "cr" else
                        "Autorize o aplicativo na aba do seu navegador habitual e depois volte ao sincronizador.")
        def job():
            if service == "al":
                if config.auth_service_url:
                    record = login_via_service(config.client_id, config.auth_service_url,
                                              self.stop.is_set, config.redirect_uri)
                else:
                    record = login_anilist(config.client_id, config.redirect_uri, self.stop.is_set,
                                           client_secret=client_secret)
                value = record["access_token"]
                AniList(value, cancelled=self.stop.is_set).identify()
            else:
                record = login_crunchyroll(self.stop.is_set,
                                          on_status=lambda text: self.q.put(("login_status", text)),
                                          use_existing=browser_mode == "current",
                                          preferred_browser="edge" if browser_mode == "edge" else "auto")
                value = CrunchyrollSession(record, lambda updated: self.save_session("cr", updated))
                Crunchyroll(value, cancelled=self.stop.is_set).identify()
            if self.stop.is_set():
                raise Cancelled("Login cancelado.")
            # Só salva depois de conferir o acesso na API do próprio serviço.
            self.save_session(service, record)
            return service, value
        self.run_worker(job, self.login_ready, kind="login")

    def login_ready(self, result):
        service, value = result
        self.auth[service] = value
        self.session_labels[service].configure(text=("Crunchyroll" if service == "cr" else "AniList") + ": conectado")
        self.status.set("Conta conectada. Entre na outra conta para continuar." +
                        (" " + self.storage_warning if self.storage_warning else ""))
        self.maybe_identify_accounts()

    def refresh_login_ui(self):
        self.advanced_window.withdraw()
        if self.logged_in:
            self.login_panel.pack_forget()
            self.accounts_panel.pack(fill="x")
            self.auth_frame.configure(text="CONEXÕES ATIVAS")
        else:
            self.accounts_panel.pack_forget()
            self.login_panel.pack(fill="x")
            self.auth_frame.configure(text="CONECTAR CONTAS")
            if self.token_mode:
                center_dialog(self.advanced_window, self.root)
                self.advanced_window.deiconify()
                self.advanced_window.lift()
        self.token_login_button.configure(text="Ocultar opções avançadas" if self.token_mode else "Opções avançadas")
        self.preview_button.configure(
            state="normal" if self.logged_in and not self.busy and not self.bridge else "disabled")

    def set_logged_in(self, value):
        self.logged_in = value
        if value:
            self.token_mode = False
        self.refresh_login_ui()

    def toggle_token_login(self):
        if self.busy or self.bridge or self.logged_in:
            return
        self.token_mode = not self.token_mode
        self.refresh_login_ui()

    def logout(self):
        if self.busy:
            return
        try:
            self.session_store.clear()
        except OSError:
            messagebox.showerror("Sair", "Não foi possível apagar o login salvo. Confira as permissões da pasta de dados.")
            return
        self.session_records.clear()
        self.storage_warning = ""
        self.persist_review()
        if self.bridge:
            self.end_connection()
        self.folder = None
        self.history_file.set("")
        self.clear_access()
        self.status.set("Contas desconectadas e logins salvos removidos. Entre novamente para continuar.")

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
        self.user.set("Não conectado")
        self.profile.set("Não conectado")

    def show_identity(self, user, cr_profile):
        self.user.set(f"{user['name']} (ID {user['id']})")
        self.profile.set(profile_label(cr_profile))
        self.request_avatar("al", user)
        self.request_avatar("cr", cr_profile)
        self.set_logged_in(True)

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
        if isinstance(self.auth["cr"], CrunchyrollSession):
            self.save_session("cr", self.auth["cr"].record)
        self.show_identity(*accounts)
        self.status.set(f"Conectado: AniList {accounts[0]['name']} · "
                        f"Crunchyroll {profile_label(accounts[1])}. Clique em Gerar prévia." +
                        (" " + self.storage_warning if self.storage_warning else ""))

    def review_changed(self, plan, included):
        self.plan = plan
        self.apply_button.configure(text=f"✓  Aplicar selecionados ({len(included)})",
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
        self.token_mode = False
        self.set_logged_in(False)
        self.clear_identities()
        self.auth = {"cr": "", "al": ""}
        for label in self.auth_labels.values():
            label.configure(text="Não carregado")
        for service, label in self.session_labels.items():
            label.configure(text=("Crunchyroll" if service == "cr" else "AniList") + ": aguardando login")
        self.invalidate()

    def end_connection(self, clear=False):
        bridge, self.bridge = self.bridge, None
        if bridge:
            bridge.close()
        self.connect_button.configure(text=self.chrome_connect_label, state="normal")
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
        saved_al = self.session_records.get("al", {})
        keep_al = self.auth["al"] if (saved_al.get("access_token") == self.auth["al"] and
                                     saved_al.get("expires_at", 0) > time.time() + 60) else ""
        self.clear_access()
        if keep_al:
            self.auth["al"] = keep_al
            self.session_labels["al"].configure(text="AniList: OAuth conectado")
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

    def receive_browser_access(self, service, value):
        # Mantém o OAuth duradouro quando já foi autorizado no navegador habitual.
        saved_al = self.session_records.get("al", {})
        if (service == "al" and self.auth["al"] and
                saved_al.get("access_token") == self.auth["al"] and
                saved_al.get("expires_at", 0) > time.time() + 60):
            return
        record = cr_record_from_fetch(value) if service == "cr" else None
        self.auth[service] = (CrunchyrollSession(record, lambda updated: self.save_session("cr", updated))
                              if record else value)
        self.auth_labels[service].configure(text="Recebido do Chrome — renovável" if record else "Recebido do Chrome — temporário")
        self.session_labels[service].configure(text=("Crunchyroll" if service == "cr" else "AniList") +
                                              (": via extensão, renovável" if record else ": via extensão, temporário"))
        self.invalidate()

    def install_extension(self):
        if self.busy or self.bridge:
            return
        show_extension_setup(parent=self.root)

    def paste(self, service):
        if self.busy or self.logged_in:
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
        self.session_labels[service].configure(text=("Crunchyroll" if service == "cr" else "AniList") + ": acesso manual")
        self.invalidate()
        self.maybe_identify_accounts()

    def token_dialog(self, service):
        if self.busy or self.logged_in:
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
            self.session_labels[service].configure(text=("Crunchyroll" if service == "cr" else "AniList") + ": acesso manual")
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
                self.q.put(("error", str(exc), exc))
        threading.Thread(target=work, daemon=False).start()

    def preview(self):
        if self.busy or self.bridge:
            return
        if not self.auth["al"] or (not self.history_file.get() and not self.auth["cr"]):
            messagebox.showerror("Acessos", "Carregue o acesso do AniList e o do Crunchyroll, ou importe o histórico JSON.")
            return
        auth = dict(self.auth)
        history = self.history_file.get()
        if not self.logged_in:
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
        self.apply_button.configure(text=f"✓  Aplicar selecionados ({len(self.review.included)})",
                                    state="normal" if self.review.included else "disabled")

    def apply(self):
        if self.busy or self.plan is None:
            return
        plan = self.review.subset()
        count = len(plan["changes"])
        if not count:
            return
        comment_count = sum(bool(c.get("activity_comment", "").strip()) for c in plan["changes"])
        if not messagebox.askyesno("Aplicar itens marcados",
                                  f"Aplicar somente os {count} itens marcados em {plan['user']['name']}?\n"
                                  f"Origem Crunchyroll: {profile_label(plan.get('cr_profile'))}\n\n"
                                  + (f"Também serão enviados {comment_count} comentários nas atividades correspondentes.\n\n"
                                     if comment_count else "") +
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
        comments = result.get("comments", [])
        if comments:
            published = sum(c["status"] == "published" for c in comments)
            pending = len(comments) - published
            self.status.set(self.status.get() + f" Comentários: {published} publicados; {pending} pendentes.")
            if pending:
                self.logs.configure(state="normal")
                self.logs.insert("end", "Comentários pendentes: confira comentarios.json na pasta do lote. "
                                 "Se o envio estiver sem confirmação, consulte a atividade antes de publicar novamente.\n")
                self.logs.configure(state="disabled")
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
                elif event[0] == "login_status":
                    if self.busy and self.operation == "login":
                        self.status.set(event[1])
                elif event[0] == "avatar":
                    self.receive_avatar(event)
                elif event[0] == "identity":
                    self.show_identity(event[1], event[2])
                elif event[0] == "browser_access":
                    if self.bridge is not event[1]:
                        continue
                    service, value = event[2], event[3]
                    self.receive_browser_access(service, value)
                    if all(self.auth.values()) and self.bridge.received == {"al", "cr"}:
                        self.end_connection()
                        self.maybe_identify_accounts()
                else:
                    self.busy = False
                    self.review.set_busy(False)
                    self.connect_button.configure(state="normal")
                    for widget in self.option_widgets:
                        widget.configure(state="normal")
                    self.bar.stop()
                    self.preview_button.configure(state="normal" if self.logged_in else "disabled")
                    self.cancel_button.configure(state="disabled")
                    if self.closing:
                        self.destroy_root()
                        return
                    if event[0] == "done":
                        event[1](event[2])
                    else:
                        error = event[2] if len(event) > 2 else None
                        if self.operation == "identity" or getattr(error, "status", None) in (401, 403):
                            self.clear_identities()
                            self.set_logged_in(False)
                        self.invalidate()
                        self.status.set("Login cancelado. Clique em Entrar para tentar novamente."
                                        if self.operation == "login" and isinstance(error, Cancelled) else
                                        "Execução interrompida. Gere outra prévia para continuar."
                                        if self.operation == "apply" else
                                        "Não foi possível concluir o login. Tente novamente."
                                        if self.operation == "login" else "Não foi possível concluir a consulta.")
                        if isinstance(error, ChromeSetupRequired) and not self.closing:
                            self.show_chrome_setup()
                        elif not self.closing and not isinstance(error, Cancelled):
                            messagebox.showerror("Não foi possível concluir", event[1])
        except queue.Empty:
            pass
        if self.bridge and self.bridge.expired:
            self.end_connection(clear=True)
            self.status.set("A conexão expirou. Confira a extensão e os logins e clique em Conectar pela extensão novamente.")
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
        folder = self.folder if self.folder and self.folder.exists() else DATA_ROOT
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            import webbrowser
            webbrowser.open(Path(folder).as_uri())

    def destroy_root(self):
        if self.restore_timer:
            self.root.after_cancel(self.restore_timer)
        if self.save_timer:
            self.root.after_cancel(self.save_timer)
        try:
            self.root.after_cancel(self.drain_timer)
        except tk.TclError:
            pass
        self.identity_generation += 1
        self.auth.clear()
        self.anilist_client_credentials = None
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
