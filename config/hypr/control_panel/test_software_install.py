"""Run disposable installers; no package transactions or user settings changes."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import shlex
import unittest
from unittest.mock import patch
import software_install as install
import software_favorites as favorites


class InstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.home = Path(temp.name)
        env = patch.dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.home/'data'), XDG_CACHE_HOME=str(self.home/'cache'))
        env.start(); self.addCleanup(env.stop)
        p = patch.object(install, 'pin_desktop', return_value=True); self.pin = p.start(); self.addCleanup(p.stop)
        self.events = []

    def script(self, body):
        path = self.home/'setup.run'; path.write_text('#!/bin/sh\nset -eu\n'+body); path.chmod(0o600)
        return path, dict(filename=path.name, size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_verified_installer_gets_execute_permission_runs_and_then_pins(self):
        path, artifact = self.script('test -x "$0"\nmkdir -p "$XDG_DATA_HOME/applications"\nprintf "[Desktop Entry]\\nType=Application\\nName=XMusic\\nExec=true\\n" > "$XDG_DATA_HOME/applications/xmusic.desktop"\n')
        result = install.install('xmusic', artifact=artifact, bundled=path, progress=self.events.append)
        self.assertTrue(result.is_file()); self.pin.assert_called_once_with(result)
        self.assertFalse(path.stat().st_mode & 0o111)  # Only private verified copy executable.
        self.assertFalse(list((self.home/'cache/hyperfusion/software').glob('xmusic-*')))
        self.assertTrue(any(e['type']=='installing' for e in self.events))

    def test_failed_hash_or_installer_never_adds_favorite(self):
        path, artifact = self.script('echo useful-failure >&2\nexit 9\n')
        with self.assertRaisesRegex(RuntimeError, 'useful-failure'):
            install.install('xmusic', artifact=artifact, bundled=path)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            install.install('xmusic', artifact={**artifact,'sha256':'0'*64}, bundled=path)
        self.pin.assert_not_called()

    def test_cancelled_wizard_without_launcher_is_not_reported_installed(self):
        path, artifact = self.script('exit 0\n')
        with self.assertRaisesRegex(RuntimeError, 'without installing'):
            install.install('echo', artifact=artifact, bundled=path)
        self.pin.assert_not_called()

    def test_studio_uses_archive_and_creates_a_launchable_entry(self):
        archive = self.home/'studio.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            for name,data in [('studio/run.sh',('#!/bin/sh\ntouch '+shlex.quote(str(self.home/'launched'))+'\n').encode()),('studio/AppRun',b'#!/bin/sh\nexit 0\n')]:
                m=tarfile.TarInfo(name);m.size=len(data);m.mode=0o755;t.addfile(m,io.BytesIO(data))
        dest = self.home/'.local/opt/LinuxStudio'
        launcher = install.install_studio(archive,dest)
        from gi.repository import Gio
        app = Gio.DesktopAppInfo.new_from_filename(str(launcher))
        self.assertIsNotNone(app);self.assertTrue(app.launch([],None))
        end=time.monotonic()+3
        while not (self.home/'launched').exists() and time.monotonic()<end:time.sleep(.02)
        self.assertTrue((self.home/'launched').exists())
        self.assertTrue(os.access(dest/'run.sh',os.X_OK))
        with self.assertRaisesRegex(RuntimeError,'already has'):
            install.install_studio(archive,dest)

    def test_archive_traversal_and_escaping_symlinks_are_rejected(self):
        for name,target in (('../outside',''),('studio/escape','../../outside')):
            archive = self.home/'bad.tar.gz'
            with tarfile.open(archive, 'w:gz') as t:
                m=tarfile.TarInfo(name)
                if target:m.type=tarfile.SYMTYPE;m.linkname=target
                t.addfile(m)
            with self.assertRaises(tarfile.FilterError):install.install_studio(archive,self.home/'bad-install')
            self.assertFalse((self.home/'bad-install').exists())

    def test_linux_studio_prefers_tarball_even_if_appimage_is_first(self):
        archive={'filename':'studio.tar.gz'}
        self.assertIs(install.preferred(dict(product='linuxstudio',choices=[{'filename':'studio.AppImage'},archive])),archive)
        self.assertIsNone(install.preferred(dict(product='linuxstudio',choices=[{'filename':'studio.AppImage'}])))

    def test_make_default_reuses_existing_player_without_reinstall_or_network(self):
        dest=self.home/'.local/opt/XMusic';dest.mkdir(parents=True);(dest/'run.sh').touch()
        launcher=install.applications()/'xmusic.desktop';launcher.parent.mkdir(parents=True);launcher.touch()
        with patch.object(install,'set_music_defaults') as defaults,patch.object(install,'vendor_release',side_effect=AssertionError('network')):
            self.assertEqual(install.install('xmusic',make_default=True),launcher)
            defaults.assert_called_once();self.pin.assert_called_once_with(launcher)


class FavoriteTests(unittest.TestCase):
    def test_only_visible_launchers_of_confirmed_package_are_pinned(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,XDG_DATA_HOME=temp):
            apps=Path(temp)/'applications';apps.mkdir()
            for name,hidden in (('one',''),('two','NoDisplay=true\n')):
                (apps/(name+'.desktop')).write_text('[Desktop Entry]\nType=Application\nName='+name+'\nExec=true\n'+hidden)
            import sys;sys.path.insert(0,str(favorites.ROOT/'launcher'));import catalog
            local=Path(temp)/'favorites.json';local.write_text(json.dumps({'add':['old.desktop'],'hide':['one.desktop'],'future':'keep'}))
            with patch.object(catalog,'LOCAL',local),patch.object(favorites.subprocess,'run',side_effect=[
                subprocess.CompletedProcess([],0,'pkg\n',''),subprocess.CompletedProcess([],0,str(apps/'one.desktop')+'\n'+str(apps/'two.desktop')+'\n','')]):
                self.assertEqual(favorites.pin_package('extra/pkg'),[str(apps/'one.desktop')])
            self.assertEqual(json.loads(local.read_text()),{'add':['old.desktop','one.desktop'],'hide':[],'future':'keep'})
            with patch.object(favorites.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','not installed')),patch.object(favorites,'pin_desktop') as pin:
                self.assertEqual(favorites.pin_package('pkg'),[]);pin.assert_not_called()


if __name__=='__main__':unittest.main()
