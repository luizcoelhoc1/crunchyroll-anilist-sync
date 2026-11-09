"""Assistente local e entrada do MSI sem abrir navegador ou contas reais."""
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extension_setup as setup


class ExtensionSetupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="extensao teste ")
        self.addCleanup(folder.cleanup)
        self.resources = Path(folder.name)
        self.extension = self.resources / "extensao_chrome"
        self.extension.mkdir()
        (self.extension / "manifest.json").write_text("{}", encoding="utf-8")
        for name, value in (("RESOURCE_ROOT", self.resources), ("messagebox", Mock()),
                            ("open_chrome", Mock()), ("tk", Mock())):
            patcher = patch.object(setup, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(setup.os, "startfile", create=True)
        self.open_folder = patcher.start()
        self.addCleanup(patcher.stop)

    def test_opens_installed_assets_and_explains_manual_confirmation(self):
        parent = Mock()
        setup.show_extension_setup(parent=parent)
        self.open_folder.assert_called_once_with(str(self.extension))
        setup.open_chrome.assert_called_once_with("chrome://extensions")
        text = setup.messagebox.showinfo.call_args.args[1]
        self.assertIn(str(self.extension), text)
        self.assertIn("Carregar sem compactação", text)
        self.assertNotIn("ZIP", text)
        self.assertEqual(setup.messagebox.showinfo.call_args.kwargs["parent"], parent)
        setup.tk.Tk.assert_not_called()

    def test_missing_assets_explain_reinstall_without_opening_chrome(self):
        (self.extension / "manifest.json").unlink()
        setup.show_extension_setup(parent=Mock())
        setup.messagebox.showerror.assert_called_once()
        setup.open_chrome.assert_not_called()
        self.open_folder.assert_not_called()

    def test_missing_chrome_still_opens_folder_and_shows_instructions(self):
        setup.open_chrome.side_effect = setup.SyncError("Chrome ausente")
        setup.show_extension_setup()
        self.open_folder.assert_called_once()
        self.assertIn("Abra ou instale", setup.messagebox.showinfo.call_args.args[1])
        setup.tk.Tk.return_value.withdraw.assert_called_once()
        setup.tk.Tk.return_value.destroy.assert_called_once()

    def test_folder_error_does_not_skip_chrome_or_instructions(self):
        self.open_folder.side_effect = OSError("Indisponível")
        setup.show_extension_setup(parent=Mock())
        setup.open_chrome.assert_called_once()
        self.assertIn("Use o caminho abaixo", setup.messagebox.showinfo.call_args.args[1])

    def test_installer_argument_only_runs_setup_and_normal_start_still_runs_app(self):
        entry = Path(__file__).resolve().parents[1] / "iniciar.pyw"
        interface = Mock()
        with patch.dict(sys.modules, {"interface": interface}), \
                patch.object(setup, "show_extension_setup") as show:
            with patch.object(sys, "argv", [str(entry), "--install-chrome-extension"]):
                runpy.run_path(str(entry))
            show.assert_called_once_with()
            interface.start_gui.assert_not_called()
            with patch.object(sys, "argv", [str(entry)]):
                runpy.run_path(str(entry))
            interface.start_gui.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
