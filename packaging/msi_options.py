"""Opção de configuração da extensão após concluir o MSI interativo."""
from msilib import add_data

from cx_Freeze.command.bdist_msi import bdist_msi


class ExtensionInstaller(bdist_msi):
    def add_exit_dialog(self):
        super().add_exit_dialog()
        # No Property row: the checkbox starts unchecked on every installation.
        add_data(self.db, "Control", [
            ("ExitDialog", "ChromeExtension", "CheckBox", 15, 180, 330, 20, 3,
             "SETUP_CHROME_EXTENSION", "Configurar extensão no Chrome (opcional)", "Finish", None),
            ("ExitDialog", "ChromeExtensionHelp", "Text", 15, 202, 330, 30, 3,
             None, "Abre o Chrome, a pasta da extensão e as instruções. "
             "Você conclui a instalação no navegador.", None, None),
        ])
        view = self.db.OpenView(
            "UPDATE `Control` SET `Control_Next` = 'ChromeExtension' "
            "WHERE `Dialog_` = 'ExitDialog' AND `Control` = 'Finish'"
        )
        view.Execute(None)
        view.Close()
        view = self.db.OpenView(
            "UPDATE `ControlEvent` SET `Ordering` = 1 "
            "WHERE `Dialog_` = 'ExitDialog' AND `Control_` = 'Finish' "
            "AND `Event` = 'EndDialog'"
        )
        view.Execute(None)
        view.Close()
        add_data(self.db, "CheckBox", [("SETUP_CHROME_EXTENSION", "1")])
        removing = 'REMOVE="ALL" OR MaintenanceForm_Action="Remove"'
        add_data(self.db, "ControlCondition", [
            ("ExitDialog", control, "Hide", removing)
            for control in ("ChromeExtension", "ChromeExtensionHelp")
        ])
        # Type 226: run from TARGETDIR, asynchronously, without waiting for the
        # helper or treating its exit code as an installation failure.
        add_data(self.db, "CustomAction", [
            ("SetupChromeExtension", 226, "TARGETDIR",
             '"[TARGETDIR]CrunchyrollAniListSync.exe" --install-chrome-extension'),
        ])
        add_data(self.db, "ControlEvent", [
            ("ExitDialog", "Finish", "DoAction", "SetupChromeExtension",
             'SETUP_CHROME_EXTENSION=1 AND NOT (' + removing + ')', 0),
        ])
