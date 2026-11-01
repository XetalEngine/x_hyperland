import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fusion-applications-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ)
        for key, directory in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')]:
            path = self.root/directory; path.mkdir(); self.env[key] = str(path)
        self.env['XDG_DATA_DIRS'] = '/usr/local/share:/usr/share'
        self.env['XDG_CONFIG_DIRS'] = str(self.root/'config')
        self.env['XDG_CURRENT_DESKTOP'] = 'Hyprland'
        (self.root/'profile/desktop/config').mkdir(parents=True)
        self.apps = self.root/'data/applications'; self.apps.mkdir()
        self.log = self.root/'opened.json'
        self.program = self.root/'editor.py'
        self.program.write_text('import json,sys\nfrom pathlib import Path\nPath('+repr(str(self.log))+').write_text(json.dumps(sys.argv[1:]))\n')
        (self.apps/'fusion-fixture-editor.desktop').write_text('[Desktop Entry]\nType=Application\nName=Fusion Fixture Editor\nExec=/usr/bin/python3 '+str(self.program)+' %F\nIcon=text-editor\nMimeType=text/plain;application/octet-stream;\n')
        (self.apps/'fusion-fixture-other.desktop').write_text('[Desktop Entry]\nType=Application\nName=Fusion Fixture Other\nExec=/usr/bin/true %F\nIcon=application-x-executable\n')

    def call(self, action, data):
        script = 'import sys,json\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nimport applications as a\na.default_apps.ROOT=Path(sys.argv[2])\ntry:\n print(json.dumps(getattr(a,sys.argv[3])(json.load(sys.stdin))))\nexcept Exception as e:\n print(json.dumps({"error":str(e)}));sys.exit(1)\n'
        result = subprocess.run(['python3', '-c', script, str(ROOT), str(self.root/'profile'), action],
                                input=json.dumps(data), text=True, capture_output=True, env=self.env, timeout=20)
        return result.returncode, json.loads(result.stdout)

    def test_unknown_type_lists_all_installed_apps_without_menu_definition(self):
        code, result = self.call('choices', {'mimes':['application/octet-stream']})
        self.assertEqual(code, 0, result)
        ids = {app['id'] for app in result['apps']}
        self.assertTrue({'fusion-fixture-editor.desktop', 'fusion-fixture-other.desktop'} <= ids)
        self.assertFalse((self.root/'config/mimeapps.list').exists())

    def test_launch_preserves_literal_names_and_save_default_uses_shared_backend(self):
        file = self.root/'literal # % ; file.txt'; file.write_text('fixture')
        _, choices = self.call('choices', {'mimes':['text/plain']})
        code, result = self.call('launch', dict(app='fusion-fixture-editor.desktop', mime='text/plain',
                                              urls=[file.as_uri()], remember=True, revision=choices['revision']))
        self.assertEqual(code, 0, result)
        for _ in range(100):
            if self.log.exists():break
            time.sleep(.02)
        self.assertEqual(json.loads(self.log.read_text()), [str(file)])
        self.assertIn('text/plain=fusion-fixture-editor.desktop;', (self.root/'config/mimeapps.list').read_text())
        self.assertTrue((self.root/'profile/control_panel/state/default-apps/last-change.json').exists())
        # Explicit launch without Remember does not rewrite defaults.
        previous = (self.root/'config/mimeapps.list').read_bytes()
        code, result = self.call('launch', dict(app='fusion-fixture-other.desktop', mime='text/plain', urls=[file.as_uri()]))
        self.assertEqual(code, 0, result)
        self.assertEqual(previous, (self.root/'config/mimeapps.list').read_bytes())

    def test_custom_program_can_be_saved_without_shell_expansion(self):
        file = self.root/'unknown.data'; file.write_text('fixture')
        _, choices = self.call('choices', {'mimes':['application/octet-stream']})
        code, result = self.call('launch', dict(command='/usr/bin/python3 '+str(self.program), mime='application/octet-stream',
                                              urls=[file.as_uri()], remember=True, revision=choices['revision']))
        self.assertEqual(code, 0, result)
        self.assertEqual(len(list(self.apps.glob('xetal-openwith-*.desktop'))), 1)
        self.assertIn('application/octet-stream=xetal-openwith-', (self.root/'config/mimeapps.list').read_text())

    def test_stale_default_save_and_missing_application_report_errors(self):
        code, result = self.call('launch', dict(app='fusion-fixture-editor.desktop', mime='text/plain',
                                              urls=[(self.root/'unused').as_uri()], remember=True, revision='stale'))
        self.assertEqual(code, 1)
        self.assertIn('changed elsewhere', result['error'])
        self.assertFalse((self.root/'config/mimeapps.list').exists())
        code, result = self.call('launch', dict(app='missing-fixture.desktop', mime='text/plain', urls=['file:///unused']))
        self.assertEqual(code, 1)
        self.assertIn('No application', result['error'])


if __name__ == '__main__':unittest.main()
