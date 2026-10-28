"""Favorite hotkeys, conflicts and UI synchronization with temporary bindings only."""
import copy
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt,QTimer,QEvent,QCoreApplication,QThreadPool
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QDialog,QMessageBox
import app
import catalog
import hotkeys
import hotkey_dialog
import launch
import shortcuts

QT=QApplication.instance() or QApplication([])
QT.setStyle('Fusion')


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.calls=[]
        self.records=hotkeys.keys.parse('bind = $mainMod, Q, exec, $terminal\n'
            'bind = SUPER, Return, exec, $terminal\nbind = SUPER, E, exec, $fileManager\n'
            'bind = SUPER, K, exec, control-center\n')
        self.records[-1].protected=True
        (self.root/'keybindings.conf').write_text(hotkeys.keys.serialize(self.records))
        (self.root/'hyprland.conf').write_text('$mainMod = SUPER\n$terminal = kitty --config '+str(shortcuts.ROOT/'kitty.conf')+'\n'
            '$fileManager = '+str(shortcuts.ROOT/'scripts/dolphin.sh')+'\n'+hotkeys.keys.SOURCE+'\n')
        self.values=hotkeys.keys.variables((self.root/'hyprland.conf').read_text())
        self.store=hotkeys.keys.Store(self.root,self.root/'history',self.runner)
        self.entry=shortcuts.Entry('example.desktop',None,{'name':'Example tool','command':'/usr/bin/printf hello',
            'icon':'applications-development'},custom=True)
        self.windows=[]

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(2000)
        for window in reversed(self.windows):window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def runner(self,argv):
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv,0,'config ok' if argv[0]=='Hyprland' else ('ok\n' if argv[1]=='reload' else ''),'')

    def dialog(self):
        result=hotkey_dialog.HotkeyDialog(self.entry,store=self.store);self.windows.append(result);result.show()
        return result

    def add_binding(self,key='F8',enabled=True):
        records=hotkeys.edited(self.records,self.entry,None,'SUPER',key,enabled)
        hotkeys.keys.atomic_write(self.store.path,hotkeys.keys.serialize(records).encode())
        return records[-1]

    def settle(self,dialog):
        for _ in range(100):
            QTest.qWait(15)
            if not dialog.busy:return
        self.fail('Apply did not complete')

    def test_existing_variable_aliases_match_kitty_and_isolated_dolphin(self):
        terminal=shortcuts.Entry('kitty.desktop',None,{'name':'Kitty','command':'kitty'})
        files=shortcuts.Entry('org.kde.dolphin.desktop',None,{'name':'Dolphin','command':'dolphin %U'})
        self.assertEqual([hotkeys.display(b,self.values) for b in hotkeys.matches(terminal,self.records,self.values)],['Super+Q','Super+Enter'])
        self.assertEqual([b.key for b in hotkeys.matches(files,self.records,self.values)],['E'])
        extra=copy.deepcopy(self.records[0]);extra.args+=' -e something-else'
        self.assertEqual(hotkeys.matches(terminal,[extra],self.values),[])

    def test_index_caches_commands_and_refreshes_after_binding_and_shortcut_edits(self):
        index=hotkeys.ShortcutIndex(store=self.store)
        terminal=shortcuts.Entry('kitty.desktop',None,{'name':'Kitty','command':'kitty'})
        with patch.object(hotkeys,'tokens',side_effect=AssertionError('Bindings must already be indexed')):
            self.assertEqual(index.labels(terminal),['Super+Q','Super+Enter'])
            terminal.fields['command']='unrelated-app'
            self.assertEqual(index.labels(terminal),[])
        terminal.fields['command']='kitty'
        records,_=self.store.load();records[0].key='T'
        hotkeys.keys.atomic_write(self.store.path,hotkeys.keys.serialize(records).encode());index.reload()
        self.assertEqual(index.labels(terminal),['Super+T','Super+Enter'])
        index.deleteLater()

    def test_encoded_identity_follows_shortcut_edits_without_matching_another_copy(self):
        self.entry.app_id='custom-$HOME#name, with spaces.desktop'
        b=hotkeys.edited(self.records,self.entry,None,'$mainMod CTRL','F8')[-1]
        self.assertEqual(b.mods,'$mainMod CTRL')
        self.assertNotIn('$HOME',b.args);self.assertNotIn('#',b.args);self.assertNotIn(',',b.args)
        self.entry.fields.update(command='/usr/bin/printf changed',directory=str(self.root),terminal=True)
        self.assertEqual(hotkeys.matches(self.entry,[b],self.values),[b])
        other=shortcuts.Entry('other.desktop',None,self.entry.fields,custom=True)
        self.assertEqual(hotkeys.matches(other,[b],self.values),[])

    def test_launch_wrapper_resolves_latest_shortcut_preferences(self):
        argv=shlex.split(hotkeys.launch_command(self.entry.get_id()))[1:]
        with (patch.object(sys,'argv',argv),patch.dict(os.environ,{'HYPRLAND_INSTANCE_SIGNATURE':'test'}),
              patch.object(catalog,'applications',return_value={self.entry.get_id():self.entry}),
              patch.object(shortcuts,'leave_dashboard') as leave,patch.object(self.entry,'launch') as run):
            self.assertEqual(launch.main(),0);run.assert_called_once_with();leave.assert_called_once()

    def test_apply_uses_shared_store_preserves_recovery_and_categories(self):
        d=self.dialog();d.mods.setText('SUPER CTRL');d.key.setText('F8');d.apply();self.settle(d)
        self.assertEqual(d.result(),QDialog.DialogCode.Accepted)
        records,_=self.store.load();b=hotkeys.matches(self.entry,records,self.values)[0]
        self.assertEqual((b.key,b.mods,b.category,b.label),('F8','SUPER CTRL','Applications','Open Example tool'))
        self.assertEqual(records[-2],self.records[-1]);self.assertEqual(self.calls[-2:],[['hyprctl','reload'],['hyprctl','configerrors']])
        self.assertTrue(list((self.root/'history').glob('keybindings-*.conf')))

    def test_conflict_and_ordinary_typing_are_blocked_before_apply(self):
        original=self.store.path.read_bytes();d=self.dialog();d.key.setText('q')
        self.assertFalse(d.apply_button.isEnabled());self.assertIn('same shortcut',d.message.text())
        d.mods.setText('CTRL');d.key.setText('C')
        self.assertFalse(d.apply_button.isEnabled());self.assertIn('use SUPER',d.message.text())
        d.apply();self.assertEqual(self.store.path.read_bytes(),original);self.assertEqual(self.calls,[])

    def test_external_save_refused_and_reload_keeps_other_window_changes(self):
        d=self.dialog();d.key.setText('F8');self.add_binding('F9');outside=self.store.path.read_bytes()
        d.apply();self.settle(d)
        self.assertIn('changed outside',d.message.text());self.assertEqual(self.store.path.read_bytes(),outside)
        self.assertTrue(d.isVisible());d.reload();self.assertEqual(d.key.text(),'F9')

    def test_remove_is_confirmed_and_does_not_remove_other_launch_hotkeys(self):
        existing=self.add_binding();second=hotkeys.edited(self.store.load()[0],self.entry,None,'SUPER','F9')
        hotkeys.keys.atomic_write(self.store.path,hotkeys.keys.serialize(second).encode())
        d=self.dialog();before=self.store.path.read_bytes()
        QTimer.singleShot(10,lambda:QApplication.activeModalWidget().button(QMessageBox.StandardButton.Cancel).click())
        d.remove_hotkey();self.assertEqual(self.store.path.read_bytes(),before)
        def confirm():
            box=QApplication.activeModalWidget();next(b for b in box.buttons() if b.text()=='Remove hotkey').click()
        QTimer.singleShot(10,confirm);d.remove_hotkey();self.settle(d)
        records,_=self.store.load();self.assertNotIn(existing.id,[b.id for b in records])
        self.assertEqual([b.key for b in hotkeys.matches(self.entry,records,self.values)],['F9'])

    def test_disabled_hotkey_can_be_selected_and_reenabled(self):
        existing=self.add_binding(enabled=False);d=self.dialog()
        self.assertIn('disabled',d.choice.currentText());self.assertFalse(d.enabled.isChecked())
        d.enabled.setChecked(True);d.apply();self.settle(d)
        self.assertTrue(next(b for b in self.store.load()[0] if b.id==existing.id).enabled)

    def test_capture_records_modifiers_and_cancel_restores_only_owned_mode(self):
        d=self.dialog();state=['reset'];calls=[]
        def compositor(*args):
            calls.append(args)
            if args==('submap',):return state[0]
            state[0]=args[-1];return 'ok'
        with patch.object(hotkey_dialog,'compositor',side_effect=compositor):
            d.begin_capture();QTest.keyClick(d.key,Qt.Key.Key_F8,Qt.KeyboardModifier.MetaModifier|Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(d.mods.text(),'SUPER CTRL');self.assertEqual(d.key.text(),'F8');self.assertEqual(state[0],'reset')
            d.begin_capture();d.reject();self.assertEqual(state[0],'reset')
            state[0]='another-mode';d.begin_capture();self.assertFalse(d.key.recording);self.assertEqual(state[0],'another-mode')

    def test_favorite_badges_update_after_atomic_and_in_place_control_desk_edits(self):
        self.add_binding()
        with (patch.object(hotkeys.keys,'Store',return_value=self.store),
              patch.object(catalog,'applications',return_value={self.entry.get_id():self.entry}),
              patch.object(catalog,'favorites',return_value=[self.entry.get_id()])):
            menu=app.Menu(preview=True)
        self.windows.append(menu);menu.show();QTest.qWait(20)
        item=menu.grid.item(0);self.assertEqual(item.data(hotkeys.ROLE),['Super+F8'])
        self.assertIn('hotkey',[action.data() for action in menu.build_context_menu(self.entry.get_id()).actions()])
        records,_=self.store.load();records[-1].key='F9'
        hotkeys.keys.atomic_write(self.store.path,hotkeys.keys.serialize(records).encode());QTest.qWait(260)
        self.assertEqual(item.data(hotkeys.ROLE),['Super+F9'])
        records[-1].enabled=False;self.store.path.write_text(hotkeys.keys.serialize(records));QTest.qWait(260)
        self.assertEqual(item.data(hotkeys.ROLE),[])


if __name__=='__main__':unittest.main(verbosity=2)
