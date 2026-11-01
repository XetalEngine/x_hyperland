import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import aliases
import startup


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.environment = {'SHELL': '/bin/bash', 'HOME': str(self.home)}
        self.config = self.home/'.bashrc'
        self.state = self.home/'panel/state'

    def load(self):
        return aliases.load(self.home, self.environment)

    def save(self, snapshot):
        return aliases.save(snapshot, self.state, self.home, self.environment)

    def test_edit_preserves_functions_comments_and_unrelated_shell_settings(self):
        unchanged = '# personal settings\nexport PATH="$HOME/bin:$PATH"\nfunction jump() { cd /tmp; }\n'
        self.config.write_text(unchanged + "alias ll='ls -l'\nalias music='printf music'\n")
        snapshot = self.load()
        snapshot['entries'][0]['command'] = "printf '%s\\n' 'hello # world'"
        snapshot['entries'].append({'name': 'new', 'command': 'echo "$HOME"'})
        saved = self.save(snapshot)
        self.assertTrue(self.config.read_text().startswith(unchanged))
        self.assertEqual(saved['entries'], snapshot['entries'])
        backups = list((self.state/'alias-backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertIn("alias ll='ls -l'", backups[0].read_text())
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_external_changes_block_all_writes(self):
        self.config.write_text("alias a='echo a'\n")
        snapshot = self.load()
        snapshot['entries'][0]['command'] = 'echo edited'
        self.config.write_text('# external change\n' + self.config.read_text())
        with self.assertRaisesRegex(ValueError, 'changed outside'):
            self.save(snapshot)
        self.assertIn('# external change', self.config.read_text())
        self.assertNotIn('edited', self.config.read_text())

    def test_source_includes_and_duplicate_removal_do_not_revive_aliases(self):
        extra = self.home/'.aliases'
        self.config.write_text("alias ll='ls -a'\nsource $HOME/.aliases\n# keep me\n")
        extra.write_text("alias ll='ls -lah'\nalias other='echo other'\n")
        snapshot = self.load()
        self.assertEqual(snapshot['entries'][0]['command'], 'ls -lah')
        snapshot['entries'] = [entry for entry in snapshot['entries'] if entry['name'] != 'll']
        self.assertEqual(self.save(snapshot)['entries'], [{'name': 'other', 'command': 'echo other'}])
        self.assertIn('source $HOME/.aliases\n# keep me', self.config.read_text())

    def test_zdotdir_and_kitty_override_choose_correct_config(self):
        profile = self.home/'.config/hypr'
        profile.mkdir(parents=True)
        (profile/'kitty.conf').write_text('shell /usr/bin/zsh -l\n')
        dotdir = self.home/'zsh'
        dotdir.mkdir()
        (dotdir/'.zshrc').write_text("alias z='echo zsh'\n")
        self.environment['ZDOTDIR'] = str(dotdir)
        snapshot = self.load()
        self.assertEqual(snapshot['shell'], 'zsh')
        self.assertEqual(snapshot['config'], str(dotdir/'.zshrc'))

    def test_fish_functions_survive_abbreviation_edits(self):
        self.environment['SHELL'] = '/usr/bin/fish'
        config = self.home/'.config/fish/config.fish'
        config.parent.mkdir(parents=True)
        function = 'function hello\n  echo hello\nend\n'
        config.write_text(function + 'abbr --add go "git status"\n')
        snapshot = self.load()
        snapshot['entries'][0]['command'] = 'git log --oneline'
        self.save(snapshot)
        self.assertTrue(config.read_text().startswith(function))
        self.assertEqual(self.load()['entries'][0]['command'], 'git log --oneline')

    def test_loading_does_not_evaluate_shell_commands(self):
        marker = self.home/'should-not-exist'
        self.config.write_text(f'source $(touch {marker})\nalias touchme="touch {marker}"\n')
        self.load()
        self.assertFalse(marker.exists())

    def test_reject_duplicate_or_multiline_aliases(self):
        self.config.write_text("alias a='echo a'\n")
        snapshot = self.load()
        snapshot['entries'].append(copy.deepcopy(snapshot['entries'][0]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.save(snapshot)
        snapshot = self.load()
        snapshot['entries'][0]['command'] += '\nother-command'
        with self.assertRaisesRegex(ValueError, 'single-line'):
            self.save(snapshot)
        self.assertEqual(self.config.read_text(), "alias a='echo a'\n")

    def test_adding_first_alias_does_not_require_existing_config(self):
        snapshot = self.load()
        snapshot['entries'] = [{'name': 'hello', 'command': 'echo hello'}]
        self.assertEqual(self.save(snapshot)['entries'], snapshot['entries'])


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def entry(self, extra=''):
        path = self.directory/'example.desktop'
        path.write_text('[Desktop Entry]\nType=Application\nName=Example\nExec=/bin/echo "one argument" %%\n' + extra)
        return path

    def test_desktop_exec_keeps_quoting_and_literal_percent(self):
        argv, directory = startup.entry_command(self.entry('OnlyShowIn=Hyprland;\n'))
        self.assertEqual(argv, ['/bin/echo', 'one argument', '%'])
        self.assertIsNone(directory)

    def test_disabled_and_other_desktop_entries_do_not_autostart(self):
        for extra in ('Hidden=true\n', 'OnlyShowIn=KDE;\n', 'NotShowIn=Hyprland;\n', 'X-GNOME-Autostart-enabled=false\n'):
            with self.subTest(extra=extra):
                self.assertIsNone(startup.entry_command(self.entry(extra)))

    def test_terminal_entries_use_private_kitty_profile(self):
        argv, _ = startup.entry_command(self.entry('Terminal=true\n'))
        self.assertEqual(argv[:3], ['kitty', '--config', str(startup.ROOT/'kitty.conf')])
        self.assertEqual(argv[-3:], ['/bin/echo', 'one argument', '%'])

    def test_run_now_is_explicit_and_can_launch_a_disabled_entry(self):
        self.assertIsNotNone(startup.entry_command(self.entry('Hidden=true\n'), automatic=False))

    def test_environment_values_are_literal_and_do_not_execute_commands(self):
        path = self.directory/'environment.env'
        marker = self.directory/'not-created'
        path.write_text(f'# comment\nEXAMPLE=$(touch {marker})\nOTHER=a=b # literal\n')
        self.assertEqual(startup.environment_values(path), {'EXAMPLE': f'$(touch {marker})', 'OTHER': 'a=b # literal'})
        self.assertFalse(marker.exists())
        path.write_text('NOT A KEY=value\n')
        with self.assertRaises(ValueError):
            startup.environment_values(path)


class CoverageTests(unittest.TestCase):
    def test_every_original_top_level_tool_has_a_panel_route_except_inherited_theme(self):
        import xml.etree.ElementTree as ET
        root = Path(__file__).resolve().parent
        ui = ET.parse(root/'backend/mainwindow.ui')
        original = {widget.attrib['name'] for widget in ui.find(".//widget[@name='tabWidget']").findall('widget')}
        tools = [tool for group in json.loads((root/'tools.json').read_text()) for tool in group['tools']]
        represented = {tool['path'][0] for tool in tools if tool['path']}
        self.assertEqual(original - represented, {'themeTab', 'kvmTab'})
        self.assertIn('cleanerTab', represented)
        ids = [tool['id'] for tool in tools]
        start = ids.index('pacman')
        self.assertEqual(ids[start:start+3], ['pacman', 'paru', 'yay'])

    def test_iso_payloads_preserve_upstream_provenance_and_document_adaptations(self):
        import hashlib
        root = Path(__file__).resolve().parent
        provenance = json.loads((root/'UPSTREAM.json').read_text())
        for relative, expected in provenance['files'].items():
            if relative.startswith('iso/'):
                with self.subTest(file=relative):
                    actual = hashlib.sha256((root/'backend'/relative).read_bytes()).hexdigest()
                    if relative in provenance.get('local_adaptations', {}):
                        self.assertTrue(provenance['local_adaptations'][relative].strip())
                        self.assertNotEqual(actual, expected)
                    else:
                        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
