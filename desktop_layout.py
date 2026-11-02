"""Composição visual: menus, navegação, contas e área de trabalho."""
import os
import tkinter as tk
from tkinter import ttk

from desktop_theme import SIDEBAR, BLUE, install_dark_theme, dark_titlebar
from review_pane import ReviewPane
from desktop_menu import MenuButton
from desktop_window import IntegratedTitlebar


def build_workspace(app):
    root = app.root
    app.style = install_dark_theme(root)
    app.option_widgets = []
    top = ttk.Frame(root, style="Rail.TFrame", padding=(14, 0, 0, 0))
    top.pack(fill="x")
    menu_specs = (
        ("Arquivo", [("Importar histórico JSON…", app.choose_file), ("Pasta da execução", app.open_folder),
                     None, ("Sair do aplicativo", app.close)]),
        ("Contas", [("Entrar no Crunchyroll…", lambda: app.sign_in("cr")),
                    ("Autorizar AniList…", lambda: app.sign_in("al")),
                    ("Configurar AniList…", app.configure_anilist), None, ("Desconectar contas", app.logout)]),
        ("Sincronizar", [("Gerar prévia", lambda: app.preview_button.invoke()),
                         ("Aplicar selecionados", lambda: app.apply_button.invoke()),
                         ("Interromper", lambda: app.cancel_button.invoke())]),
        ("Ajuda", [("Abrir guia de uso", app.help)]))
    for label, entries in menu_specs:
        button = MenuButton(top, text=label, style="Top.TButton", entries=entries)
        button.pack(side="left", padx=2)
    title = ttk.Label(top, text="Crunchyroll → AniList", style="RailMuted.TLabel", anchor="center")
    app.titlebar = IntegratedTitlebar(root, top, title, app.close)

    footer = ttk.Frame(root, style="Rail.TFrame", padding=(16, 9))
    footer.pack(side="bottom", fill="x")
    ttk.Label(footer, text="●", foreground=BLUE, style="Rail.TLabel").pack(side="left", padx=(0, 10))
    app.status_label = ttk.Label(footer, textvariable=app.status, style="RailMuted.TLabel", wraplength=1100)
    app.status_label.pack(side="left", fill="x", expand=True)
    footer.bind("<Configure>", lambda event: app.status_label.configure(wraplength=max(300, event.width - 60)))

    body = ttk.Frame(root)
    body.pack(fill="both", expand=True)
    sidebar = ttk.Frame(body, style="Rail.TFrame", width=224, padding=(12, 14))
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)
    app.sidebar = sidebar
    accounts = ttk.Frame(sidebar, style="Rail.TFrame")
    accounts.pack(side="bottom", fill="x")
    ttk.Label(sidebar, text="SYNC", style="Rail.TLabel", font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=12)
    ttk.Label(sidebar, text="Seu histórico, em dia.", style="RailMuted.TLabel").pack(anchor="w", padx=12, pady=(0, 18))
    ttk.Label(sidebar, text="ÁREA DE TRABALHO", style="RailMuted.TLabel").pack(anchor="w", padx=12, pady=(0, 8))
    app.nav_buttons = []
    for index, label in enumerate(("▤   Revisão", "!    Pendências", "≡   Progresso")):
        button = ttk.Button(sidebar, text=label, style="Nav.TButton",
                            command=lambda i=index: app.notebook.select(i))
        button.pack(fill="x", pady=2)
        app.nav_buttons.append(button)
    ttk.Label(accounts, text="CONTAS CONECTADAS", style="RailMuted.TLabel").pack(anchor="w", padx=12, pady=(20, 14))
    app.avatar_canvases = {}
    app.session_labels = {}
    for service, title, role, variable in (
            ("cr", "Crunchyroll", "ORIGEM", app.profile), ("al", "AniList", "DESTINO", app.user)):
        card = ttk.Frame(accounts, style="Rail.TFrame", padding=(10, 6))
        card.pack(fill="x", pady=(0, 8))
        head = ttk.Frame(card, style="Rail.TFrame")
        head.pack(fill="x")
        canvas = tk.Canvas(head, width=56, height=56, highlightthickness=0, background=SIDEBAR,
                           cursor="hand2", takefocus=True)
        def open_account(_event=None, s=service):
            app.sign_in(s)
            return "break"
        canvas.bind("<Button-1>", open_account)
        canvas.bind("<Return>", open_account)
        canvas.bind("<space>", open_account)
        canvas.bind("<FocusIn>", lambda event: event.widget.configure(background="#203448"))
        canvas.bind("<FocusOut>", lambda event: event.widget.configure(background=SIDEBAR))
        canvas.pack(side="left", padx=(0, 10))
        app.avatar_canvases[service] = canvas
        names = ttk.Frame(head, style="Rail.TFrame")
        names.pack(side="left", fill="x", expand=True)
        ttk.Label(names, text=role, style="RailMuted.TLabel", font=("Segoe UI", 8)).pack(anchor="w")
        ttk.Label(names, text=title, style="Rail.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=3)
        ttk.Label(card, textvariable=variable, style="Rail.TLabel", wraplength=178).pack(anchor="w", pady=(6, 3))
        label = ttk.Label(card, text=title + ": aguardando login", style="RailMuted.TLabel", wraplength=178)
        label.pack(anchor="w")
        app.session_labels[service] = label
        app.reset_avatar(service)

    main = ttk.Frame(body, padding=(24, 20, 24, 16))
    main.pack(side="left", fill="both", expand=True)
    ttk.Label(main, text="BIBLIOTECA  /  SINCRONIZAÇÃO", style="Eyebrow.TLabel").pack(anchor="w")
    ttk.Label(main, text="Sua biblioteca, sincronizada.", style="Title.TLabel").pack(anchor="w", pady=(8, 4))
    ttk.Label(main, text="Traga seu histórico do Crunchyroll. Revise cada mudança antes de atualizar o AniList.",
              style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(0, 20))
    app.auth_frame = ttk.LabelFrame(main, text="CONECTAR CONTAS", padding=(14, 10))
    app.auth_frame.pack(fill="x")
    app.login_panel = ttk.Frame(app.auth_frame)
    app.login_panel.pack(fill="x")
    login_row = ttk.Frame(app.login_panel)
    login_row.pack(fill="x")
    for service, title in (("cr", "Entrar no Crunchyroll"), ("al", "Autorizar AniList")):
        button = ttk.Button(login_row, text=title, command=lambda s=service: app.sign_in(s))
        button.pack(side="left", padx=(0, 8))
        app.option_widgets.append(button)
    app.token_login_button = ttk.Button(login_row, text="Opções avançadas", style="Small.TButton", command=app.toggle_token_login)
    app.token_login_button.pack(side="right")
    app.option_widgets.append(app.token_login_button)
    app.remember = tk.BooleanVar(value=app.keep_sessions)

    def remember_check(parent):
        check = ttk.Checkbutton(parent, text="Manter contas conectadas neste Windows",
                                variable=app.remember, command=app.change_remember)
        check.pack(anchor="w", pady=(4, 0))
        if os.name == "nt":
            app.option_widgets.append(check)
        else:
            check.configure(state="disabled")
    remember_check(app.login_panel)
    app.advanced_window = tk.Toplevel(app.login_panel)
    app.advanced_window.withdraw()
    app.advanced_window.title("Opções avançadas de conexão")
    app.advanced_window.transient(root)
    app.advanced_window.resizable(False, False)
    def close_advanced():
        app.token_mode = False
        app.refresh_login_ui()
    app.advanced_window.protocol("WM_DELETE_WINDOW", close_advanced)
    app.token_panel = ttk.LabelFrame(app.advanced_window, text="MÉTODOS ALTERNATIVOS", padding=16)
    app.token_panel.pack(fill="both", expand=True, padx=16, pady=16)
    alternatives = ttk.Frame(app.token_panel)
    alternatives.pack(fill="x")
    app.chrome_connect_label = "Conectar pela extensão"
    app.connect_button = ttk.Button(alternatives, text=app.chrome_connect_label, style="Small.TButton", command=app.connect_chrome)
    app.connect_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
    specs = [("Instalar extensão", app.install_extension), ("Configurar AniList", app.configure_anilist),
             ("Chrome: perfil habitual", lambda: app.sign_in("cr", browser_mode="current")),
             ("Chrome: janela própria", lambda: app.sign_in("cr", browser_mode="isolated")),
             ("Edge: janela própria", lambda: app.sign_in("cr", browser_mode="edge"))]
    for index, (label, command) in enumerate(specs, 1):
        button = ttk.Button(alternatives, text=label, style="Small.TButton", command=command)
        button.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0, 6), pady=4)
        app.option_widgets.append(button)
        if index == 5:
            app.edge_login_button = button
    for column in range(3):
        alternatives.columnconfigure(column, weight=1)
    app.auth_labels = {}
    for service, name in (("cr", "Crunchyroll"), ("al", "AniList")):
        row = ttk.Frame(app.token_panel)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=name, width=12).pack(side="left")
        ttk.Button(row, text="Colar acesso", style="Small.TButton", command=lambda s=service: app.paste(s)).pack(side="left", padx=4)
        ttk.Button(row, text="Digitar token", style="Small.TButton", command=lambda s=service: app.token_dialog(s)).pack(side="left", padx=4)
        app.auth_labels[service] = ttk.Label(row, text="Não carregado", style="Muted.TLabel")
        app.auth_labels[service].pack(side="left", padx=8)
    ttk.Button(app.advanced_window, text="Fechar opções", command=close_advanced,
               style="Small.TButton").pack(anchor="e", padx=16, pady=(0, 16))
    app.source_panel = ttk.Frame(app.login_panel)
    app.source_panel.pack(fill="x", pady=(6, 0))
    ttk.Button(app.source_panel, text="Importar histórico JSON", style="Small.TButton", command=app.choose_file).pack(side="left")
    ttk.Label(app.source_panel, textvariable=app.history_file, style="Muted.TLabel", width=22).pack(side="left", padx=10, fill="x", expand=True)
    api_button = ttk.Button(app.source_panel, text="Usar API", style="Small.TButton", command=lambda: app.history_file.set(""))
    api_button.pack(side="right")
    app.option_widgets.append(api_button)
    app.accounts_panel = ttk.Frame(app.auth_frame)
    connected_row = ttk.Frame(app.accounts_panel)
    connected_row.pack(fill="x")
    ttk.Label(connected_row, text="●  Contas prontas para sincronizar", foreground="#89d185").pack(side="left", padx=(0, 16))
    app.logout_button = ttk.Button(connected_row, text="Sair / trocar contas", style="Small.TButton", command=app.logout)
    app.logout_button.pack(side="right")
    app.option_widgets.append(app.logout_button)
    remember_check(app.accounts_panel)

    controls = ttk.Frame(main)
    controls.pack(fill="x", pady=(18, 12))
    app.preview_button = ttk.Button(controls, text="↻  Gerar prévia", command=app.preview, style="Primary.TButton")
    app.preview_button.pack(side="left")
    app.apply_button = ttk.Button(controls, text="✓  Aplicar selecionados", state="disabled", command=app.apply, style="Primary.TButton")
    app.apply_button.pack(side="left", padx=10)
    app.cancel_button = ttk.Button(controls, text="■  Interromper", state="disabled", command=app.stop.set)
    app.cancel_button.pack(side="right")
    progress_track = ttk.Frame(main, height=3)
    progress_track.pack(fill="x", pady=(0, 12))
    progress_track.pack_propagate(False)
    app.bar = ttk.Progressbar(progress_track, mode="indeterminate", style="Horizontal.TProgressbar")
    app.bar.pack(fill="both", expand=True)
    app.notebook = ttk.Notebook(main)
    app.notebook.pack(fill="both", expand=True)
    app.review = ReviewPane(app.notebook, app.review_changed)
    app.notebook.add(app.review, text="Revisão do plano")
    app.table = app.review.table
    app.pending = tk.Text(app.notebook, wrap="word", state="disabled", font=("Segoe UI", 10))
    app.notebook.add(app.pending, text="Pendências")
    app.logs = tk.Text(app.notebook, wrap="word", state="disabled", font=("Cascadia Code", 10))
    app.notebook.add(app.logs, text="Progresso")
    def tab_changed(_event=None):
        selected = app.notebook.index("current")
        for index, button in enumerate(app.nav_buttons):
            button.configure(style="Active.Nav.TButton" if index == selected else "Nav.TButton")
    app.notebook.bind("<<NotebookTabChanged>>", tab_changed)
    tab_changed()
    root.bind_all("<Map>", lambda event: dark_titlebar(event.widget) if isinstance(event.widget, (tk.Tk, tk.Toplevel)) else None, add="+")
