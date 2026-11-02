"""Numeração automática, falhas de compilação e exclusão entre builds."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
import build as installer_build
from build_version import next_version, parse_version, read_version


class VersionTests(unittest.TestCase):
    def test_increments_patch_numerically(self):
        self.assertEqual(next_version("1.6.9"), "1.6.10")

    def test_manual_version_must_advance(self):
        self.assertEqual(next_version("1.6.1", "2.0.0"), "2.0.0")
        for value in ("1.6.1", "1.5.9"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                next_version("1.6.1", value)

    def test_rejects_invalid_or_out_of_range_msi_versions(self):
        for value in ("v1.6.1", "1.6", "1.6.1.0", "01.6.1", "256.0.0", "1.256.0",
                      "1.6.65536", "1.6.-1", "1.6.1\n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_version(value)
        self.assertEqual(parse_version("255.255.65535"), (255, 255, 65535))

    def test_patch_overflow_requires_explicit_minor_or_major(self):
        with self.assertRaises(ValueError):
            next_version("1.6.65535")
        self.assertEqual(next_version("1.6.65535", "1.7.0"), "1.7.0")


class CompileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Path(self.folder.name)
        (self.project / "VERSION").write_text("1.6.1\n", encoding="utf-8")

    def test_records_version_only_after_build_and_verification_succeed(self):
        def run(command, **kwargs):
            self.assertEqual(read_version(self.project), "1.6.1")
            self.assertEqual(kwargs["env"]["APP_BUILD_VERSION"], "1.6.2")
            self.assertTrue((self.project / "build" / ".compile.lock").exists())

        with patch.object(installer_build.subprocess, "run", side_effect=run) as runner:
            self.assertEqual(installer_build.compile_installer(self.project), "1.6.2")
        self.assertEqual([Path(call.args[0][1]).name for call in runner.call_args_list],
                         ["windows.py", "verify.py"])
        self.assertEqual(read_version(self.project), "1.6.2")
        self.assertFalse((self.project / "build" / ".compile.lock").exists())

    def test_build_or_verification_failure_preserves_current_version(self):
        failure = subprocess.CalledProcessError(1, "build")
        for outcomes in ([failure], [None, failure]):
            with self.subTest(outcomes=outcomes):
                with patch.object(installer_build.subprocess, "run", side_effect=outcomes):
                    with self.assertRaises(subprocess.CalledProcessError):
                        installer_build.compile_installer(self.project)
                self.assertEqual(read_version(self.project), "1.6.1")
                self.assertFalse((self.project / "build" / ".compile.lock").exists())

    def test_explicit_version_is_shared_by_build_verification_and_version_file(self):
        with patch.object(installer_build.subprocess, "run") as runner:
            installer_build.compile_installer(self.project, "1.7.0")
        self.assertEqual(read_version(self.project), "1.7.0")
        for call in runner.call_args_list:
            self.assertEqual(call.kwargs["env"]["APP_BUILD_VERSION"], "1.7.0")

    def test_invalid_version_does_not_start_build(self):
        with patch.object(installer_build.subprocess, "run") as runner:
            with self.assertRaises(ValueError):
                installer_build.compile_installer(self.project, "1.0.0")
        runner.assert_not_called()
        self.assertEqual(read_version(self.project), "1.6.1")

    def test_concurrent_build_is_refused_without_removing_its_lock(self):
        lock = self.project / "build" / ".compile.lock"
        lock.parent.mkdir()
        lock.write_text("123", encoding="utf-8")
        with patch.object(installer_build.subprocess, "run") as runner:
            with self.assertRaises(RuntimeError):
                installer_build.compile_installer(self.project)
        runner.assert_not_called()
        self.assertEqual(lock.read_text(encoding="utf-8"), "123")


if __name__ == "__main__":
    unittest.main()
