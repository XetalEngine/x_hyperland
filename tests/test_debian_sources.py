"""Debian source repair fixtures; no host APT files or packages are modified."""
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import debian_sources as sources

DVD = 'deb cdrom:[Debian GNU/Linux 13.7.0 _Trixie_ - Official amd64 DVD Binary-1 with firmware 20260912-09:36]/ trixie contrib main non-free-firmware\n'
NETWORK = 'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://mirror.example/debian trixie main\n'


class SourcePlanTests(unittest.TestCase):
    def test_dvd_only_adds_fixed_release_official_signed_repositories(self):
        before = {'sources.list': '# Installed from DVD\n'+DVD}
        after = sources.prepare(before)
        self.assertIn('# Disabled installation media', after['sources.list'])
        self.assertIn(DVD, after['sources.list'])
        added = after['sources.list.d/xetal-debian.sources']
        self.assertIn('URIs: https://deb.debian.org/debian\n', added)
        self.assertIn('Suites: trixie trixie-updates\n', added)
        self.assertIn('URIs: https://security.debian.org/debian-security\n', added)
        self.assertIn('Suites: trixie-security\n', added)
        self.assertEqual(added.count('Signed-By: '+str(sources.KEYRING)), 2)
        for unwanted in ('trusted=yes', 'Trusted: yes', 'testing', 'backports'):
            self.assertNotIn(unwanted, added)
        self.assertEqual(sources.prepare(after), after)

    def test_empty_or_commented_sources_get_online_repositories(self):
        for before in ({}, {'sources.list': '# '+DVD}, {'sources.list': '\n# No mirror chosen\n'}):
            after = sources.prepare(before)
            self.assertIn('sources.list.d/xetal-debian.sources', after)
            self.assertTrue(all(after[name] == text for name, text in before.items()))

    def test_existing_mirror_and_third_party_sources_stay_byte_identical(self):
        before = {'sources.list': NETWORK,
                  'sources.list.d/vendor.list': 'deb [arch=amd64 signed-by=/etc/apt/keyrings/vendor.gpg] https://vendor.example/repo stable main\n'}
        self.assertEqual(sources.prepare(before), before)
        before['sources.list'] += DVD
        after = sources.prepare(before)
        self.assertEqual(set(after), set(before))
        self.assertTrue(after['sources.list'].startswith(NETWORK))
        self.assertEqual(after['sources.list.d/vendor.list'], before['sources.list.d/vendor.list'])

    def test_disabled_and_source_only_repositories_do_not_cover_binary_packages(self):
        for disabled in ('no', 'false', '0'):
            before = {'sources.list.d/disabled.sources': 'Types: deb\nURIs: https://deb.debian.org/debian\nSuites: trixie\nComponents: main\nEnabled: '+disabled+'\n',
                      'sources.list': 'deb-src https://deb.debian.org/debian trixie main\n'}
            after = sources.prepare(before)
            self.assertIn('sources.list.d/xetal-debian.sources', after)
            self.assertTrue(all(after[name] == text for name, text in before.items()))

    def test_third_party_stable_feed_does_not_replace_the_debian_archive(self):
        vendor = 'deb https://vendor.example/browser stable main\n'
        after = sources.prepare({'sources.list': DVD, 'sources.list.d/browser.list': vendor})
        self.assertIn('sources.list.d/xetal-debian.sources', after)
        self.assertEqual(after['sources.list.d/browser.list'], vendor)
        before = {'sources.list': 'deb https://mirror.example/debian stable main\n'}
        self.assertEqual(sources.prepare(before), before)

    def test_security_only_does_not_duplicate_existing_security_mirror(self):
        before = {'sources.list': 'deb https://security.debian.org/debian-security trixie-security main\n'}
        after = sources.prepare(before)
        self.assertEqual(after['sources.list'], before['sources.list'])
        added = after['sources.list.d/xetal-debian.sources']
        self.assertIn('Suites: trixie trixie-updates', added)
        self.assertNotIn('trixie-security', added)

    def test_name_collision_never_overwrites_a_user_source_file(self):
        before = {'sources.list.d/xetal-debian.sources': '# My disabled source\n'}
        after = sources.prepare(before)
        self.assertEqual(after['sources.list.d/xetal-debian.sources'], before['sources.list.d/xetal-debian.sources'])
        self.assertIn('sources.list.d/xetal-debian-1.sources', after)
        self.assertEqual(sources.prepare(after), after)

    def test_list_cdrom_options_and_source_entries_are_disabled_without_touching_comments(self):
        original = '# '+DVD+'  deb-src [arch=amd64] cdrom:[Disc with spaces]/ trixie main\n'+NETWORK
        after, found = sources.list_sources(original)
        self.assertEqual(after.splitlines()[0], original.splitlines()[0])
        self.assertTrue(after.splitlines()[1].startswith('# Disabled installation media'))
        self.assertTrue(after.endswith(NETWORK))
        self.assertEqual(found, {'trixie'})

    def test_deb822_dvd_stanza_is_disabled_and_unrelated_fields_preserved(self):
        stanza = '# DVD\nTypes: deb deb-src\nURIs: cdrom:[Disc with spaces]/\nSuites: trixie\nComponents: main\nEnabled: yes\n'
        untouched = '# Custom\nTypes: deb\nURIs: https://mirror.example/debian\nSuites: trixie\nComponents: main\nSigned-By:\n -----BEGIN PGP PUBLIC KEY BLOCK-----\n .\n fake-test-key\n -----END PGP PUBLIC KEY BLOCK-----\n'
        after, found = sources.deb822_sources(stanza+'\n'+untouched)
        self.assertIn('Enabled: no', after)
        self.assertIn('URIs: cdrom:[Disc with spaces]/', after)
        self.assertIn(untouched, after)
        self.assertEqual(found, {'trixie'})
        self.assertEqual(sources.deb822_sources(after)[0], after)

    def test_deb822_mixed_uris_preserve_network_and_other_continuations(self):
        original = 'Types: deb\nURIs: cdrom://[Disc with spaces]/\n https://mirror.example/debian\n# Retain this comment\nSuites: trixie\n trixie-updates\nComponents: main\n non-free-firmware\nSigned-By: /custom/keyring.gpg'
        after, found = sources.deb822_sources(original)
        self.assertNotIn('cdrom:', after)
        self.assertIn('URIs: https://mirror.example/debian\n', after)
        self.assertIn('# Retain this comment\n', after)
        self.assertIn('Suites: trixie\n trixie-updates\n', after)
        self.assertTrue(after.endswith('Signed-By: /custom/keyring.gpg'))
        self.assertEqual(found, {'trixie', 'trixie-updates'})

    def test_disabled_cdrom_stanzas_are_not_rewritten(self):
        original = 'Types: deb\nURIs: cdrom:[Disc]/\nSuites: trixie\nComponents: main\nEnabled: no\n'
        self.assertEqual(sources.deb822_sources(original), (original, set()))

    def test_malformed_duplicate_deb822_fields_stop_planning(self):
        with self.assertRaisesRegex(RuntimeError, 'Duplicate field'):
            sources.prepare({'sources.list.d/user.sources': 'URIs: https://one.example\nURIs: https://two.example\n'})


class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.apt = self.root/'apt'; self.apt.mkdir()
        (self.apt/'sources.list.d').mkdir()
        self.original = self.apt/'sources.list'; self.original.write_text(DVD)
        self.original.chmod(0o640)
        self.state = self.root/'backups'
        self.enterContext(patch.object(sources.os, 'geteuid', return_value=0))
        self.enterContext(patch.object(sources.runtime.policy, 'debian_host', return_value=True))
        key = self.root/'archive-keyring'; key.touch()
        self.enterContext(patch.object(sources, 'KEYRING', key))

    def refresh(self):
        return sources.refresh(self.apt, self.state)

    def test_success_validates_before_publishing_then_retries_without_another_backup(self):
        def validate(args):
            self.assertEqual(self.original.read_text(), DVD)
            staged = next(value.split('=', 1)[1] for value in args if value.startswith('Dir::Etc::sourcelist='))
            self.assertIn('# Disabled installation media', Path(staged).read_text())
            return 0
        with patch.object(sources, 'update', side_effect=validate) as update:
            self.assertEqual(self.refresh(), 0)
            update.assert_called_once()
        backups = [path for path in self.state.iterdir() if path.is_dir()]
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0]/'sources.list').read_text(), DVD)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.original.stat().st_mode), 0o640)
        record = json.loads((backups[0]/'record.json').read_text())
        self.assertTrue(record['sources.list']['existed'])
        self.assertFalse(record['sources.list.d/xetal-debian.sources']['existed'])
        after = sources.read_sources(self.apt)
        with patch.object(sources, 'update', return_value=0) as update:
            self.assertEqual(self.refresh(), 0)
            update.assert_called_once_with()
        self.assertEqual(sources.read_sources(self.apt), after)
        self.assertEqual([p for p in self.state.iterdir() if p.is_dir()], backups)

    def test_network_signature_failure_or_interruption_preserves_sources(self):
        for error in (None, KeyboardInterrupt()):
            with self.subTest(error=error), patch.object(sources, 'update', return_value=100, side_effect=error):
                if error:
                    with self.assertRaises(KeyboardInterrupt): self.refresh()
                else:
                    self.assertEqual(self.refresh(), 100)
            self.assertEqual(self.original.read_text(), DVD)
            self.assertEqual(list((self.apt/'sources.list.d').iterdir()), [])
            self.assertEqual([p for p in self.state.iterdir() if p.is_dir()], [])

    def test_missing_keyring_stops_before_update_or_source_changes(self):
        sources.KEYRING.unlink()
        with patch.object(sources, 'update') as update:
            with self.assertRaisesRegex(RuntimeError, 'keyring is missing'): self.refresh()
            update.assert_not_called()
        self.assertEqual(self.original.read_text(), DVD)

    def test_external_source_edit_during_refresh_is_preserved(self):
        def update(args):
            self.original.write_text(NETWORK)
            return 0
        with patch.object(sources, 'update', side_effect=update):
            with self.assertRaisesRegex(RuntimeError, 'sources changed'): self.refresh()
        self.assertEqual(self.original.read_text(), NETWORK)
        self.assertFalse((self.apt/'sources.list.d/xetal-debian.sources').exists())

    def test_partial_write_failure_restores_already_changed_files(self):
        real_atomic = sources.atomic
        def atomic(path, data, mode=0o644):
            if path == self.apt/'sources.list.d/xetal-debian.sources':
                raise OSError('injected disk error')
            return real_atomic(path, data, mode)
        with patch.object(sources, 'update', return_value=0), patch.object(sources, 'atomic', side_effect=atomic):
            with self.assertRaisesRegex(OSError, 'injected disk error'): self.refresh()
        self.assertEqual(self.original.read_text(), DVD)
        self.assertEqual(stat.S_IMODE(self.original.stat().st_mode), 0o640)
        self.assertFalse((self.apt/'sources.list.d/xetal-debian.sources').exists())

    def test_disabled_backup_files_are_ignored(self):
        ignored = self.apt/'sources.list.d/user.list.save'; ignored.write_text('bad backup syntax\n')
        with patch.object(sources, 'update', return_value=0): self.refresh()
        self.assertEqual(ignored.read_text(), 'bad backup syntax\n')

    def test_symlink_source_is_not_followed_or_replaced(self):
        target = self.root/'untouched'; target.write_text(DVD)
        self.original.unlink(); self.original.symlink_to(target)
        with patch.object(sources, 'update') as update:
            with self.assertRaisesRegex(RuntimeError, 'symbolic links'): self.refresh()
            update.assert_not_called()
        self.assertTrue(self.original.is_symlink())
        self.assertEqual(target.read_text(), DVD)

    def test_guard_rejects_other_distros_and_unprivileged_calls_before_writes(self):
        for uid, debian in ((1000, True), (0, False)):
            with patch.object(sources.os, 'geteuid', return_value=uid), \
                 patch.object(sources.runtime.policy, 'debian_host', return_value=debian), \
                 patch.object(sources, 'update') as update:
                with self.assertRaisesRegex(RuntimeError, 'Debian 13'): self.refresh()
                update.assert_not_called()
                self.assertFalse(self.state.exists())

    def test_real_apt_invocation_requires_valid_metadata_without_installing(self):
        with patch.object(sources.subprocess, 'run', return_value=subprocess.CompletedProcess([], 100)) as run:
            self.assertEqual(sources.update(), 100)
        command = run.call_args.args[0]
        self.assertEqual(command[0], '/usr/bin/apt-get')
        self.assertEqual(command[-1], 'update')
        self.assertIn('APT::Update::Error-Mode=any', command)
        self.assertIn('APT::Get::AllowUnauthenticated=false', command)
        self.assertIn('-q', command)
        self.assertNotIn('install', command)
        self.assertNotIn('upgrade', command)


if __name__ == '__main__': unittest.main()
