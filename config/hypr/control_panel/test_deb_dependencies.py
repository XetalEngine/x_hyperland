"""Regression cases from Chrome's Debian metadata and isolated archive fixtures."""
import io
import os
from pathlib import Path
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


class MetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fusion-deb ' test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

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
