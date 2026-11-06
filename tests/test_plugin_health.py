import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fusion_plugin_health', ROOT/'config/hypr/runtime/plugin_health.py')
health = importlib.util.module_from_spec(spec); sys.modules[spec.name] = health; spec.loader.exec_module(health)


class HealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.instance = self.root/'session'; self.instance.mkdir()
        self.plugins = [dict(name=p.name, version='1') for p in health.PLUGINS]
        self.states = {p.command:dict(enabled=True) for p in health.PLUGINS if p.command}
        for p in health.PLUGINS:
            if p.settings:
                path = self.root/p.settings; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"enabled":true}' if path.suffix == '.json' else 'enabled=1\n')

    def query(self, *args):
        if args == ('-j', 'version'): return dict(tag='v0.56.2')
        if args == ('-j', 'plugin', 'list'): return self.plugins
        value = self.states[args[0]]
        if isinstance(value, Exception): raise value
        return value

    def inspect(self): return health.inspect(self.root, self.instance, self.query)

    def test_checks_all_eight_plugins_and_their_status_endpoints(self):
        result = self.inspect(); self.assertTrue(result['ok']); self.assertEqual(len(result['plugins']), 8)
        self.states['xetal-minimize'] = RuntimeError('unknown request')
        result = self.inspect(); self.assertFalse(result['ok'])
        failed = [p for p in result['plugins'] if not p['ok']]
        self.assertEqual(len(failed), 1); self.assertIn('unknown request', failed[0]['detail'])

    def test_missing_plugin_reports_login_error_and_manual_recovery_is_green(self):
        self.plugins = [p for p in self.plugins if p['name'] != 'Xetal Minimize']
        (self.instance/'plugin-startup-minimize.json').write_text(json.dumps(dict(state='failed', error='IPC timeout at login')))
        row = next(p for p in self.inspect()['plugins'] if p['key'] == 'minimize')
        self.assertFalse(row['ok']); self.assertIn('IPC timeout', row['detail'])
        self.plugins.append(dict(name='Xetal Minimize'))
        row = next(p for p in self.inspect()['plugins'] if p['key'] == 'minimize')
        self.assertTrue(row['ok']); self.assertIn('Recovered', row['detail'])

    def test_disabled_effect_is_clear_but_missing_required_handler_is_an_error(self):
        for name in ('burn', 'minimize'):
            (self.root/f'effects/{name}/settings.conf').write_text('enabled=0\n')
        self.plugins = [p for p in self.plugins if p['name'] not in ('Xetal Burn', 'Xetal Minimize')]
        rows = {p['key']:p for p in self.inspect()['plugins']}
        self.assertTrue(rows['burn']['ok']); self.assertEqual(rows['burn']['message'], 'Disabled in settings')
        self.assertFalse(rows['minimize']['ok'])  # Native ordering still needs the handler.

    def test_saved_on_but_active_off_is_not_reported_healthy(self):
        self.states['xetal-minimize'] = dict(enabled=False)
        self.assertFalse(self.inspect()['ok'])
        self.states['xetal-minimize'] = dict(error='renderer unavailable')
        self.assertFalse(self.inspect()['ok'])

    def test_icon_helper_failure_is_distinguished_from_native_minimize_failure(self):
        (self.instance/'plugin-startup-minimize-icons.json').write_text(json.dumps(
            dict(state='failed', error='Dock icon helper exited with status 7')))
        row = next(p for p in self.inspect()['plugins'] if p['key'] == 'minimize')
        self.assertTrue(row['loaded']); self.assertFalse(row['ok'])
        self.assertIn('icon helper failed', row['message']); self.assertIn('status 7', row['detail'])

    def test_falls_back_to_old_session_log_and_displays_colored_marks(self):
        self.plugins = [p for p in self.plugins if p['name'] != 'Xetal Minimize']
        (self.instance/'minimize.log').write_text('Minimize: Cannot load adapter\n')
        report = self.inspect(); output = io.StringIO(); health.display(report, True, output)
        self.assertIn('\033[32m[✓]', output.getvalue()); self.assertIn('\033[31m[✗]', output.getvalue())
        self.assertIn('Cannot load adapter', output.getvalue())
        self.assertEqual(health.safe_text('\x1b[31munsafe\x07'), ' [31munsafe ')

    def test_session_detection_never_guesses_another_login(self):
        for env in ({}, {'XDG_RUNTIME_DIR':'/tmp','HYPRLAND_INSTANCE_SIGNATURE':'../other'}):
            with self.assertRaises(RuntimeError): health.instance_path(env)


if __name__ == '__main__': unittest.main()
