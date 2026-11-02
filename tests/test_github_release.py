"""Publicação com Git real temporário e API simulada, sem releases externas."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
import build as installer_build
import github_release as release


def asset(name, data):
    return {"name": name, "size": len(data), "state": "uploaded",
            "digest": "sha256:" + hashlib.sha256(data).hexdigest()}


class FakeGitHub:
    repository = "owner/repo"
    branch = "main"
    base = "https://api.github.com/repos/owner/repo"

    def __init__(self):
        self.current = None
        self.assets = {}
        self.calls = []
        self.fail_after_upload = False
        self.resumes = []

    def prepare(self, project, version, resume=False):
        self.resumes.append(resume)

    def git_environment(self):
        return None

    def release(self, version):
        return self.current

    def request(self, method, url, payload=None, content_type=None):
        self.calls.append((method, url, payload))
        if method == "POST" and url.endswith("/releases"):
            self.current = {"id": 1, "tag_name": payload["tag_name"], "draft": True,
                            "prerelease": False, "upload_url": "https://uploads.github.com/assets{?name}",
                            "html_url": "https://github.com/owner/repo/releases/tag/" + payload["tag_name"],
                            "assets": []}
            return self.current
        if method == "GET" and url.endswith("/assets"):
            return list(self.assets.values())
        if method == "POST" and "?name=" in url:
            name = url.split("?name=")[1]
            self.assets[name] = asset(name, payload)
            self.current["assets"] = list(self.assets.values())
            if self.fail_after_upload:
                self.fail_after_upload = False
                raise OSError("Resposta perdida depois do upload")
            return self.assets[name]
        if method == "PATCH":
            if len(self.assets) != 2:
                raise AssertionError("A publicação precisa aguardar os dois anexos")
            self.current["draft"] = False
            return self.current
        raise AssertionError((method, url))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.project = root / "project"
        self.project.mkdir()
        self.remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)], capture_output=True, check=True)
        release.git(self.project, "init", "-b", "main")
        release.git(self.project, "config", "user.name", "Release Test")
        release.git(self.project, "config", "user.email", "release@example.invalid")
        release.git(self.project, "config", "commit.gpgsign", "false")
        release.git(self.project, "config", "tag.gpgsign", "false")
        release.git(self.project, "remote", "add", "origin", str(self.remote))
        (self.project / ".gitignore").write_text("build/\ndist/\n.env\n*.tmp\n", encoding="utf-8")
        (self.project / "VERSION").write_text("1.6.1\n", encoding="utf-8")
        (self.project / "app.py").write_text("old code\n", encoding="utf-8")
        (self.project / "removed.py").write_text("removed code\n", encoding="utf-8")
        release.git(self.project, "add", "--all")
        release.git(self.project, "commit", "-m", "Initial test code")
        self.original = release.git(self.project, "rev-parse", "HEAD").stdout.strip()
        (self.project / "app.py").write_text("new code\n", encoding="utf-8")
        (self.project / "new.py").write_text("new module\n", encoding="utf-8")
        (self.project / "removed.py").unlink()
        (self.project / ".env").write_text("EXAMPLE=ignored-private-value\n", encoding="utf-8")
        self.github = FakeGitHub()

    def build(self, project, environment):
        version = environment["APP_BUILD_VERSION"]
        (project / "dist").mkdir(exist_ok=True)
        (project / "dist" / f"CrunchyrollAniListSync-{version}-x64.msi").write_bytes(b"fake verified MSI")

    def compile(self):
        with patch.object(installer_build.github_release, "GitHub", return_value=self.github):
            with patch.object(installer_build, "build_and_verify", side_effect=self.build) as builder:
                result = installer_build.compile_installer(self.project, publish=True)
        return result, builder

    def test_compile_commits_exact_code_pushes_tag_and_publishes_both_assets(self):
        result, builder = self.compile()
        self.assertEqual(result, "1.6.2")
        builder.assert_called_once()
        tag = "refs/tags/v1.6.2"
        head = release.git(self.project, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(head, self.original)
        self.assertEqual(release.git(self.project, "rev-parse", tag + "^{commit}").stdout.strip(), head)
        self.assertEqual(release.git(self.project, "show", tag + ":app.py").stdout, "new code\n")
        self.assertEqual(release.git(self.project, "show", tag + ":VERSION").stdout, "1.6.2\n")
        names = release.git(self.project, "ls-tree", "--name-only", tag).stdout.splitlines()
        self.assertIn("new.py", names)
        self.assertNotIn("removed.py", names)
        self.assertNotIn(".env", names)
        remote = release.git(self.project, "ls-remote", "origin", tag + "^{}").stdout
        self.assertTrue(remote.startswith(head + "\t"))
        self.assertFalse(self.github.current["draft"])
        self.assertEqual(len(self.github.assets), 2)
        self.assertFalse((self.project / "build" / "pending-release.json").exists())
        self.assertFalse(release.git(self.project, "status", "--porcelain").stdout)

    def test_lost_upload_response_resumes_without_build_bump_new_commit_or_duplicate_asset(self):
        self.github.fail_after_upload = True
        with self.assertRaises(OSError):
            self.compile()
        pending = self.project / "build" / "pending-release.json"
        self.assertTrue(pending.exists())
        self.assertTrue(self.github.current["draft"])
        first_head = release.git(self.project, "rev-parse", "HEAD").stdout.strip()
        result, builder = self.compile()
        builder.assert_not_called()
        self.assertEqual(result, "1.6.2")
        self.assertEqual(release.git(self.project, "rev-parse", "HEAD").stdout.strip(), first_head)
        self.assertEqual(self.github.resumes, [False, True])
        self.assertEqual(sum("?name=" in url for _, url, _ in self.github.calls), 2)
        self.assertFalse(pending.exists())

    def test_source_edit_during_build_prevents_version_commit_tag_and_release(self):
        def changed_build(project, environment):
            self.build(project, environment)
            (project / "app.py").write_text("edited during build", encoding="utf-8")

        with patch.object(installer_build.github_release, "GitHub", return_value=self.github):
            with patch.object(installer_build, "build_and_verify", side_effect=changed_build):
                with self.assertRaisesRegex(RuntimeError, "durante a compilação"):
                    installer_build.compile_installer(self.project, publish=True)
        self.assertEqual((self.project / "VERSION").read_text().strip(), "1.6.1")
        self.assertEqual(release.git(self.project, "rev-parse", "HEAD").stdout.strip(), self.original)
        self.assertIsNone(self.github.current)

    def test_pending_changed_source_or_installer_is_refused(self):
        self.github.fail_after_upload = True
        with self.assertRaises(OSError):
            self.compile()
        path = self.project / "dist" / "CrunchyrollAniListSync-1.6.2-x64.msi"
        original = path.read_bytes()
        path.write_bytes(b"different MSI")
        with self.assertRaisesRegex(RuntimeError, "instalador pendente"):
            self.compile()
        path.write_bytes(original)
        (self.project / "app.py").write_text("different source", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "código mudou"):
            self.compile()
        self.assertTrue(self.github.current["draft"])

    def test_pending_release_blocks_local_build_and_other_version(self):
        self.github.fail_after_upload = True
        with self.assertRaises(OSError):
            self.compile()
        with self.assertRaisesRegex(RuntimeError, "publicação pendente"):
            installer_build.compile_installer(self.project, publish=False)
        with self.assertRaisesRegex(RuntimeError, "outra VERSION"):
            installer_build.compile_installer(self.project, requested="1.7.0", publish=True)

    def test_existing_different_asset_is_never_overwritten_or_published(self):
        self.github.fail_after_upload = True
        with self.assertRaises(OSError):
            self.compile()
        existing = next(iter(self.github.assets.values()))
        existing["digest"] = "sha256:wrong"
        with self.assertRaisesRegex(RuntimeError, "não corresponde"):
            self.compile()
        self.assertTrue(self.github.current["draft"])

    def test_preflight_failure_does_not_compile_or_change_version(self):
        with patch.object(installer_build.github_release, "GitHub", side_effect=RuntimeError("auth")):
            with patch.object(installer_build, "build_and_verify") as builder:
                with self.assertRaisesRegex(RuntimeError, "auth"):
                    installer_build.compile_installer(self.project, publish=True)
        builder.assert_not_called()
        self.assertEqual((self.project / "VERSION").read_text().strip(), "1.6.1")


class GitHubApiTests(unittest.TestCase):
    def test_repository_parses_https_and_ssh(self):
        for remote in ("https://github.com/owner/repo.git", "git@github.com:owner/repo.git",
                       "ssh://git@github.com/owner/repo.git", "https://github.com/owner/repo"):
            self.assertEqual(release.repository_name(remote), "owner/repo")
        with self.assertRaises(RuntimeError):
            release.repository_name("https://another.example/owner/repo.git")

    def test_api_rejects_unexpected_upload_host_before_sending_credentials(self):
        github = release.GitHub.__new__(release.GitHub)
        with self.assertRaises(RuntimeError):
            github.request("POST", "https://untrusted.example/assets", b"MSI")

    def test_release_404_is_absent_but_auth_failure_is_not_hidden(self):
        github = release.GitHub.__new__(release.GitHub)
        github.base = "https://api.github.com/repos/owner/repo"
        for status in (404, 401):
            error = urllib.error.HTTPError(github.base, status, "test", {}, None)
            with patch.object(github, "request", side_effect=error):
                if status == 404:
                    self.assertIsNone(github.release("1.6.2"))
                else:
                    with self.assertRaises(urllib.error.HTTPError):
                        github.release("1.6.2")


if __name__ == "__main__":
    unittest.main()
