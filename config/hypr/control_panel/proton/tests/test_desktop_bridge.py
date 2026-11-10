#!/usr/bin/env python3
"""Real filesystem/argv checks; no installed application or personal settings."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'desktop_bridge.py'
spec = importlib.util.spec_from_file_location('desktop_bridge', SOURCE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class DesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='proton-handlers-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, self.storage, self.config = (self.base / name for name in ('hypr', 'handlers', 'config'))
        self.config.mkdir()
        self.mime = self.config / 'hyprland-mimeapps.list'
        self.generic = self.config / 'mimeapps.list'
        self.kde = self.config / 'kde-mimeapps.list'
        self.generic.write_text('[Default Applications]\nx-scheme-handler/example=shared.desktop;\n')
        self.kde.write_text('[Default Applications]\nx-scheme-handler/example=kde.desktop;\n')
        self.mime.write_text('# keep this comment\n[Default Applications]\nx-scheme-handler/example=older.desktop;\ninode/directory=files.desktop;\n')
        self.runner = self.base / 'runner.py'
        self.event = self.base / 'event.json'
        self.runner.write_text('import os,sys,json\nfrom pathlib import Path\n'
            'Path(os.environ["EVENT"]).write_text(json.dumps({"args":sys.argv[1:],"prefix":os.environ["WINEPREFIX"],"cwd":os.getcwd()}))\n'
            'print("PRIVATE SIGN-IN OUTPUT", *sys.argv[1:])\n')
        self.app = dict(id='app_one', name='An app', schemes=['example'], argument='{url}',
            make_default=True, private_output=True, argv=[sys.executable, str(self.runner), '--normal', 'a b'],
            callback_argv=[sys.executable, str(self.runner), '--normal', 'a b'],
            env={'WINEPREFIX': str(self.base / 'prefix/pfx'), 'EVENT': str(self.event)},
            cwd=str(self.base), prefix=str(self.base / 'prefix'))

    def request(self, apps):
        return dict(root=str(self.root), storage=str(self.storage), config_home=str(self.config), apps=apps)

    def sync(self, apps=None):
        bridge.sync(self.request([self.app] if apps is None else apps))

    def run_bridge(self, action, *args):
        env = dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='fixture', XDG_CONFIG_HOME=str(self.config), PATH='/nonexistent')
        return subprocess.run([sys.executable, str(SOURCE), action, str(self.storage / 'app_one.json'), *args],
                              capture_output=True, text=True, env=env, timeout=15)

    def test_registration_is_hyprland_only_and_reversible(self):
        original, shared, kde = self.mime.read_bytes(), self.generic.read_bytes(), self.kde.read_bytes()
        self.sync()
        self.assertEqual(bridge.defaults(self.mime.read_text())['x-scheme-handler/example'], 'xetal-proton-app_one.desktop;')
        self.assertIn('# keep this comment', self.mime.read_text())
        entry = self.root / 'desktop/data/applications/xetal-proton-app_one.desktop'
        self.assertIn('NoDisplay=true\n', entry.read_text())
        self.assertEqual((self.storage / 'app_one.json').stat().st_mode & 0o777, 0o600)
        if shutil.which('desktop-file-validate'):
            subprocess.run(['desktop-file-validate', str(entry)], check=True, capture_output=True)
        self.sync([])
        self.assertEqual(self.mime.read_bytes(), original)
        self.assertEqual(self.generic.read_bytes(), shared)
        self.assertEqual(self.kde.read_bytes(), kde)
        self.assertFalse(entry.exists())
        self.assertFalse((self.storage / 'app_one.json').exists())

    def test_removal_keeps_an_external_default_change(self):
        self.sync()
        changed = self.mime.read_text().replace('xetal-proton-app_one.desktop;', 'user-choice.desktop;')
        self.mime.write_text(changed)
        self.sync([])
        self.assertEqual(self.mime.read_text(), changed)

    def test_nondefault_registration_and_duplicate_owner_conflicts(self):
        original = self.mime.read_bytes()
        self.app['make_default'] = False
        self.sync()
        self.assertEqual(self.mime.read_bytes(), original)
        second = dict(self.app, id='two', make_default=True)
        self.app['make_default'] = True
        with self.assertRaisesRegex(ValueError, 'Only one'):
            self.sync([self.app, second])
        self.assertEqual(self.mime.read_bytes(), original)

    def test_callback_keeps_the_link_one_argument_and_never_logs_it(self):
        self.sync()
        token = "example://auth/callback?token=a%26b&quote='\";$(touch /tmp/never-run)&space=a b"
        result = self.run_bridge('--callback', token)
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(self.event.read_text())
        self.assertEqual(event['args'], ['--normal', 'a b', token])
        self.assertEqual(event['prefix'], self.app['env']['WINEPREFIX'])
        self.assertEqual(event['cwd'], self.app['cwd'])
        self.assertEqual(result.stdout + result.stderr, '')
        self.assertNotIn(token, (self.storage / 'app_one.json').read_text())

    def test_callback_uses_the_last_launched_prefix_after_edits(self):
        self.sync()
        result = self.run_bridge('--launch')
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.app['env']['WINEPREFIX']
        self.app['env']['WINEPREFIX'] = str(self.base / 'second/pfx')
        self.app['prefix'] = str(self.base / 'second')
        self.sync()
        result = self.run_bridge('--callback', 'example://auth/callback?token=fixture')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.event.read_text())['prefix'], original)
        self.sync([])
        self.assertFalse((self.storage / 'app_one.active.json').exists())

    def test_disabled_scheme_cannot_use_a_previous_active_snapshot(self):
        self.sync()
        self.assertEqual(self.run_bridge('--launch').returncode, 0)
        self.app['schemes'] = ['replacement']
        self.sync()
        result = self.run_bridge('--callback', 'example://auth/callback?token=secret')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('secret', result.stdout + result.stderr)

    def test_argument_template_and_skipping_normal_arguments(self):
        self.app['argument'] = '--open-url={url}'
        self.app['callback_argv'] = [sys.executable, str(self.runner)]
        self.sync()
        result = self.run_bridge('--callback', 'example://callback?x=one&y=two')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.event.read_text())['args'], ['--open-url=example://callback?x=one&y=two'])

    def test_prefix_dependency_lock_prevents_callback_launch(self):
        self.sync()
        prefix = Path(self.app['prefix'])
        prefix.mkdir()
        with (prefix / '.xetalproton.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_bridge('--callback', 'example://callback?token=secret')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('busy installing dependencies', result.stderr)
        self.assertNotIn('secret', result.stderr)
        self.assertFalse(self.event.exists())

    def test_invalid_schemes_urls_and_templates_are_rejected(self):
        for value in ('https', 'file', 'example-app://', 'one\nExec=bad', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.schemes(value)
        self.assertEqual(bridge.schemes('Example-App, example;example'), ['example-app', 'example'])
        for value in ('https://example.com', 'example://ok\n--flag'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.callback_command(self.app, value)
        for value in ('', '{url} {url}', '{url}\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.validate(dict(self.app, argument=value))

    def test_failed_install_rolls_back_existing_files(self):
        self.sync()
        paths = [self.mime, self.storage / 'app_one.json', self.storage / 'registry.json']
        original = {p: p.read_bytes() for p in paths}
        self.app['name'] = 'Changed name'
        self.app['schemes'] = ['new-scheme']
        write = bridge.atomic_write
        failed = False

        def fail_once(path, *args):
            nonlocal failed
            if path == self.storage / 'registry.json' and not failed:
                failed = True
                raise OSError('fixture write failure')
            return write(path, *args)

        with patch.object(bridge, 'atomic_write', side_effect=fail_once), self.assertRaises(OSError):
            self.sync()
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)

    def test_managed_launch_repairs_the_default_without_a_panel_process(self):
        self.sync()
        self.mime.write_text(self.mime.read_text().replace('xetal-proton-app_one.desktop;', 'other.desktop;'))
        result = self.run_bridge('--launch')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(bridge.defaults(self.mime.read_text())['x-scheme-handler/example'], 'xetal-proton-app_one.desktop;')
        self.sync([])
        self.assertEqual(bridge.defaults(self.mime.read_text())['x-scheme-handler/example'], 'other.desktop;')

    def test_exported_launcher_accepts_extra_application_flags(self):
        self.sync()
        result = self.run_bridge('--launch', '--', '--extra-flag', 'with spaces')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.event.read_text())['args'], ['--normal', 'a b', '--extra-flag', 'with spaces'])

    def test_desktop_arguments_survive_reserved_path_characters(self):
        self.storage = self.base / 'space $ cash `tick` "quote" %percent'
        self.sync()
        entry = self.root / 'desktop/data/applications/xetal-proton-app_one.desktop'
        if shutil.which('desktop-file-validate'):
            result = subprocess.run(['desktop-file-validate', str(entry)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('%%percent', entry.read_text())
        if Path('/usr/bin/python3').exists():
            url='example://callback?value=a%26b&other=with space'
            probe=subprocess.run(['/usr/bin/python3','-c','from gi.repository import Gio'],capture_output=True)
            if probe.returncode==0:
                env=dict(os.environ,HYPRLAND_INSTANCE_SIGNATURE='fixture',XDG_CONFIG_HOME=str(self.config))
                result=subprocess.run(['/usr/bin/python3','-c',
                    'import sys;from gi.repository import Gio;'
                    'app=Gio.DesktopAppInfo.new_from_filename(sys.argv[1]);'
                    'assert app is not None;assert app.launch_uris([sys.argv[2]],None)',str(entry),url],
                    env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                deadline=time.monotonic()+3
                while not self.event.exists() and time.monotonic()<deadline:
                    time.sleep(.03)
                self.assertTrue(self.event.exists(),'Desktop launcher did not reach the selected app')
                self.assertEqual(json.loads(self.event.read_text())['args'][-1],url)


if __name__ == '__main__':
    unittest.main()
