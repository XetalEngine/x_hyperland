"""Run the complete KVM editor with disposable VM and interface state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class InterfaceTests(unittest.TestCase):
    def test_visibility_survives_profile_rebuilds_and_does_not_change_vm_configuration(self):
        code = r'''
import copy, json, sys
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtCore import QEvent, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton
sys.path.insert(0, sys.argv[2])
import app as kvm
from interface_settings import InterfaceSettingsDialog, read_preferences, write_preferences
root = Path(sys.argv[1]); kvm.ROOT = root/'kvm'
kvm.portable.prepare()
qt = QApplication([]); kvm.desktop_theme.install(qt, kvm.backend_theme.build_stylesheet('#65d5cb'))
path = kvm.ROOT/'state/interface.json'
write_preferences(path, dict(show_window_controls=False, hidden_pages=['Wizard', 'Memory', 'TPM']))
window = kvm.KVMSettings()
try:
    assert window.window_controls.isHidden()
    assert not window.app_settings_button.isHidden()
    original = copy.deepcopy(window.cfg.data)
    assert window.navigation.items['Memory'].isHidden()
    window._select_tab_by_name('Memory')
    assert window.tabs.currentWidget() is window.tab_mem
    assert window.navigation.items['Memory'].isHidden(), 'Direct navigation lost the hidden choice'
    values = dict(show_window_controls=True, hidden_pages=['Wizard', 'Memory', 'TPM'])
    window.apply_interface_preferences(values)
    assert not window.window_controls.isHidden()
    assert window.cfg.data == original, 'Appearance changed VM settings'
    for profile in ('macos', 'windows'):
        window.switch_profile(profile)
        assert window.navigation.items['Memory'].isHidden()
        assert window.navigation.items['TPM'].isHidden()
        assert window.navigation.items['Boot Arguments'].isHidden() == (profile == 'windows')
    from navigation import PAGES
    all_pages = [entry[0] for entry in PAGES]
    window.apply_interface_preferences(dict(show_window_controls=False, hidden_pages=all_pages))
    assert all(item.isHidden() for item in window.navigation.items.values())
    assert not window.app_settings_button.isHidden()
    window.apply_interface_preferences(dict(show_window_controls=False, hidden_pages=[]))
    assert not window.navigation.items['Memory'].isHidden()
    assert not window.navigation.items['Wizard'].isHidden()
    assert window.navigation.items['Boot Arguments'].isHidden(), 'Show all exposed a macOS-only page in Windows'
    observed = {}
    before = path.read_bytes()
    config_before = copy.deepcopy(window.cfg.data)
    def inspect_about():
        settings = window.findChild(QDialog, 'interfaceSettingsDialog')
        if settings is None: return
        try:
            settings.findChild(QPushButton, 'aboutApplicationButton').click()
            about = settings.findChild(QDialog, 'fusionAboutDialog')
            observed['name'] = about.findChild(QLabel, 'aboutAppName').text()
            observed['credit'] = about.findChild(QLabel, 'aboutCredits').text()
            about.close()
        finally:
            settings.reject()
    QTimer.singleShot(0, inspect_about)
    window.open_interface_settings()
    assert observed == dict(name='KVM Settings', credit='Built on vmstart_2.')
    assert path.read_bytes() == before and window.cfg.data == config_before
    print('PASS: full KVM editor, profile rebuilds, hidden direct links, About from Settings and VM configuration preservation')
finally:
    window.tabs.blockSignals(True); window.tab_wizard.blockSignals(True)
    window.deleteLater(); qt.sendPostedEvents(None, QEvent.Type.DeferredDelete)
'''
        with tempfile.TemporaryDirectory(prefix='kvm-interface-') as temporary:
            env = dict(os.environ, XETAL_KVM_DATA=str(Path(temporary)/'vm-data'), QT_QPA_PLATFORM='offscreen',
                       QT_QPA_PLATFORMTHEME='', DBUS_SESSION_BUS_ADDRESS='unix:path='+temporary+'/no-bus')
            env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
            result = subprocess.run([sys.executable, '-c', code, temporary, str(ROOT)], env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
