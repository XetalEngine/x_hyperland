"""Shortcut regression tests; all settings and desktop entries are temporary."""
import copy
import os
import shlex
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gi.repository import Gio
from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtGui import QIcon
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

import app
import catalog
import shortcuts
import pins
from editor import ShortcutEditor

QT = QApplication.instance() or QApplication([])
QT.setStyle('Fusion')
QT.setStyleSheet(app.STYLE)
QIcon.setThemeSearchPaths([str(Path.home()/'.local/share/icons'), '/usr/share/icons'])
QIcon.setThemeName('Papirus-Dark')


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.desktop = self.root/'example.desktop'
        self.original = '[Desktop Entry]\nType=Application\nName=Example\nExec=/usr/bin/printf "hello world" %U\nIcon=utilities-terminal\nTerminal=false\nCategories=Utility;\n'
        self.desktop.write_text(self.original)
        self.native = Gio.DesktopAppInfo.new_from_filename(str(self.desktop))
        self.patches = [patch.object(shortcuts, 'STATE', self.root/'shortcuts.json'),
                        patch.object(app.geometry, 'STATE', self.root/'window.json'),
                        patch.object(shortcuts, 'ICONS', self.root/'icons'),
                        patch.object(catalog, 'LOCAL', self.root/'favorites.json'),
                        patch.object(pins, 'STATE', self.root/'bar-pins.json'),
                        patch.object(catalog, 'kde_favorites', return_value=['example.desktop']),
                        patch.object(Gio.AppInfo, 'get_all', return_value=[self.native])]
        for p in self.patches: p.start()
        self.entry = shortcuts.Entry('example.desktop', self.native)

    def tearDown(self):
        self.assertEqual(self.desktop.read_text(), self.original)
        for widget in QApplication.topLevelWidgets(): widget.close()
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_edit_persists_without_changing_original_and_reset_restores(self):
        shortcuts.save(self.entry, {**self.entry.fields, 'name': 'My tool', 'terminal': True,
                                   'command': '/usr/bin/printf "two words"', 'directory': str(self.root)})
        saved = catalog.applications()['example.desktop']
        self.assertEqual(saved.get_display_name(), 'My tool')
        self.assertTrue(saved.fields['terminal'])
        self.assertEqual(saved.argv(), ['/usr/bin/printf', 'two words'])
        shortcuts.reset(saved)
        self.assertEqual(catalog.applications()['example.desktop'].get_display_name(), 'Example')

    def test_favorite_copy_is_independent_of_original(self):
        ident = shortcuts.duplicate(self.entry, {**self.entry.fields, 'name': 'Separate favorite'})
        catalog.pin(ident, True)
        saved = catalog.applications()[ident]
        self.assertTrue(saved.custom)
        shortcuts.save(saved, {**saved.fields, 'command': '/usr/bin/printf changed'})
        self.assertIn(ident, catalog.favorites())
        self.assertEqual(catalog.applications()['example.desktop'].fields['command'], self.entry.fields['command'])
        shortcuts.remove_copy(saved)
        catalog.pin(ident, False)
        self.assertNotIn(ident, catalog.applications())
        self.assertNotIn(ident, catalog.favorites())

    def test_argv_preserves_quoted_arguments_and_expands_fields_once(self):
        fields = {**self.entry.fields, 'name': 'Name %f', 'icon': 'icon-name'}
        argv = shortcuts.command_argv('/usr/bin/printf "two words" %%f %c %i %k %U', fields, '/tmp/source.desktop')
        self.assertEqual(argv, ['/usr/bin/printf','two words','%f','Name %f','--icon','icon-name','/tmp/source.desktop'])
        with self.assertRaises(ValueError): shortcuts.command_argv('/usr/bin/printf %z', fields)

    def test_terminal_uses_local_kitty_config_and_does_not_run_shell(self):
        saved = shortcuts.Entry('example.desktop', self.native, {'terminal': True, 'directory': str(self.root)})
        with patch.object(shortcuts.subprocess, 'Popen') as spawn:
            saved.launch()
        argv = spawn.call_args.args[0]
        self.assertEqual(argv[:3], ['kitty','--config',str(shortcuts.ROOT/'kitty.conf')])
        self.assertEqual(argv[-3:], ['-e','/usr/bin/printf','hello world'])
        self.assertEqual(spawn.call_args.kwargs['cwd'], str(self.root))
        self.assertNotIn('shell', spawn.call_args.kwargs)

    def test_dolphin_copy_keeps_isolated_profile(self):
        saved = shortcuts.Entry('copy.desktop', self.native,
            {**self.entry.fields, 'command': 'dolphin %u'}, origin='org.kde.dolphin.desktop', custom=True)
        with patch.object(shortcuts.subprocess, 'Popen') as spawn: saved.launch()
        self.assertEqual(spawn.call_args.args[0], [str(shortcuts.ROOT/'scripts/dolphin.sh')])

    def test_kitty_app_and_favorite_copy_use_hyprland_profile(self):
        desktop=self.root/'kitty.desktop'
        desktop.write_text('[Desktop Entry]\nType=Application\nName=Kitty\nExec=kitty\nTerminal=false\n')
        native=Gio.DesktopAppInfo.new_from_filename(str(desktop))
        for saved in [shortcuts.Entry('kitty.desktop',native),
                      shortcuts.Entry('copy.desktop',native,{'name':'My terminal'},origin='kitty.desktop',custom=True)]:
            with patch.object(shortcuts.subprocess,'Popen') as spawn:saved.launch()
            self.assertEqual(spawn.call_args.args[0],['kitty','--config',str(shortcuts.ROOT/'kitty.conf')])

    def test_floating_preference_persists_and_quotes_command_and_working_folder(self):
        folder=self.root/'folder with $sign and `ticks`';folder.mkdir()
        fields={**self.entry.fields,'floating':True,'directory':str(folder),'command':'/usr/bin/printf "literal $HOME; `id`"'}
        shortcuts.save(self.entry,fields)
        saved=catalog.applications()[self.entry.get_id()]
        self.assertTrue(saved.fields['floating'])
        with (patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':'test'}),
              patch.object(shortcuts.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ok\n','')) as dispatch):
            saved.launch()
        argv=dispatch.call_args.args[0]
        self.assertEqual(argv[:3],['hyprctl','dispatch','exec'])
        command=argv[3];self.assertTrue(command.startswith('[float on] cd '+shlex.quote(str(folder))+' && exec '))
        parsed=shlex.split(command.split(' && exec ',1)[1])
        self.assertEqual(parsed[-2:],['/usr/bin/printf','literal $HOME; `id`'])
        shortcuts.reset(saved);self.assertFalse(catalog.applications()[self.entry.get_id()].fields['floating'])

    def test_floating_and_terminal_launch_combine_and_report_dispatch_failure(self):
        with (patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':'test'}),
              patch.object(shortcuts.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ok\n','')) as dispatch):
            self.entry.launch(terminal=True,floating=True)
        argv=shlex.split(dispatch.call_args.args[0][-1].removeprefix('[float on] exec '))
        self.assertIn('kitty',argv);self.assertIn('--config',argv);self.assertIn('-e',argv)
        with (patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':'test'}),
              patch.object(shortcuts.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','test rejection'))):
            with self.assertRaisesRegex(ValueError,'test rejection'):self.entry.launch(floating=True)

    def test_floating_context_and_shortcut_editor_share_saved_flag(self):
        menu=app.Menu(preview=True)
        actions={action.data():action for action in menu.build_context_menu(self.entry.get_id()).actions()}
        self.assertIn('open-floating',actions);self.assertFalse(actions['toggle-floating'].isChecked())
        menu.perform('toggle-floating',self.entry.get_id())
        saved=catalog.applications()[self.entry.get_id()];self.assertTrue(saved.fields['floating'])
        dialog=ShortcutEditor(saved,menu);self.assertTrue(dialog.floating.isChecked())
        dialog.floating.setChecked(False);dialog.accept();self.assertFalse(dialog.fields['floating'])

    def test_invalid_save_leaves_state_unchanged(self):
        shortcuts.save(self.entry, {**self.entry.fields, 'name': 'Saved'})
        original = shortcuts.STATE.read_bytes()
        for fields in [{**self.entry.fields, 'command': '/not/a/real/program'},
                       {**self.entry.fields, 'directory': '/not/a/real/directory'},
                       {**self.entry.fields, 'command': '/usr/bin/printf "unclosed'}]:
            with self.assertRaises(ValueError): shortcuts.save(self.entry, fields)
            self.assertEqual(shortcuts.STATE.read_bytes(), original)

    def test_icon_is_copied_to_launcher_storage(self):
        icon = self.root/'my icon.svg'
        icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="teal"/></svg>')
        shortcuts.save(self.entry, {**self.entry.fields, 'icon': str(icon)})
        saved = catalog.applications()['example.desktop']
        destination = Path(saved.fields['icon'])
        self.assertEqual(destination.parent, shortcuts.ICONS)
        self.assertEqual(destination.read_bytes(), icon.read_bytes())

    def test_right_click_does_not_launch_and_menu_has_editor_actions(self):
        menu = app.Menu(True); menu.show(); QTest.qWait(220)
        called = []
        menu.launch_app = lambda *args, **kwargs: called.append(args)
        point = menu.grid.visualItemRect(menu.grid.item(0)).center()
        QTest.mouseClick(menu.grid.viewport(), Qt.MouseButton.RightButton, pos=point)
        self.assertEqual(called, [])
        actions = {a.data() for a in menu.build_context_menu('example.desktop').actions()}
        self.assertTrue({'edit','icon','duplicate','pin','terminal','toggle-terminal','copy-command','show-file','reset'} <= actions)
        QTest.mouseClick(menu.grid.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(called, [('example.desktop',)])

    def test_editor_cancel_does_not_write_and_invalid_command_stays_open(self):
        editor = ShortcutEditor(self.entry); editor.show()
        editor.inputs['command'].setText('/does/not/exist')
        editor.accept()
        self.assertTrue(editor.isVisible())
        self.assertIn('Program not found',editor.error.text())
        editor.reject()
        self.assertFalse(shortcuts.STATE.exists())

    def test_launcher_keeps_open_for_modal_editor(self):
        menu = app.Menu(False); menu.show(); QTest.qWait(220)
        menu.started = 0
        menu.interaction_depth = 1
        editor = ShortcutEditor(self.entry,menu); editor.setModal(True); editor.show()
        menu.close_if_outside()
        self.assertTrue(menu.isVisible())
        menu.close()
        self.assertTrue(menu.isVisible())
        editor.reject(); menu.interaction_depth=0; menu.close()


if __name__ == '__main__': unittest.main(verbosity=2)
