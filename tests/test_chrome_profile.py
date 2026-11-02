"""Chrome normal: metadados fictícios e conexão simulada, sem ler perfis pessoais."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chrome_profile as c
import browser_bridge as bridge
from sync_anilist import Cancelled, SyncError


class CurrentProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cral-profile-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / "Local State").write_text(json.dumps({"profile": {"last_used": "Profile 3"}}))
        (self.folder / "DevToolsActivePort").write_text("12345\n/devtools/browser/test-only\n")
        self.browser = c.CurrentChrome(folder=self.folder)
        self.connection = Mock()
        self.own_url = self.browser.marker

        def command(method, params=None, **kwargs):
            if method == "Target.getTargets":
                return {"targetInfos": [
                    {"targetId": "personal-tab", "type": "page", "url": "https://example.com/"},
                    {"targetId": "own-tab", "type": "page", "url": self.browser.marker}]}
            if method == "Target.attachToTarget":
                self.assertEqual(params["targetId"], "own-tab")
                return {"sessionId": "own-session"}
            if method == "Target.getTargetInfo":
                self.assertEqual(params["targetId"], "own-tab")
                return {"targetInfo": {"url": self.own_url}}
            return {}
        self.connection.command.side_effect = command

    def test_selects_last_used_profile_without_new_user_data_directory(self):
        before = (self.folder / "Local State").read_bytes()
        with patch.object(c, "DevTools", return_value=self.connection), patch.object(c, "open_chrome") as launch:
            with self.browser:
                launch.assert_called_once_with(self.browser.marker, profile_directory="Profile 3")
                self.assertEqual(self.browser.target_id, "own-tab")
                self.assertIsNone(self.browser.temp)
                self.assertIsNone(self.browser.process)
        self.assertEqual((self.folder / "Local State").read_bytes(), before)
        self.assertTrue((self.folder / "DevToolsActivePort").exists())

    def test_cleanup_closes_only_created_login_tab_and_never_browser(self):
        with patch.object(c, "DevTools", return_value=self.connection), patch.object(c, "open_chrome"):
            with self.browser:
                self.own_url = "https://www.crunchyroll.com/history"
        closed = [call.args[1]["targetId"] for call in self.connection.command.call_args_list
                  if call.args[0] == "Target.closeTarget"]
        self.assertEqual(closed, ["own-tab"])
        self.assertNotIn("Browser.close", [call.args[0] for call in self.connection.command.call_args_list])
        self.connection.socket.close.assert_called_once()
        self.browser.close()  # Idempotente; não usa um alvo antigo.
        self.connection.socket.close.assert_called_once()

    def test_tab_navigated_elsewhere_is_detached_and_left_open(self):
        with patch.object(c, "DevTools", return_value=self.connection), patch.object(c, "open_chrome"):
            with self.browser:
                self.own_url = "https://example.com/user-moved-tab"
        methods = [call.args[0] for call in self.connection.command.call_args_list]
        self.assertIn("Target.detachFromTarget", methods)
        self.assertNotIn("Target.closeTarget", methods)
        self.assertNotIn("Browser.close", methods)

    def test_missing_setting_requests_setup_without_opening_guest_window(self):
        (self.folder / "DevToolsActivePort").unlink()
        with patch.object(c, "DevTools") as connect, patch.object(c, "open_chrome") as launch:
            with self.assertRaisesRegex(c.ChromeSetupRequired, "chrome://inspect/#remote-debugging"):
                self.browser.__enter__()
        connect.assert_not_called()
        launch.assert_not_called()

    def test_invalid_descriptor_never_connects_to_foreign_endpoint(self):
        for descriptor in ("99999\n/devtools/browser/fake", "12345\nhttps://evil.example/path", "invalid"):
            (self.folder / "DevToolsActivePort").write_text(descriptor)
            with self.subTest(descriptor=descriptor), patch.object(c, "DevTools") as connect:
                with self.assertRaises(c.ChromeSetupRequired):
                    self.browser.__enter__()
                connect.assert_not_called()

    def test_cancel_is_preserved_instead_of_becoming_setup_error(self):
        with patch.object(c, "DevTools", side_effect=Cancelled("cancelled")), patch.object(c, "open_chrome") as launch:
            with self.assertRaises(Cancelled):
                self.browser.__enter__()
        launch.assert_not_called()

    def test_connection_failure_does_not_echo_descriptor_or_credentials(self):
        with patch.object(c, "DevTools", side_effect=SyncError("private-descriptor")):
            with self.assertRaises(c.ChromeSetupRequired) as caught:
                self.browser.__enter__()
        self.assertNotIn("private-descriptor", str(caught.exception))

    def test_last_profile_rejects_guest_and_path_traversal(self):
        for profile in ("Guest Profile", "../outside", "C:/somewhere", "--user-data-dir=other"):
            (self.folder / "Local State").write_text(json.dumps({"profile": {"last_used": profile}}))
            with self.subTest(profile=profile), self.assertRaises(c.ChromeSetupRequired):
                c.last_profile(self.folder)

    def test_launcher_passes_profile_but_no_isolated_or_debugging_flags(self):
        with patch.object(bridge, "chrome_path", return_value="chrome.exe"), patch.object(bridge.subprocess, "Popen") as launch:
            bridge.open_chrome("https://www.crunchyroll.com/login", profile_directory="Profile 3")
        args = launch.call_args.args[0]
        self.assertEqual(args, ["chrome.exe", "--profile-directory=Profile 3", "--new-tab", "https://www.crunchyroll.com/login"])
        self.assertFalse(any(arg.startswith("--user-data-dir") or arg.startswith("--remote-debugging") for arg in args))


if __name__ == "__main__":
    unittest.main()
