"""Actual editor/session integration using disposable files and compositor sockets."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import shutil

ROOT = Path(__file__).resolve().parent


class DesktopIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='panel-integration-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        instance = self.root/'hypr/fixture'
        instance.mkdir(parents=True)
        self.server = socket.socket(socket.AF_UNIX)
        self.addCleanup(self.server.close)
        self.server.bind(str(instance/'.socket2.sock'))
        self.server.listen(1)
        self.server.settimeout(5)
        self.env = dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='fixture',
                        XDG_RUNTIME_DIR=str(self.root), QT_QPA_PLATFORM='offscreen')

    def child(self, code):
        process = subprocess.Popen([sys.executable, '-c', code, str(self.root)], cwd=ROOT,
                                   env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        connection, _ = self.server.accept()
        self.addCleanup(connection.close)
        return process, connection

    def test_shortcut_editor_saves_into_apps_with_floating_and_literal_command(self):
        code = r'''
import json,sys
from pathlib import Path
import bridge
root=Path(sys.argv[1]);sys.path.insert(0,str(bridge.ROOT/'launcher'))
import shortcuts,catalog,editor
from PyQt6.QtCore import QTimer
shortcuts.STATE=root/'shortcuts.json';catalog.LOCAL=root/'favorites.json'
original=editor.ShortcutEditor
class SaveEditor(original):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.inputs['name'].setText('Panel test favorite')
        self.inputs['directory'].setText(str(root))
        self.inputs['icon'].setText('')
        self.floating.setChecked(True);self.keep_open.setChecked(False)
        QTimer.singleShot(0,self.accept)
editor.ShortcutEditor=SaveEditor
result=bridge.shortcut({'name':'example','shell':'bash','command':"printf '%s\\n' '100%'"})
print(json.dumps(result))
'''
        process, connection = self.child(code)
        stdout, stderr = process.communicate(timeout=12)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertTrue(json.loads(stdout)['saved'])
        shortcuts = json.loads((self.root/'shortcuts.json').read_text())['copies']
        self.assertEqual(len(shortcuts), 1)
        ident, item = next(iter(shortcuts.items()))
        fields = item['fields']
        self.assertTrue(fields['floating']);self.assertTrue(fields['terminal'])
        self.assertFalse(fields['keep_open'])
        self.assertEqual(fields['directory'], str(self.root))
        self.assertIn('100%%', fields['command'])
        self.assertEqual(json.loads((self.root/'favorites.json').read_text())['add'], [ident])

    def test_startup_helper_and_owned_application_end_with_compositor(self):
        directory = self.root/'control_panel/state/autostart'
        directory.mkdir(parents=True)
        (directory/'fixture.desktop').write_text('fixture')
        code = r'''
import subprocess,sys
from pathlib import Path
import startup
startup.ROOT=Path(sys.argv[1])
def launch(path):
    code="import signal,sys,time;from pathlib import Path;signal.signal(signal.SIGTERM,lambda *_:(Path(sys.argv[1]).write_text('stopped'),sys.exit(0)));Path(sys.argv[2]).write_text('ready');time.sleep(30)"
    return subprocess.Popen([sys.executable,'-c',code,str(startup.ROOT/'stopped'),str(startup.ROOT/'ready')],start_new_session=True)
startup.launch=launch
raise SystemExit(startup.session())
'''
        process, connection = self.child(code)
        deadline = time.monotonic()+5
        while not (self.root/'ready').exists() and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue((self.root/'ready').exists())
        connection.close()
        stdout, stderr = process.communicate(timeout=4)
        self.assertEqual(process.returncode, 0, stderr)
        deadline = time.monotonic()+2
        while not (self.root/'stopped').exists() and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue((self.root/'stopped').exists(), 'The owned startup application survived logout')

    @unittest.skipUnless((ROOT/'.build/xetal-control-panel').is_file(), 'Build the native panel to test instance reuse')
    def test_native_panel_reuses_its_instance_and_keeps_settings_private(self):
        profile=self.root/'profile';panel=profile/'control_panel';panel.mkdir(parents=True)
        for name in ('tools.json','bridge.py','aliases.py'):
            shutil.copy2(ROOT/name,panel/name)
        (profile/'theme').symlink_to(ROOT.parent/'theme',target_is_directory=True)
        self.env['XETAL_HYPR_ROOT']=str(profile)
        code='import os;os.execv('+repr(str(ROOT/'.build/xetal-control-panel'))+','+repr([str(ROOT/'.build/xetal-control-panel')])+')'
        process,connection=self.child(code)
        endpoint=self.root/'hypr/fixture/.xpanel.sock'
        deadline=time.monotonic()+5
        while not endpoint.exists() and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue(endpoint.exists())
        second=subprocess.run([str(ROOT/'.build/xetal-control-panel'),'--section','iso'],env=self.env,
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertIsNone(process.poll(),'The original panel exited instead of receiving the request')
        connection.close();stdout,stderr=process.communicate(timeout=5)
        self.assertEqual(process.returncode,0,stderr)
        self.assertTrue((panel/'state/XetalHyperland/ControlPanel.conf').is_file())


if __name__ == '__main__':
    unittest.main()
