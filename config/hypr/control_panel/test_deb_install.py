"""Package-manager failures must stop conversion/installation, never fake success."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import deb_install as deb


class DebInstallTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.cache=self.root/'debtap';self.cache.mkdir()
        self.pkgcache=self.root/'pkgfile';self.pkgcache.mkdir()
        self.source=self.root/"browser's $(not-a-command) download.deb"
        self.source.write_bytes(b'downloaded package')
        self.tool=self.root/'debtap-command';self.tool.write_text('#!/bin/bash\nexit 0\n')
        self.commands=[];self.missing={'pactree'}
        self.fail_at=None;self.broken_update=False;self.query_broken=False;self.output_count=1
        self.real_database=deb.prepare_database
        for mock in (patch.object(deb.os,'geteuid',return_value=1000),
                     patch.object(deb.shutil,'which',side_effect=lambda name:None if name in self.missing else
                                  str(self.tool) if name=='debtap' else '/usr/bin/'+name),
                     patch.object(deb,'run',side_effect=self.command),
                     patch.object(deb,'prepare_database',side_effect=lambda:self.real_database(self.cache,self.pkgcache))):
            mock.start();self.addCleanup(mock.stop)
        self.output=io.StringIO()
        redirect=contextlib.redirect_stdout(self.output);redirect.__enter__();self.addCleanup(redirect.__exit__,None,None,None)

    def databases(self):
        for name in deb.DATABASES:(self.cache/name).write_text('package-data\n')
        (self.pkgcache/'core.files').write_bytes(b'pkgfile database')

    def command(self, args, **kwargs):
        args=list(map(str,args));self.commands.append(args)
        if self.fail_at and args[:len(self.fail_at)]==self.fail_at:
            if args[0]=='debtap':(Path(kwargs['cwd'])/'partial.pkg.tar.zst').write_bytes(b'partial')
            raise RuntimeError('Simulated command failed (exit 7): '+' '.join(args))
        if args[:3]==['sudo','pacman','-S']:
            self.missing.difference_update(name for name,package in deb.TOOLS.items() if package in args[4:])
        if args[:3]==['/usr/bin/yay','-S','--needed']:self.missing.discard('debtap')
        if args==['sudo','debtap','-u']:
            self.databases();self.query_broken=False
            if self.broken_update:(self.cache/'extended-base-packages-list').write_text('\n')
        if args==['pkgfile','-l','pacman']:
            if self.query_broken:raise RuntimeError('pkgfile archive is corrupt')
            return subprocess.CompletedProcess(args,0,'core/pacman /usr/bin/pacman\n','')
        if args[0]=='debtap':
            self.assertEqual(args,['debtap','-q','source.deb'])
            work=Path(kwargs['cwd'])
            self.assertEqual((work/'source.deb').read_bytes(),self.source.read_bytes())
            for i in range(self.output_count):(work/f'browser-{i}.pkg.tar.zst').write_bytes(b'converted package')
            (work/'browser.pkg.tar.zst.sig').write_bytes(b'not a package')
        return subprocess.CompletedProcess(args,0,'','')

    def test_missing_pactree_and_partial_cache_are_repaired_before_conversion(self):
        (self.cache/'aur-packages').write_text('left over from a failed update')
        self.assertEqual(deb.main([str(self.source)]),0)
        self.assertEqual(self.commands[:2],[['sudo','pacman','-S','--needed','pacman-contrib'],['sudo','debtap','-u']])
        self.assertEqual(self.commands[2:4],[['pkgfile','-l','pacman'],['debtap','-q','source.deb']])
        self.assertEqual(self.commands[-1][:3],['sudo','pacman','-U'])
        self.assertIn('Installed successfully',self.output.getvalue())

    def test_newline_only_base_list_is_repaired_even_with_all_files_present(self):
        self.databases();(self.cache/'extended-base-packages-list').write_text('\n')
        deb.install(self.source)
        self.assertIn(['sudo','debtap','-u'],self.commands)

    def test_archive_and_dependency_inspection_tools_are_installed_before_conversion(self):
        self.databases();self.missing={'bsdtar','file','which','namcap'}
        deb.install(self.source)
        self.assertEqual(self.commands[0],['sudo','pacman','-S','--needed','libarchive','file','which','namcap'])
        self.assertEqual(self.commands[-1][:3],['sudo','pacman','-U'])

    def test_healthy_cache_skips_download_and_does_not_require_aur_helper(self):
        self.databases();self.missing={'yay','paru'}
        deb.install(self.source)
        self.assertNotIn(['sudo','debtap','-u'],self.commands)
        self.assertEqual(self.commands[0],['pkgfile','-l','pacman'])

    def test_corrupt_pkgfile_index_is_refreshed_before_conversion(self):
        self.databases();self.missing.clear();self.query_broken=True
        deb.install(self.source)
        self.assertEqual(self.commands[:3],[['pkgfile','-l','pacman'],['sudo','debtap','-u'],['pkgfile','-l','pacman']])

    def test_incomplete_update_cannot_reach_conversion_even_when_debtap_exits_zero(self):
        self.broken_update=True
        self.assertEqual(deb.main([str(self.source)]),1)
        self.assertFalse(any(args[0]=='debtap' or args[:3]==['sudo','pacman','-U'] for args in self.commands))
        self.assertIn('database update is incomplete',self.output.getvalue())
        self.assertNotIn('Installed successfully',self.output.getvalue())

    def test_dependency_update_conversion_and_pacman_failures_are_reported(self):
        for command in (['sudo','pacman','-S'],['sudo','debtap','-u'],['debtap'],['sudo','pacman','-U']):
            with self.subTest(command=command):
                self.commands.clear();self.output.seek(0);self.output.truncate();self.missing={'pactree'}
                for path in self.cache.iterdir():path.unlink()
                self.fail_at=command
                self.assertEqual(deb.main([str(self.source)]),1)
                self.assertEqual(self.commands[-1][:len(command)],command)
                self.assertIn('exit 7',self.output.getvalue())
                self.assertNotIn('Installed successfully',self.output.getvalue())

    def test_missing_debtap_installs_as_user_then_continues(self):
        self.missing={'debtap'}
        deb.install(self.source)
        self.assertEqual(self.commands[0],['/usr/bin/yay','-S','--needed','debtap'])
        self.assertEqual(self.commands[-1][:3],['sudo','pacman','-U'])

    def test_no_or_multiple_converted_packages_are_not_installed(self):
        self.databases();self.missing.clear()
        for count in (0,2):
            self.output_count=count;self.commands.clear()
            with self.assertRaisesRegex(RuntimeError,f'produced {count} installable packages'):
                deb.install(self.source)
            self.assertFalse(any(args[:3]==['sudo','pacman','-U'] for args in self.commands))


class DebtapCompatibilityTests(unittest.TestCase):
    """Run the upstream shell guard, not a mocked successful debtap command."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.bin=self.root/'bin';self.bin.mkdir()
        self.cache=self.root/'cache';self.cache.mkdir()
        self.work=self.root/'work';self.work.mkdir()
        self.tool=self.bin/'debtap'
        # The cache-name probe is verbatim from debtap 3.6.3. Redirect only ls
        # to a disposable directory; the real bash/grep condition still runs.
        self.source=b'''#!/bin/bash
ls() { command ls "$TEST_PKGFILE_CACHE"; }
if [[ ! $(ls /var/cache/pkgfile | grep -E '*.files?(.[[:digit:]]{3})' 2> /dev/null) ]] || [[ ! -s "$TEST_DEBTAP_DATA" ]]; then
    echo 'Error: Run debtap -u first'
    exit 1
fi
echo converted
'''
        self.tool.write_bytes(self.source)
        pkgfile=self.bin/'pkgfile'
        pkgfile.write_text('''#!/bin/bash
for index in "$TEST_PKGFILE_CACHE"/*.files "$TEST_PKGFILE_CACHE"/*.files.[0-9][0-9][0-9]; do
    if [[ $(cat "$index" 2>/dev/null) == valid-index ]]; then
        echo 'core/pacman /usr/bin/pacman'
        exit 0
    fi
done
exit 1
''')
        self.tool.chmod(0o755);pkgfile.chmod(0o755)
        self.data=self.root/'debtap-data';self.data.write_text('package data')
        environment=patch.dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
                               TEST_PKGFILE_CACHE=str(self.cache),TEST_DEBTAP_DATA=str(self.data))
        environment.start();self.addCleanup(environment.stop)

    def execute(self, command):
        return subprocess.run(command+['-q','source.deb'],cwd=self.work,capture_output=True,text=True,timeout=5)

    def test_current_and_numbered_caches_pass_actual_shell_guard_after_adaptation(self):
        command=deb.converter(self.work)
        for filename in ('core.files','core.files.001','extra.files.002'):
            with self.subTest(filename=filename):
                index=self.cache/filename;index.write_text('valid-index')
                original=self.execute(['bash',str(self.tool)])
                self.assertEqual(original.returncode,1 if filename=='core.files' else 0)
                result=self.execute(command)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(result.stdout.strip(),'converted')
                index.unlink()
        self.assertEqual(self.tool.read_bytes(),self.source)

    def test_adaptation_keeps_missing_corrupt_and_debtap_data_checks(self):
        command=deb.converter(self.work)
        self.assertEqual(self.execute(command).returncode,1)
        index=self.cache/'core.files';index.write_text('corrupt-index')
        self.assertEqual(self.execute(command).returncode,1)
        index.write_text('valid-index');self.data.unlink()
        self.assertEqual(self.execute(command).returncode,1)

    def test_already_fixed_converter_runs_unchanged(self):
        self.tool.write_bytes(self.source.replace(deb.LEGACY_CACHE_PROBE,b'pkgfile -l pacman'))
        (self.cache/'core.files').write_text('valid-index')
        self.assertEqual(deb.converter(self.work),['debtap'])
        self.assertEqual(self.execute(['debtap']).returncode,0)
        self.assertFalse((self.work/'debtap-compat').exists())


if __name__=='__main__':unittest.main()
