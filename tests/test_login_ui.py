"""Estados da interface com Tk oculto e contas fictícias; não abre sites."""
from pathlib import Path
import json
import gc
import os
import sys
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import interface as ui
from browser_login import PUBLIC_CR_CLIENT
from session_store import cr_record, CrunchyrollSession
import session_store
from test_sync import jwt
from app_config import AniListConfig
from oauth_login import REDIRECT_URI
from test_cr_direct_login import record as direct_record


class LoginUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.store = Mock()
        self.store.load.return_value = {}
        self.client_store = Mock()
        self.client_store.get.return_value = "secret-ficticio"
        self.config_patch = patch.object(ui, "load_anilist_config", return_value=AniListConfig("55193", REDIRECT_URI))
        self.config_mock = self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        with patch.object(ui, "SessionStore", return_value=self.store), \
                patch.object(ui, "ClientSecretStore", return_value=self.client_store):
            self.window = ui.Window(self.root)
        # Testes de restauração chamam o método explicitamente.
        self.root.after_cancel(self.window.restore_timer)
        self.window.restore_timer = None
        self.window.keep_sessions = True
        self.window.remember.set(True)

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.destroy_root()
            self.window = self.root = None
            # Avoid collecting old Tcl interpreters on a later server thread.
            gc.collect()

    def test_restore_keeps_saved_sessions_and_verifies_accounts(self):
        self.store.load.return_value = {
            "al": {"access_token": "fake-al", "expires_at": time.time() + 1000},
            "cr": cr_record(jwt(), "fake-cookie", PUBLIC_CR_CLIENT)}
        with patch.object(self.window, "maybe_identify_accounts") as identify:
            self.window.restore_sessions()
        self.assertEqual(self.window.auth["al"], "fake-al")
        self.assertIsInstance(self.window.auth["cr"], CrunchyrollSession)
        identify.assert_called_once()
        self.assertFalse(self.window.logged_in)  # Ainda depende de conferir as APIs.

    def test_avatar_clicks_open_corresponding_login_even_when_connected(self):
        self.window.set_logged_in(True)
        self.root.deiconify()
        self.root.update()
        with patch.object(self.window, "show_cr_password_login") as cr_login, \
                patch.object(self.window, "run_worker") as worker:
            self.window.avatar_canvases["cr"].event_generate("<Button-1>")
            cr_login.assert_called_once()
            worker.assert_not_called()
            self.window.avatar_canvases["al"].event_generate("<Button-1>")
            worker.assert_called_once()
            self.assertEqual(worker.call_args.kwargs["kind"], "login")

    def test_flat_menu_invokes_once_and_closes_with_escape(self):
        from desktop_menu import MenuButton
        action = Mock()
        button = MenuButton(self.root, text="Menu de teste", entries=[("Ação", action)])
        button.pack()
        self.root.deiconify()
        self.root.update()
        button.invoke()
        self.root.update()
        button.popup.winfo_children()[0].invoke()
        action.assert_called_once()
        self.assertIsNone(button.popup)
        button.invoke()
        self.root.update()
        button.popup.event_generate("<Escape>")
        self.assertIsNone(button.popup)
        button.configure(state="disabled")
        button.invoke()
        self.assertIsNone(button.popup)
        action.assert_called_once()

    def test_expired_anilist_is_not_restored_as_logged_in(self):
        self.store.load.return_value = {"al": {"access_token": "expired", "expires_at": time.time() - 1}}
        self.window.restore_sessions()
        self.assertEqual(self.window.auth["al"], "")
        self.assertFalse(self.window.logged_in)

    def test_restored_cr_session_renews_without_opening_login(self):
        self.store.load.return_value = {
            "cr": cr_record(jwt(expiry=time.time() - 10), "old-cookie", PUBLIC_CR_CLIENT)}
        fresh = jwt(expiry=time.time() + 3600)
        with patch.object(self.window, "maybe_identify_accounts"), \
                patch.object(ui, "login_crunchyroll") as login, \
                patch.object(session_store, "exchange_cr", return_value=(fresh, "rotated-cookie")) as exchange:
            self.window.restore_sessions()
            client = ui.Crunchyroll(self.window.auth["cr"])
        login.assert_not_called()
        exchange.assert_called_once()
        self.assertEqual(client.account_id, "account")
        self.assertEqual(client.claims["profile_id"], "active")
        self.assertEqual(self.store.put.call_args.args[0], "cr")
        self.assertEqual(self.store.put.call_args.args[1]["refresh_cookie"], "rotated-cookie")
        self.assertEqual(self.window.session_records["cr"]["access_token"], fresh)

    def test_disabling_remember_deletes_saved_file_but_retains_current_access(self):
        self.window.auth["al"] = "fake-al"
        self.window.remember.set(False)
        self.window.change_remember()
        self.store.clear.assert_called_once()
        self.assertFalse(self.window.keep_sessions)
        self.assertEqual(self.window.auth["al"], "fake-al")

    def test_logout_removes_saved_accounts_and_current_access(self):
        self.window.auth["al"] = "fake-al"
        self.window.session_records["al"] = {"access_token": "fake-al"}
        self.window.logout()
        self.store.clear.assert_called_once()
        self.assertEqual(self.window.auth, {"cr": "", "al": ""})
        self.assertEqual(self.window.session_records, {})
        self.assertFalse(self.window.logged_in)

    def test_anilist_login_uses_configured_client_and_verifies_before_saving(self):
        record = {"access_token": "fake-al", "expires_at": time.time() + 1000}
        with patch.object(ui, "login_anilist", return_value=record) as login, \
                patch.object(ui, "AniList") as api, \
                patch.object(self.window, "run_worker") as worker, \
                patch.object(self.window, "maybe_identify_accounts"):
            self.window.sign_in("al")
            job, callback = worker.call_args.args
            self.store.put.assert_not_called()
            callback(job())
        self.assertEqual(login.call_args.args[0], "55193")
        self.assertEqual(login.call_args.kwargs["client_secret"], "secret-ficticio")
        api.return_value.identify.assert_called_once()
        self.store.put.assert_called_once_with("al", record)
        self.assertEqual(self.window.auth["al"], "fake-al")

    def test_unverified_login_is_not_persisted(self):
        record = {"access_token": "fake-al", "expires_at": time.time() + 1000}
        with patch.object(ui, "login_anilist", return_value=record), \
                patch.object(ui, "AniList") as api, patch.object(self.window, "run_worker") as worker:
            api.return_value.identify.side_effect = ui.SyncError("invalid")
            self.window.sign_in("al")
            job = worker.call_args.args[0]
            with self.assertRaises(ui.SyncError):
                job()
        self.store.put.assert_not_called()

    def test_missing_client_secret_opens_local_setup_before_login(self):
        self.client_store.get.return_value = None
        with patch.object(self.window, "configure_anilist") as configure, \
                patch.object(self.window, "run_worker") as worker:
            self.window.sign_in("al")
        configure.assert_called_once_with(authorize=True)
        worker.assert_not_called()

    def test_env_secret_takes_precedence_without_prompt_or_protected_copy(self):
        self.config_mock.return_value = AniListConfig("55193", REDIRECT_URI, "env-secret-ficticio")
        self.window.anilist_client_credentials = ("55193", "old-secret-ficticio")
        record = {"access_token": "fake-al", "expires_at": time.time() + 1000}
        with patch.object(ui, "login_anilist", return_value=record) as login, \
                patch.object(ui, "AniList"), patch.object(self.window, "run_worker") as worker, \
                patch.object(self.window, "configure_anilist") as setup:
            self.window.sign_in("al")
            worker.call_args.args[0]()
        self.assertEqual(login.call_args.kwargs["client_secret"], "env-secret-ficticio")
        setup.assert_not_called()
        self.client_store.get.assert_not_called()
        self.client_store.save.assert_not_called()

    def test_connecting_cr_keeps_anilist_access_already_authorized(self):
        self.window.auth["al"] = "fake-al-already-connected"
        record = cr_record(jwt(), "fake-cookie", PUBLIC_CR_CLIENT)
        with patch.object(ui, "login_crunchyroll", return_value=record) as login, \
                patch.object(ui, "Crunchyroll"), patch.object(self.window, "run_worker") as worker, \
                patch.object(self.window, "maybe_identify_accounts"):
            self.window.sign_in("cr", browser_mode="isolated")
            job, callback = worker.call_args.args
            callback(job())
        self.assertEqual(self.window.auth["al"], "fake-al-already-connected")
        self.assertIsInstance(self.window.auth["cr"], CrunchyrollSession)
        self.assertFalse(login.call_args.kwargs["use_existing"])
        self.store.put.assert_called_once_with("cr", record)

    def test_normal_chrome_profile_requires_explicit_choice(self):
        record = cr_record(jwt(), "fake-cookie", PUBLIC_CR_CLIENT)
        with patch.object(ui, "login_crunchyroll", return_value=record) as login, \
                patch.object(ui, "Crunchyroll"), patch.object(self.window, "run_worker") as worker:
            self.window.sign_in("cr", browser_mode="current")
            worker.call_args.args[0]()
        self.assertTrue(login.call_args.kwargs["use_existing"])

    def dialog_button(self, dialog, text):
        return next(child for frame in dialog.winfo_children() for child in frame.winfo_children()
                    if child.winfo_class() == "TButton" and child.cget("text") == text)

    def test_default_cr_login_asks_for_masked_password_without_browser(self):
        with patch.object(ui, "login_crunchyroll") as browser, patch.object(self.window, "run_worker") as worker:
            self.window.sign_in("cr")
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        entries = [w for w in dialog.winfo_children() if w.winfo_class() == "TEntry"]
        self.assertEqual(str(entries[1].cget("show")), "*")
        browser.assert_not_called()
        worker.assert_not_called()
        self.dialog_button(dialog, "Cancelar").invoke()
        self.store.put.assert_not_called()

    def test_password_is_submitted_once_and_not_saved_before_profile_choice(self):
        self.window.auth["al"] = "fake-al"
        self.window.sign_in("cr")
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        entries = [w for w in dialog.winfo_children() if w.winfo_class() == "TEntry"]
        entries[0].insert(0, "test@example.invalid")
        entries[1].insert(0, " password with spaces ")
        with patch.object(ui, "login_with_password", return_value="pending") as login, \
                patch.object(self.window, "run_worker") as worker:
            self.dialog_button(dialog, "Entrar").invoke()
            job, callback = worker.call_args.args
            self.assertEqual(job(), "pending")
        self.assertEqual(login.call_args.args[:2], ("test@example.invalid", " password with spaces "))
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(callback, self.window.show_cr_profiles)
        self.assertEqual(self.window.auth["al"], "fake-al")
        self.store.put.assert_not_called()

    def test_direct_profile_is_verified_with_history_before_saving(self):
        self.window.auth["al"] = "fake-al"
        pending = Mock()
        pending.profiles = [{"id": "active", "name": "Meu perfil"}]
        pending.select.return_value = direct_record()
        self.window.show_cr_profiles(pending)
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        with patch.object(ui, "Crunchyroll") as api, patch.object(self.window, "run_worker") as worker, \
                patch.object(self.window, "maybe_identify_accounts"):
            api.return_value.account_id = "account"
            api.return_value.http.request.return_value = {"data": []}
            self.dialog_button(dialog, "Usar este perfil").invoke()
            job, callback = worker.call_args.args
            self.store.put.assert_not_called()
            callback(job())
        api.return_value.identify.assert_called_once()
        api.return_value.http.request.assert_called_once_with("GET", "/content/v2/account/watch-history?page_size=1&locale=en-US")
        pending.select.assert_called_once_with("active")
        pending.clear.assert_called_once()
        self.store.put.assert_called_once()
        self.assertEqual(self.window.auth["al"], "fake-al")
        self.assertTrue(self.window.auth["cr"].direct)

    def test_direct_profile_failure_is_not_saved_and_discards_pending_tokens(self):
        pending = Mock()
        pending.profiles = [{"id": "active", "name": "Meu perfil"}]
        pending.select.return_value = direct_record()
        self.window.show_cr_profiles(pending)
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        with patch.object(ui, "Crunchyroll") as api, patch.object(self.window, "run_worker") as worker:
            api.return_value.http.request.side_effect = ui.SyncError("blocked")
            self.dialog_button(dialog, "Usar este perfil").invoke()
            with self.assertRaises(ui.SyncError):
                worker.call_args.args[0]()
        self.store.put.assert_not_called()
        pending.clear.assert_called_once()

    def test_cancel_profile_discards_tokens_without_saving(self):
        pending = Mock()
        pending.profiles = [{"id": "active", "name": "Meu perfil"}]
        self.window.show_cr_profiles(pending)
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        self.dialog_button(dialog, "Cancelar").invoke()
        pending.clear.assert_called_once()
        self.store.put.assert_not_called()

    def test_edge_button_uses_own_window_and_keeps_anilist(self):
        self.window.auth["al"] = "fake-al"
        record = cr_record(jwt(), "fake-cookie", PUBLIC_CR_CLIENT)
        with patch.object(ui, "login_crunchyroll", return_value=record) as login, \
                patch.object(ui, "Crunchyroll"), patch.object(self.window, "run_worker") as worker:
            self.window.edge_login_button.invoke()
            worker.call_args.args[0]()
        self.assertFalse(login.call_args.kwargs["use_existing"])
        self.assertEqual(login.call_args.kwargs["preferred_browser"], "edge")
        self.assertEqual(self.window.auth["al"], "fake-al")
        self.store.put.assert_called_once_with("cr", record)

    def test_login_progress_event_does_not_mark_worker_as_finished(self):
        self.root.after_cancel(self.window.drain_timer)
        self.window.busy = True
        self.window.operation = "login"
        self.window.q.put(("login_status", "Aguardando entrada no Crunchyroll"))
        self.window.drain()
        self.assertTrue(self.window.busy)
        self.assertEqual(self.window.status.get(), "Aguardando entrada no Crunchyroll")

    def test_in_memory_client_secret_does_not_require_saved_credentials(self):
        self.window.anilist_client_credentials = ("55193", "memory-secret-ficticio")
        with patch.object(self.window, "run_worker") as worker:
            self.window.sign_in("al")
        self.client_store.get.assert_not_called()
        worker.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "Persistência protegida requer Windows")
    def test_client_setup_masks_secret_and_saves_before_authorizing(self):
        self.client_store.get.return_value = None
        with patch.object(self.window, "sign_in") as login:
            self.window.configure_anilist(authorize=True)
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            entry = next(w for w in dialog.winfo_children() if w.winfo_class() == "TEntry")
            self.assertEqual(str(entry.cget("show")), "*")
            entry.insert(0, "setup-secret-ficticio")
            buttons = [child for frame in dialog.winfo_children() for child in frame.winfo_children()
                       if child.winfo_class() == "TButton"]
            save = next(button for button in buttons if button.cget("text") == "Salvar e autorizar")
            save.invoke()
        self.client_store.save.assert_called_once_with("55193", "setup-secret-ficticio")
        self.assertEqual(self.window.anilist_client_credentials, ("55193", "setup-secret-ficticio"))
        login.assert_called_once_with("al")

    def test_cancelling_client_setup_does_not_save_or_start_login(self):
        self.client_store.get.return_value = None
        with patch.object(self.window, "sign_in") as login:
            self.window.configure_anilist(authorize=True)
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
            buttons = [child for frame in dialog.winfo_children() for child in frame.winfo_children()
                       if child.winfo_class() == "TButton"]
            next(button for button in buttons if button.cget("text") == "Cancelar").invoke()
        self.client_store.save.assert_not_called()
        self.assertIsNone(self.window.anilist_client_credentials)
        login.assert_not_called()

    def test_closing_window_preserves_saved_login(self):
        self.window.auth["al"] = "fake-al"
        self.window.close()
        self.store.clear.assert_not_called()
        # A janela já foi destruída.
        del self.window

    def test_extension_does_not_replace_existing_anilist_oauth(self):
        self.window.auth["al"] = "fake-oauth"
        self.window.session_records["al"] = {"access_token": "fake-oauth", "expires_at": time.time() + 1000}
        self.window.receive_browser_access("al", "fake-web-cookie")
        self.assertEqual(self.window.auth["al"], "fake-oauth")

    def test_extension_cr_session_is_only_saved_after_identity_is_verified(self):
        credential = 'fetch("https://www.crunchyroll.com/content/v2/account/watch-history",' + json.dumps({
            "headers": {"authorization": "Bearer " + jwt(), "cookie": "etp_rt=fake-cookie"}}) + ")"
        self.window.receive_browser_access("cr", credential)
        self.assertIsInstance(self.window.auth["cr"], CrunchyrollSession)
        self.store.put.assert_not_called()
        self.window.accounts_ready(({"id": 42, "name": "Fake"},
                                    {"profile_id": "active", "verified_name": "Fake profile"}))
        self.store.put.assert_called_once()
        self.assertEqual(self.store.put.call_args.args[0], "cr")
        self.assertEqual(self.store.put.call_args.args[1]["refresh_cookie"], "fake-cookie")


if __name__ == "__main__":
    unittest.main()
