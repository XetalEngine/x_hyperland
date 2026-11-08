"""Regression cases from vendor Debian metadata and isolated archive fixtures."""
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import deb_dependencies as deps
import deb_install


class Inventory(deps.Repository):
    def __init__(self, local=None, sync=None):
        self.local = local or {}
        self.sync = sync or {}


def fields(requirements='', **extra):
    return dict(package='example', version='1.0-1', architecture='amd64',
                depends=requirements, **extra)


@unittest.skipUnless(shutil.which('vercmp'), 'pacman version comparison required')
class DependencyTests(unittest.TestCase):
    def resolve(self, requirements, local=None, sync=None, **extra):
        return deps.resolve(fields(requirements, **extra), Inventory(local, sync), 'x86_64')

    def test_discord_1_0_168_dependencies_resolve_without_an_aur_lookup(self):
        # Depends from the official Discord 1.0.168 amd64 archive, checked
        # 2026-11-08: https://discord.com/api/download?platform=linux&format=deb
        # SHA256: 93d43ad090825b9edcacfb3841506ea51e7040c60d93a9e377d0caca547bea28
        control = dict(package='discord', version='1.0.168', architecture='amd64',
                       depends=('libc6, libasound2, libatk1.0-0, libatk-bridge2.0-0, '
                                'libatspi2.0-0, libatomic1, libcairo2, libdbus-1-3, '
                                'libexpat1, libgbm1, libglib2.0-0, libgtk-3-0, '
                                'libnotify4, libnspr4, libnss3, libpango-1.0-0, '
                                'libstdc++6, libudev1, libx11-6, libxcb1, '
                                'libxcomposite1, libxdamage1, libxext6, libxfixes3, '
                                'libxkbcommon0, libxrandr2'))
        expected = ['glibc', 'alsa-lib', 'at-spi2-core', 'libatomic', 'cairo',
                    'dbus', 'expat', 'mesa', 'glib2', 'gtk3', 'libnotify', 'nspr',
                    'nss', 'pango', 'libstdc++', 'systemd-libs', 'libx11',
                    'libxcb', 'libxcomposite', 'libxdamage', 'libxext',
                    'libxfixes', 'libxkbcommon', 'libxrandr']
        aur = deps.AurRepository()
        with patch.object(aur, 'available', side_effect=AssertionError('unnecessary AUR lookup')):
            result, rows = deps.resolve(control, Inventory(sync=dict.fromkeys(expected, '1.0-1')),
                                        'x86_64', aur)
        self.assertEqual(result, expected)
        self.assertIn('libatomic1 → libatomic (repository: 1.0-1)', rows)
        self.assertEqual(aur.selected, {})

    def test_uuid_runtime_mapping_preserves_versions_and_abi(self):
        # Both package file lists contain libuuid.so.1 (util-linux):
        # https://packages.debian.org/trixie/amd64/libuuid1/filelist
        # https://archlinux.org/packages/core/x86_64/util-linux-libs/files/
        result, rows = self.resolve('libuuid1 (>= 2.31.1)', local={'util-linux-libs': '2.42.4-1'})
        self.assertEqual(result, ['util-linux-libs>=2.31.1'])
        self.assertIn('(installed: 2.42.4-1)', rows[0])
        with self.assertRaisesRegex(RuntimeError, 'missing or below its minimum'):
            self.resolve('libuuid1 (>= 2.31.1)', sync={'util-linux-libs': '2.30-1'})
        with self.assertRaisesRegex(RuntimeError, 'libuuid2'):
            self.resolve('libuuid2', sync={'util-linux-libs': '2.42.4-1'})

    def test_gcc_runtime_mappings_preserve_minimums_and_use_split_arch_packages(self):
        mappings = {'libatomic1': 'libatomic', 'libgcc-s1': 'libgcc',
                    'libstdc++6': 'libstdc++', 'libgomp1': 'libgomp',
                    'libquadmath0': 'libquadmath', 'libgfortran5': 'libgfortran'}
        for debian, arch in mappings.items():
            with self.subTest(dependency=debian):
                requirement = f'{debian} (>= 14.2.0-3)'
                result, rows = self.resolve(requirement, local={arch: '14.2.1-1'})
                self.assertEqual(result, [arch + '>=14.2.0'])
                self.assertIn('(installed: 14.2.1-1)', rows[0])
                result, rows = self.resolve(requirement, local={arch: '13.3.0-1'},
                                            sync={arch: '16.2.1-1'})
                self.assertEqual(result, [arch + '>=14.2.0'])
                self.assertIn('(repository: 16.2.1-1)', rows[0])
                # A missing/old component cannot be satisfied by the version
                # of the gcc-libs meta-package or by omitting the dependency.
                for inventory in ({'gcc-libs': '99.0-1'}, {arch: '99:13.3.0-1'}):
                    with self.subTest(inventory=inventory):
                        with self.assertRaisesRegex(RuntimeError, 'missing or below its minimum'):
                            self.resolve(requirement, sync=inventory)

    def test_unsupported_gcc_runtime_abis_are_not_mapped_to_current_libraries(self):
        packages = {'libatomic': '16.2.1-1', 'libstdc++': '16.2.1-1',
                    'libgfortran': '16.2.1-1'}
        for requirement in ('libatomic2', 'libstdc++5', 'libgfortran4'):
            with self.subTest(dependency=requirement):
                with self.assertRaisesRegex(RuntimeError, requirement.replace('+', r'\+')):
                    self.resolve(requirement, sync=packages)

    def test_vscode_1_145_2_dependencies_resolve_without_an_aur_lookup(self):
        # Depends from Microsoft's 1.145.2-1793945276 amd64 archive:
        # https://update.code.visualstudio.com/1.145.2/linux-deb-x64/stable
        # SHA256: aa2bfc5a3db4f0971e8b50ce08d07b1849894a9caca2b0f8ea5b07ac8d68da8d
        control = ('ca-certificates, libasound2 (>= 1.0.17), '
                   'libatk-bridge2.0-0 (>= 2.5.3), libatk1.0-0 (>= 2.11.90), '
                   'libatspi2.0-0 (>= 2.9.90), libc6 (>= 2.15), libc6 (>= 2.16), '
                   'libc6 (>= 2.17), libc6 (>= 2.2.5), libc6 (>= 2.25), '
                   'libc6 (>= 2.28), libc6 (>= 2.4), libcairo2 (>= 1.6.0), '
                   'libcups2 (>= 1.6.0), libcurl3-gnutls | libcurl3-nss | libcurl4 | libcurl3, '
                   'libdbus-1-3 (>= 1.9.14), libexpat1 (>= 2.1~beta3), '
                   'libgbm1 (>= 17.1.0~rc2), libglib2.0-0 (>= 2.12.0), '
                   'libglib2.0-0 (>= 2.39.4), libgtk-3-0 (>= 3.9.10), '
                   'libgtk-3-0 (>= 3.9.10) | libgtk-4-1, libnspr4 (>= 2:4.9-2~), '
                   'libnss3 (>= 2:3.30), libnss3 (>= 3.26), libpango-1.0-0 (>= 1.14.0), '
                   'libudev1 (>= 183), libx11-6, libx11-6 (>= 2:1.4.99.1), '
                   'libxcb1 (>= 1.9.2), libxcomposite1 (>= 1:0.4.4-1), '
                   'libxdamage1 (>= 1:1.1), libxext6, libxfixes3, '
                   'libxkbcommon0 (>= 0.5.0), libxkbfile1 (>= 1:1.1.0), '
                   'libxrandr2, xdg-utils (>= 1.0.2)')
        packages = {'ca-certificates': '20260101-1', 'alsa-lib': '1.2.16.1-1',
                    'at-spi2-core': '2.62.1-1', 'glibc': '2.44-1', 'cairo': '1.18.6-1',
                    'libcups': '2.4.19-1', 'curl': '8.23.0-1', 'dbus': '1.16.2-1',
                    'expat': '2.9.0-1', 'mesa': '1:26.2.5-1', 'glib2': '2.90.1-1',
                    'gtk3': '1:3.24.52-2', 'nspr': '4.40-1', 'nss': '3.132-1',
                    'pango': '1:1.58.2-1', 'systemd-libs': '262.1-1',
                    'libx11': '1.8.14-1', 'libxcb': '1.17.0-1', 'libxcomposite': '0.4.7-1',
                    'libxdamage': '1.1.7-1', 'libxext': '1.3.7-1', 'libxfixes': '6.0.2-1',
                    'libxkbcommon': '1.13.2-1', 'libxkbfile': '1.2.0-1',
                    'libxrandr': '1.5.5-1', 'xdg-utils': '1.2.1-1'}
        aur = deps.AurRepository()
        with patch.object(aur, 'available', side_effect=AssertionError('unnecessary AUR lookup')):
            result, rows = deps.resolve(fields(control), Inventory(sync=packages), 'x86_64', aur)
        self.assertIn('libxkbfile>=1.1.0', result)
        self.assertIn('libxkbfile1 (>= 1:1.1.0) → libxkbfile>=1.1.0 (repository: 1.2.0-1)', rows)
        self.assertEqual({re.split(r'[<>=]', item, maxsplit=1)[0] for item in result}, set(packages))
        self.assertEqual(aur.selected, {})

    def test_xkbfile_mapping_keeps_minimum_and_abi_checks(self):
        requirement = 'libxkbfile1 (>= 1:1.1.0)'
        self.assertEqual(self.resolve(requirement, local={'libxkbfile': '1.2.0-1'})[0],
                         ['libxkbfile>=1.1.0'])
        for packages in ({}, {'libxkbfile': '99:1.0.9-1'}, {'libxkbcommon': '99.0-1'}):
            with self.subTest(inventory=packages):
                with self.assertRaisesRegex(RuntimeError, 'missing or below its minimum'):
                    self.resolve(requirement, sync=packages)
        with self.assertRaisesRegex(RuntimeError, 'libxkbfile2'):
            self.resolve('libxkbfile2', sync={'libxkbfile': '1.2.0-1'})

    def test_chrome_epochs_never_become_part_of_package_names(self):
        control = ('libnspr4 (>= 2:4.9-2~), libnss3 (>= 2:3.35), '
                   'libx11-6 (>= 2:1.4.99.1), libxcomposite1 (>= 1:0.4.4-1), '
                   'libxdamage1 (>= 1:1.1), libgtk-3-0 (>= 3.9.10) | libgtk-4-1')
        packages = {'nspr': '4.40-1', 'nss': '3.132-1', 'libx11': '1.8.14-1',
                    'libxcomposite': '0.4.7-1', 'libxdamage': '1.1.7-1',
                    'gtk3': '1:3.24.52-2'}
        result, _ = self.resolve(control, sync=packages)
        self.assertEqual(result, ['nspr>=4.9', 'nss>=3.35', 'libx11>=1.4.99.1',
                                 'libxcomposite>=0.4.4', 'libxdamage>=1.1', 'gtk3>=1:3.9.10'])

    def test_alternatives_select_one_suitable_installed_component(self):
        result, _ = self.resolve('libcurl3-gnutls | libcurl3-nss | libcurl4 | libcurl3',
                                 local={'curl': '8.23.0-1'}, sync={'libcurl-gnutls': '8.23.0-1'})
        self.assertEqual(result, ['curl'])
        result, _ = self.resolve('libgtk-3-0 (>= 3.9.10) | libgtk-4-1', sync={'gtk4': '1:4.24.1-1'})
        self.assertEqual(result, ['gtk4'])

    def test_too_old_local_can_use_repository_upgrade(self):
        result, _ = self.resolve('libnss3 (>= 2:3.35)', local={'nss': '3.30-1'}, sync={'nss': '3.132-1'})
        self.assertEqual(result, ['nss>=3.35'])

    def test_arch_epoch_cannot_hide_an_insufficient_upstream_version(self):
        with self.assertRaisesRegex(RuntimeError, 'below its minimum'):
            self.resolve('libgtk-3-0 (>= 3.24)', sync={'gtk3': '99:3.20-1'})

    def test_pre_release_minimum_requires_stable_upstream_version(self):
        result, _ = self.resolve('libexpat1 (>= 2.1~beta3)', local={'expat': '2.9-1'})
        self.assertEqual(result, ['expat>=2.1'])

    def test_predepends_are_preserved_including_dpkg(self):
        result, _ = self.resolve('ca-certificates', sync={'ca-certificates': '20260101-1', 'dpkg': '1.23-1'},
                                 **{'pre-depends': 'dpkg (>= 1.14.0)'})
        self.assertEqual(result, ['dpkg>=1.14.0', 'ca-certificates'])

    def test_unknown_abi_and_unavailable_dependencies_are_not_guessed_or_dropped(self):
        with self.assertRaisesRegex(RuntimeError, 'libssl1.1.*\n  missing-component'):
            self.resolve('libssl1.1, missing-component', sync={'openssl': '3.6-1'})

    def test_equal_upper_and_strict_bounds_require_a_recipe(self):
        for op in ('=', '<=', '<<', '>>'):
            with self.subTest(op=op), self.assertRaisesRegex(RuntimeError, 'recipe'):
                self.resolve(f'libnss3 ({op} 3.35)', sync={'nss': '3.132-1'})

    def test_version_bound_on_unsupported_alternative_does_not_block_valid_alternative(self):
        result, _ = self.resolve('old (= 1.0) | libgtk-4-1', sync={'gtk4': '4.24-1'})
        self.assertEqual(result, ['gtk4'])

    def test_multiarch_qualifiers_are_explicit(self):
        self.assertEqual(self.resolve('libc6:amd64 (>= 2.25), python3:any',
                                     local={'glibc': '2.44-1', 'python': '3.14-1'})[0],
                         ['glibc>=2.25', 'python'])
        with self.assertRaisesRegex(RuntimeError, 'foreign architecture'):
            self.resolve('libc6:i386', local={'glibc': '2.44-1'})
        with self.assertRaisesRegex(RuntimeError, 'Cross-architecture'):
            deps.resolve(dict(fields(), architecture='arm64'), Inventory(), 'x86_64')

    def test_bad_syntax_is_not_interpreted_as_shell_or_a_missing_dependency(self):
        for text in ('libc6; touch /tmp/bad', 'x$(echo)', 'libc6 |', 'libc6 (>=)',
                     'libc6 [amd64]', 'libc6,', 'libc6 (>= 2.1) extra'):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, 'syntax'):
                self.resolve(text)

    def test_aur_is_used_only_after_installed_and_repository_alternatives(self):
        aur = deps.AurRepository(); aur.versions = {'custom-library': '2.4-1'}
        dependencies, rows = deps.resolve(fields('custom-library (>= 2.1)'), Inventory(), 'x86_64', aur)
        self.assertEqual(dependencies, ['custom-library>=2.1'])
        self.assertIn('(AUR: 2.4-1)', rows[0])
        self.assertEqual(aur.selected, {'custom-library>=2.1': '2.4-1'})
        aur = deps.AurRepository()
        with patch.object(aur, 'available', side_effect=AssertionError('unnecessary AUR lookup')):
            result, _ = deps.resolve(fields('custom-library | libgtk-4-1'),
                                     Inventory(sync={'gtk4':'4.24-1'}), 'x86_64', aur)
        self.assertEqual(result, ['gtk4'])

    def test_aur_floor_is_checked_and_unknown_names_are_not_fuzzily_matched(self):
        aur = deps.AurRepository(); aur.versions = {'custom-library':'1.9-1', 'libssl1.1':None}
        with self.assertRaisesRegex(RuntimeError, 'below its minimum version in the AUR'):
            deps.resolve(fields('custom-library (>= 2.1)'), Inventory(), 'x86_64', aur)
        with self.assertRaisesRegex(RuntimeError, 'libssl1.1'):
            deps.resolve(fields('libssl1.1'), Inventory(sync={'openssl':'3.6-1'}), 'x86_64', aur)
        self.assertEqual(aur.selected, {})

    def test_aur_info_validates_exact_names_caches_results_and_stops_on_network_failure(self):
        raw = json.dumps({'type':'multiinfo','results':[{'Name':'custom-library','Version':'2:3.0-1'}]}).encode()
        aur = deps.AurRepository()
        with patch.object(deps,'urlopen',return_value=io.BytesIO(raw)) as request:
            self.assertEqual(aur.available('custom-library'), [('2:3.0-1',False)])
            self.assertEqual(aur.available('custom-library'), [('2:3.0-1',False)])
            self.assertEqual(request.call_count,1)
        with patch.object(deps,'urlopen',side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError,'Could not check the AUR.*offline'):
                aur.available('another-library')
        raw = json.dumps({'type':'multiinfo','results':[{'Name':'similar-library','Version':'9.0'}]}).encode()
        with patch.object(deps,'urlopen',return_value=io.BytesIO(raw)):
            self.assertEqual(aur.available('another-library'), [])


class MetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fusion-deb ' test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_fresh_offline_system_reports_missing_indexes_before_claiming_packages_are_unavailable(self):
        def command(args):
            return 'core\nextra\nmultilib\n' if args[-1] == '--repo-list' else str(self.root)
        with patch.object(deps, 'command', side_effect=command):
            with self.assertRaisesRegex(deps.MissingRepositoryIndexes, 'core, extra, multilib'):
                deps.Repository()
            (self.root/'sync').mkdir()
            for name in ('core', 'extra', 'multilib'):
                (self.root/'sync'/(name+'.db')).write_bytes(b'index')
            deps.check_repository_indexes()
            (self.root/'sync/extra.db').write_bytes(b'')
            with self.assertRaisesRegex(deps.MissingRepositoryIndexes, 'empty: extra'):
                deps.check_repository_indexes()

    def test_folded_dependency_fields_are_joined(self):
        result = deps.control_fields('Package: example\nVersion: 1.0\nArchitecture: all\n'
                                     'Depends: libgtk-3-0 (>= 3.9.10) |\n libgtk-4-1,\n libc6\n')
        self.assertEqual(len(deps.parse_relationships(result['depends'])), 2)

    def test_duplicate_and_missing_fields_are_rejected(self):
        for text in ('Package: x\nVersion: 1',
                     'Package: x\nVersion: 1\nArchitecture: all\nDepends: a\nDepends: b\n'):
            with self.assertRaises(RuntimeError):
                deps.control_fields(text)

    @unittest.skipUnless(shutil.which('ar') and shutil.which('bsdtar'), 'archive tools required')
    def test_read_control_does_not_extract_or_execute_scripts(self):
        archive = self.root/'control.tar.gz'
        raw = b'Package: example\nVersion: 1.0\nArchitecture: all\nDepends: bash\n'
        with tarfile.open(archive, 'w:gz') as stream:
            for name, data in (('./control', raw), ('./postinst', b'#!/bin/sh\nexit 99\n')):
                info = tarfile.TarInfo(name); info.size = len(data)
                stream.addfile(info, io.BytesIO(data))
        package = self.root/'example.deb'
        subprocess.run(['ar', 'qc', str(package), str(archive)], check=True)
        self.assertEqual(deps.read_control(package)['depends'], 'bash')
        self.assertFalse((self.root/'postinst').exists())

    def test_dependency_replacement_runs_before_mtree_and_preserves_other_fields(self):
        tool = self.root/'debtap'
        original = '''#!/bin/bash
printf 'pkgname = example\npkgver = 1.0-1\ndepend = nss3.35\nconflict = another\n' > .PKGINFO
printf 'dependency-detected-not-included qt6-base\n' > namcap-checks
rm -rf test.pkg.tar
# Generating .MTREE file
cp .PKGINFO metadata-seen-by-mtree
'''
        tool.write_text(original)
        with patch.object(deb_install.shutil, 'which', return_value=str(tool)):
            command = deb_install.converter(self.root, ['nss>=3.35', 'gtk3>=1:3.9.10'])
        subprocess.run(command, cwd=self.root, check=True)
        content = (self.root/'metadata-seen-by-mtree').read_text()
        self.assertIn('depend = nss>=3.35\n', content)
        self.assertIn('depend = gtk3>=1:3.9.10\n', content)
        self.assertIn('conflict = another\n', content)
        self.assertIn('depend = qt6-base\n', content)
        self.assertEqual(deb_install.native_dependencies(self.root), ['qt6-base'])
        self.assertNotIn('nss3.35', content)
        self.assertEqual(tool.read_text(), original)

    def test_failed_library_inspection_pipeline_is_not_a_successful_conversion(self):
        tool = self.root/'debtap'
        tool.write_text('''#!/bin/bash
false | cat > namcap-checks
rm -rf test.pkg.tar
# Generating .MTREE file
touch should-not-exist
''')
        with patch.object(deb_install.shutil, 'which', return_value=str(tool)):
            command = deb_install.converter(self.root, [])
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Native library inspection failed', result.stderr)
        self.assertFalse((self.root/'should-not-exist').exists())

    def test_unknown_debtap_packaging_layout_is_not_silently_used(self):
        tool = self.root/'debtap'; tool.write_text('#!/bin/bash\nexit 0\n')
        with patch.object(deb_install.shutil, 'which', return_value=str(tool)):
            with self.assertRaisesRegex(RuntimeError, 'unsupported packaging layout'):
                deb_install.converter(self.root, ['nss'])


if __name__ == '__main__':
    unittest.main()
