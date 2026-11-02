"""Arquivos instalados e dados locais usam pastas distintas, sem dados reais."""
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app_config
import app_paths
import sync_anilist


class InstalledPathsTests(unittest.TestCase):
    def test_frozen_app_uses_executable_assets_and_writable_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe = base / "installed" / "app.exe"
            local = base / "userdata"
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "executable", str(exe)), \
                    patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
                paths = runpy.run_path(app_paths.__file__)
            self.assertEqual(paths["RESOURCE_ROOT"], exe.parent.resolve())
            self.assertEqual(paths["DATA_ROOT"], local / "CrunchyrollAniListSync")

    def test_source_mode_keeps_existing_workspace_paths(self):
        with patch.object(sys, "frozen", False, create=True):
            paths = runpy.run_path(app_paths.__file__)
        self.assertEqual(paths["DATA_ROOT"], Path(app_paths.__file__).resolve().parent)
        self.assertEqual(paths["DATA_ROOT"], paths["RESOURCE_ROOT"])

    def test_installed_config_uses_local_env_with_public_bundled_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            resources, data = Path(folder) / "assets", Path(folder) / "data"
            resources.mkdir()
            data.mkdir()
            (resources / "auth_config.json").write_text(json.dumps({"anilist_client_id": "123"}))
            (data / ".env").write_text("ANILIST_CLIENT_SECRET=fake-local-secret\n")
            with patch.object(app_config, "RESOURCE_ROOT", resources), patch.object(app_config, "DATA_ROOT", data):
                config = app_config.load_anilist_config(environ={})
            self.assertEqual(config.client_id, "123")
            self.assertEqual(config.client_secret, "fake-local-secret")
            with patch.object(sync_anilist, "DATA_ROOT", data):
                self.assertEqual(sync_anilist.new_run_folder().parent, data / "execucoes")
