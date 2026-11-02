"""Implantação simulada: segredo só no stdin, configuração pública sem segredo."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from app_config import AniListConfig
from oauth_login import REDIRECT_URI

spec = importlib.util.spec_from_file_location("auth_worker_deploy", PROJECT / "cloudflare" / "deploy.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)

SECRET = "private-client-secret-example"
ORIGIN = "https://auth.example.workers.dev"


class AuthDeployTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Path(self.folder.name)
        cli = self.project / "cloudflare" / "node_modules" / "wrangler" / "bin" / "wrangler.js"
        cli.parent.mkdir(parents=True)
        cli.touch()
        (self.project / "auth_config.json").write_text('{"anilist_client_id":"55193"}')

    def test_deployment_uploads_only_expected_secrets_over_stdin_then_writes_public_url(self):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            self.assertNotIn(SECRET, str(command))
            self.assertNotIn(SECRET, str(kwargs["env"]))
            operation = command[2:]
            if operation == ["whoami", "--json"]:
                stdout = '{"loggedIn":true,"authType":"OAuth Token","accounts":[]}'
            elif operation == ["deploy"]:
                stdout = "Uploaded worker\n" + ORIGIN
            elif operation == ["secret", "list"]:
                stdout = '[{"name":"STATE_SECRET"}]'
            else:
                self.assertEqual(operation, ["secret", "bulk"])
                self.assertEqual(json.loads(kwargs["input"]), {
                    "ANILIST_CLIENT_ID": "55193", "ANILIST_CLIENT_SECRET": SECRET})
                stdout = "Secrets uploaded"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"service": "crunchyroll-anilist-auth", "protocol": 1,
                                                "client_id": "55193"}).encode()
        output = StringIO()
        with patch.object(deployment, "load_anilist_config", return_value=AniListConfig("55193", REDIRECT_URI, SECRET)), \
                patch.object(deployment.shutil, "which", return_value="node"), \
                patch.object(deployment.subprocess, "run", side_effect=run), \
                patch.object(deployment.urllib.request, "build_opener") as opener, redirect_stdout(output):
            opener.return_value.open.return_value = response
            self.assertEqual(deployment.deploy(self.project), ORIGIN)
            self.assertEqual(opener.return_value.open.call_args.args[0].get_header("User-agent"),
                             "CrunchyrollAniListSync/1.0")
        self.assertEqual(len(calls), 4)
        public = json.loads((self.project / "auth_config.json").read_text())
        self.assertEqual(public, deployment.public_config("55193", ORIGIN))
        self.assertNotIn(SECRET, output.getvalue())
        self.assertNotIn(SECRET, json.dumps(public))

    def test_login_failure_preserves_public_configuration(self):
        before = (self.project / "auth_config.json").read_bytes()
        with patch.object(deployment, "load_anilist_config", return_value=AniListConfig("55193", REDIRECT_URI, SECRET)), \
                patch.object(deployment.shutil, "which", return_value="node"), \
                patch.object(deployment.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", SECRET)):
            with self.assertRaises(RuntimeError) as caught:
                deployment.deploy(self.project)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertEqual((self.project / "auth_config.json").read_bytes(), before)

    def test_missing_local_secret_stops_before_any_remote_action(self):
        with patch.object(deployment, "load_anilist_config", return_value=AniListConfig("55193", REDIRECT_URI)), \
                patch.object(deployment.subprocess, "run") as remote:
            with self.assertRaises(RuntimeError):
                deployment.deploy(self.project)
        remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
