"""Configuração .env com dados fictícios; não lê credenciais do usuário."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_config import load_anilist_config
from oauth_login import REDIRECT_URI
from sync_anilist import SyncError


class EnvConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cral-config-test-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def env(self, content):
        (self.root / ".env").write_text(content, encoding="utf-8")

    def load(self, environ=None):
        return load_anilist_config(self.root, {} if environ is None else environ)

    def test_reads_client_configuration_without_json_or_extra_dependencies(self):
        self.env(f"ANILIST_CLIENT_ID=123\nANILIST_CLIENT_SECRET=fake-secret\nANILIST_REDIRECT_URI={REDIRECT_URI}\n")
        config = self.load()
        self.assertEqual(config.client_id, "123")
        self.assertEqual(config.client_secret, "fake-secret")
        self.assertEqual(config.redirect_uri, REDIRECT_URI)
        self.assertNotIn("fake-secret", repr(config))

    def test_environment_overrides_dotenv_and_public_json(self):
        (self.root / "auth_config.json").write_text(json.dumps({"anilist_client_id": "111"}))
        self.env("ANILIST_CLIENT_ID=222\nANILIST_CLIENT_SECRET=file-secret\n")
        config = self.load({"ANILIST_CLIENT_ID": "333", "ANILIST_CLIENT_SECRET": "env-secret"})
        self.assertEqual(config.client_id, "333")
        self.assertEqual(config.client_secret, "env-secret")

    def test_dotenv_overrides_public_json_and_supports_bom_comments_quotes(self):
        (self.root / "auth_config.json").write_text(json.dumps({"anilist_client_id": "111"}))
        self.env('\ufeff# configuração\nexport ANILIST_CLIENT_ID="222" # ID\nANILIST_CLIENT_SECRET=\'a#b=c$literal\\path\'\n')
        config = self.load()
        self.assertEqual(config.client_id, "222")
        self.assertEqual(config.client_secret, "a#b=c$literal\\path")

    def test_empty_secret_allows_existing_protected_configuration_as_fallback(self):
        self.env("ANILIST_CLIENT_SECRET=\n")
        self.assertIsNone(self.load().client_secret)

    def test_legacy_json_still_provides_public_settings(self):
        (self.root / "auth_config.json").write_text(json.dumps({"anilist_client_id": "999"}))
        config = self.load()
        self.assertEqual(config.client_id, "999")
        self.assertIsNone(config.client_secret)

    def test_invalid_configuration_errors_do_not_echo_values(self):
        for content in ('ANILIST_CLIENT_SECRET="secret-ficticio\n',
                        'ANILIST_CLIENT_ID=secret-ficticio\n',
                        'ANILIST_REDIRECT_URI=https://evil.example/secret-ficticio\n'):
            self.env(content)
            with self.subTest(content=content), self.assertRaises(SyncError) as caught:
                self.load()
            self.assertNotIn("secret-ficticio", str(caught.exception))

    def test_does_not_execute_or_interpolate_dotenv_values(self):
        marker = self.root / "must-not-exist"
        secret = f"$(touch {marker})"
        self.env(f"ANILIST_CLIENT_SECRET='{secret}'\nUNRELATED_VAR=ignored\n")
        self.assertEqual(self.load().client_secret, secret)
        self.assertFalse(marker.exists())

    def test_system_environment_is_not_modified(self):
        environment = {"ANILIST_CLIENT_SECRET": "outside-secret"}
        self.env("ANILIST_CLIENT_SECRET=inside-secret\n")
        self.assertEqual(self.load(environment).client_secret, "outside-secret")
        self.assertEqual(environment, {"ANILIST_CLIENT_SECRET": "outside-secret"})


if __name__ == "__main__":
    unittest.main()
