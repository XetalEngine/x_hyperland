"""Design changes retain the editor engine and dispose animated artwork safely."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
import app
import keys
import runtime

QT=QApplication.instance() or QApplication([])


class DesignTests(unittest.TestCase):
    def test_switch_preserves_hotkey_draft_and_original_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'theme.json'
            state.write_text(json.dumps({'design':'raw','mode':'dark'}))
            (root/'keybindings.conf').write_text('bind = SUPER, Q, exec, kitty\n')
            (root/'hyprland.conf').write_text('$mainMod = SUPER\n'+keys.SOURCE+'\n')
            store=keys.Store(root,root/'history')
            original=(root/'keybindings.conf').read_bytes()
            with patch.object(runtime,'STATE',state),patch.object(keys,'Store',return_value=store),patch.object(app,'async_run'):
                window=app.Window(visible=False)
                try:
                    editor=window.pages['hotkeys']
                    editor.fields['label'].setText('A pending edit')
                    editor.edit(refresh=False)
                    self.assertTrue(editor.dirty)
                    draft=keys.serialize(editor.records)
                    for design in ('modern','raw','modern'):
                        state.write_text(json.dumps({'design':design,'mode':'dark'}))
                        window.apply_design()
                        self.assertIs(window.pages['hotkeys'],editor)
                        self.assertTrue(editor.dirty)
                        self.assertEqual(keys.serialize(editor.records),draft)
                        self.assertEqual(window.modern_rail.isHidden(),design=='raw')
                        self.assertEqual(window.tabs.indexOf(window.home)>=0,design=='modern')
                    self.assertEqual((root/'keybindings.conf').read_bytes(),original)
                finally:
                    window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_animated_profile_and_control_desk_exit_cleanly_in_both_designs(self):
        script='''
import json,sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import app, runtime
runtime.STATE=Path(sys.argv[1])
application=QApplication([])
runtime.install(application,app.STYLE)
app.async_run=lambda *args:None
window=app.Window('home' if runtime.design()=='modern' else 'hotkeys')
QTimer.singleShot(70,window.hide)
QTimer.singleShot(100,window.show)
QTimer.singleShot(200,application.quit)
sys.exit(application.exec())
'''
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json'
            for design in ('raw','modern'):
                state.write_text(json.dumps({'design':design,'mode':'dark','avatar':'assets/account.gif'}))
                result=subprocess.run([sys.executable,'-c',script,str(state)],cwd=Path(app.__file__).parent,
                    env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QPA_PLATFORMTHEME':'','GSETTINGS_BACKEND':'memory'},
                    capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,(design,result.stderr))


if __name__=='__main__':unittest.main()
