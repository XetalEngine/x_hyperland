"""Exercise real desktop associations in disposable homes, never the live account."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('defaults', HERE/'default_apps.py')
defaults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(defaults)


class DefaultAppsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-default-apps-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.profile = self.base/'profile'
        self.config = self.base/'config'
        self.data = self.base/'data'
        for path in (self.config, self.data/'applications', self.profile/'desktop/config'):
            path.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.base), XDG_CONFIG_HOME=str(self.config),
                        XDG_DATA_HOME=str(self.data), XDG_CONFIG_DIRS=str(self.profile/'desktop/config'),
                        XDG_DATA_DIRS='/usr/local/share:/usr/share', XDG_CURRENT_DESKTOP='Hyprland',
                        XDG_CACHE_HOME=str(self.base/'cache'), XDG_STATE_HOME=str(self.base/'state'))
        self.old = '# Keep my preferences\n[Default Applications]\napplication/pdf=fixture-old.desktop;\nimage/png=fixture-old.desktop;\n\n[Added Associations]\napplication/pdf=fixture-old.desktop;\n\n[Removed Associations]\napplication/pdf=fixture-new.desktop;unrelated.desktop;\n\n[Unrelated]\nliteral=100% # keep this\n'
        (self.config/'mimeapps.list').write_text(self.old)
        (self.profile/'desktop/config/mimeapps.list').write_text('[Default Applications]\napplication/pdf=fixture-old.desktop;\n')
        for name, label in (('old', 'Fixture Old'), ('new', 'Fixture New')):
            (self.data/'applications'/('fixture-'+name+'.desktop')).write_text(
                '[Desktop Entry]\nType=Application\nName='+label+'\nExec=/bin/true %U\n'
                'MimeType=application/pdf;image/png;audio/mpeg;x-scheme-handler/http;x-scheme-handler/https;text/html;application/xhtml+xml;inode/directory;\n')
        self.runner = ('import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
                       'import default_apps as d; d.ROOT=Path(sys.argv[2]); '
                       'sys.argv=[sys.argv[0],*sys.argv[3:]]; raise SystemExit(d.main())')

    def call(self, action='snapshot', data=None, okay=True):
        result = subprocess.run([sys.executable, '-c', self.runner, str(HERE), str(self.profile), action],
                                env=self.env, input=json.dumps(data or {}), text=True, capture_output=True, timeout=15)
        output = json.loads(result.stdout)
        if okay:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('error', output)
        return output

    def apply(self, **values):
        return self.call('apply', dict(revision=self.call()['revision'], app='fixture-new.desktop', **values))

    def test_inventory_does_not_write_and_includes_extensions_and_protocols(self):
        before = {p: p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        snapshot = self.call()
        self.assertEqual(len(snapshot['roles']), 12)
        self.assertIn('fixture-new.desktop', [a['id'] for a in snapshot['apps']])
        types = {t['id']: t for t in snapshot['filetypes']}
        self.assertIn('*.pdf', types['application/pdf']['extensions'])
        self.assertEqual(types['application/pdf']['default'], 'fixture-old.desktop')
        self.assertIn('x-scheme-handler/https', types)
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob('*') if p.is_file()})

    def test_apply_preserves_unrelated_entries_and_undo_restores_exact_files(self):
        result = self.apply(type='application/pdf')
        changed = (self.config/'mimeapps.list').read_text()
        self.assertIn('# Keep my preferences', changed)
        self.assertIn('image/png=fixture-old.desktop;', changed)
        self.assertIn('[Unrelated]\nliteral=100% # keep this', changed)
        self.assertEqual(defaults.entries(changed, 'Added Associations')['application/pdf'], 'fixture-new.desktop;fixture-old.desktop;')
        self.assertEqual(defaults.entries(changed, 'Removed Associations')['application/pdf'], 'unrelated.desktop;')
        self.assertEqual(next(t for t in self.call()['filetypes'] if t['id'] == 'application/pdf')['default'], 'fixture-new.desktop')
        query = subprocess.check_output(['xdg-mime', 'query', 'default', 'application/pdf'], env=self.env, text=True).strip()
        self.assertEqual(query, 'fixture-new.desktop')
        self.assertIn('application/pdf=fixture-new.desktop;', (self.profile/'desktop/config/mimeapps.list').read_text())
        self.call('undo', {'token': result['undo']})
        self.assertEqual((self.config/'mimeapps.list').read_text(), self.old)

    def test_browser_sets_web_links_and_pages_together(self):
        self.apply(role='browser')
        current = {t['id']: t['default'] for t in self.call()['filetypes']}
        for mime in ('x-scheme-handler/http', 'x-scheme-handler/https', 'text/html', 'application/xhtml+xml'):
            self.assertEqual(current[mime], 'fixture-new.desktop')
        self.assertEqual(current['application/pdf'], 'fixture-old.desktop')

    def test_audio_covers_registered_formats_without_changing_video(self):
        self.apply(role='music')
        content = defaults.entries((self.config/'mimeapps.list').read_text(), 'Default Applications')
        for mime in ('audio/mpeg', 'audio/flac', 'audio/ogg'):
            self.assertEqual(content[mime], 'fixture-new.desktop;')
        self.assertNotIn('video/mp4', content)

    def test_existing_desktop_and_isolated_overrides_follow_the_choice(self):
        specific = self.config/'hyprland-mimeapps.list'
        specific.write_text('[Default Applications]\napplication/pdf=fixture-old.desktop;\nimage/png=fixture-old.desktop;\n')
        isolated = self.profile/'dolphin/config/mimeapps.list'
        isolated.parent.mkdir(parents=True)
        isolated.write_text('[Default Applications]\napplication/pdf=fixture-old.desktop;\n')
        self.apply(type='application/pdf')
        self.assertEqual(next(t for t in self.call()['filetypes'] if t['id'] == 'application/pdf')['default'], 'fixture-new.desktop')
        self.assertIn('application/pdf=fixture-new.desktop;', specific.read_text())
        self.assertNotIn('Added Associations', specific.read_text())
        self.assertIn('application/pdf=fixture-new.desktop;', isolated.read_text())

    def test_invalid_apps_and_types_cannot_change_preferences(self):
        for data in ({'app': '../bad.desktop', 'type': 'application/pdf'},
                     {'app': 'absent.desktop', 'type': 'application/pdf'},
                     {'app': 'fixture-new.desktop', 'type': 'application/pdf\ninode/directory'},
                     {'app': 'fixture-new.desktop', 'role': 'unknown'}):
            self.call('apply', dict(revision=self.call()['revision'], **data), okay=False)
        self.assertEqual((self.config/'mimeapps.list').read_text(), self.old)

    def test_stale_saves_and_undo_preserve_newer_changes(self):
        snapshot = self.call()
        path = self.config/'mimeapps.list'
        path.write_text(self.old+'# another app changed this\n')
        result = self.call('apply', dict(revision=snapshot['revision'], app='fixture-new.desktop', type='application/pdf'), okay=False)
        self.assertIn('changed elsewhere', result['error'])
        applied = self.apply(type='application/pdf')
        path.write_text(path.read_text()+'# newer settings\n')
        newer = path.read_text()
        self.call('undo', {'token': applied['undo']}, okay=False)
        self.assertEqual(path.read_text(), newer)

    def test_failure_rolls_back_files_already_written(self):
        original_write = defaults.atomic_write
        failed = False
        def fail_profile(path, content, mode=0o600):
            nonlocal failed
            if path == self.profile/'desktop/config/mimeapps.list' and not failed:
                failed = True
                raise OSError('Fixture could not write profile')
            return original_write(path, content, mode)
        class App:
            def get_supported_types(self): return ['application/pdf']
            def get_display_name(self): return 'Fixture New'
        with patch.dict(os.environ, self.env, clear=True), patch.object(defaults, 'ROOT', self.profile), \
             patch.object(defaults, 'installed', return_value={'fixture-new.desktop': App()}), \
             patch.object(defaults, 'atomic_write', side_effect=fail_profile):
            with self.assertRaises(OSError):
                defaults.apply_choice({'app':'fixture-new.desktop', 'type':'application/pdf', 'revision':defaults.revision()})
        self.assertEqual((self.config/'mimeapps.list').read_text(), self.old)

    def test_failed_undo_leaves_the_applied_defaults_and_retry_available(self):
        applied = self.apply(type='application/pdf')
        paths = [self.config/'mimeapps.list', self.profile/'desktop/config/mimeapps.list']
        before = {p: p.read_bytes() for p in paths}
        original_write = defaults.atomic_write
        failed = False
        def fail_once(path, content, mode=0o600):
            nonlocal failed
            if path == paths[1] and not failed:
                failed = True
                raise OSError('Fixture restore failed')
            return original_write(path, content, mode)
        with patch.dict(os.environ, self.env, clear=True), patch.object(defaults, 'ROOT', self.profile), \
             patch.object(defaults, 'atomic_write', side_effect=fail_once):
            with self.assertRaises(OSError): defaults.undo({'token':applied['undo']})
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.call('undo', {'token':applied['undo']})
        self.assertEqual(paths[0].read_text(), self.old)

    def test_association_editor_handles_missing_sections_and_duplicate_entries(self):
        text = '# comment\n[Default Applications]\napplication/pdf=old.desktop;\napplication/pdf=other.desktop;\n'
        result = defaults.updated(text, ['application/pdf'], 'new.desktop')
        self.assertEqual(result.count('application/pdf=new.desktop;'), 2)
        self.assertNotIn('old.desktop', result)
        self.assertIn('# comment', result)
        self.assertNotIn('Removed Associations', result)

    def test_old_notification_environment_uses_profile_file_manager_and_selection(self):
        applications = self.profile/'desktop/data/applications'
        applications.mkdir(parents=True)
        (applications/'xetal-files.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Fusion Files\nExec=/bin/true %U\nMimeType=inode/directory;\n')
        with (self.profile/'desktop/config/mimeapps.list').open('a') as stream:
            stream.write('inode/directory=xetal-files.desktop;\n')
        scripts = self.profile/'scripts'
        scripts.mkdir()
        handler = scripts/'files.sh'
        handler.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps({"arguments":sys.argv[1:]}))\n')
        handler.chmod(0o700)
        self.env['XDG_CONFIG_DIRS'] = '/etc/xdg'
        literal = str(self.base/'screen # 100% $(literal).png')
        result = subprocess.run([sys.executable, '-c', self.runner, str(HERE), str(self.profile),
                                 'open-folder', '--select', literal],
                                env=self.env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'arguments':['--select', literal]})

    def test_folder_launcher_uses_selected_app_and_keeps_literal_paths(self):
        class App:
            def get_id(self): return 'fixture-new.desktop'
            def launch(self, files, context):
                self.paths = [f.get_path() for f in files]
                return True
        app = App()
        literal = str(self.base/"a ; $(not-a-command) # 100% folder"/'file.txt')
        with patch.object(defaults.Gio.AppInfo, 'get_default_for_type', return_value=app):
            self.assertEqual(defaults.open_folder(['--select', literal]), 0)
            self.assertEqual(app.paths, [str(Path(literal).parent)])
        with patch.object(defaults.Gio.AppInfo, 'get_default_for_type', return_value=None), patch.object(defaults.os, 'execv') as execute:
            # execv never returns in production.
            execute.side_effect = SystemExit
            with self.assertRaises(SystemExit): defaults.open_folder([])
            self.assertTrue(execute.call_args.args[0].endswith('/scripts/files.sh'))


if __name__ == '__main__':
    unittest.main()
