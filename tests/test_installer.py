"""Portable installer tests use disposable homes, never the live desktop."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'installer'))
import install
import dependencies


class DependencyEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-dependency-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.perl_bin = self.root / 'core_perl'
        for mock in (
            patch.dict(os.environ, {'PATH': str(self.bin)}),
            patch.object(dependencies.command_paths, 'PERL_SCRIPT_DIRS', (str(self.perl_bin),)),
            patch.object(dependencies.command_paths, 'SYSTEM_TOOL_DIRS', ()),
            patch.object(dependencies, 'COMMANDS', ['pod2man']),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def write_tool(self, directory, output, name='pod2man'):
        directory.mkdir(exist_ok=True)
        tool = directory / name
        tool.write_text('#!/bin/sh\nprintf "%s\\n" "' + output + '"\n')
        tool.chmod(0o755)

    def check_commands(self):
        # Leave real PATH lookup intact; unrelated GUI/library probes are outside
        # this regression. No package manager or installed profile is touched.
        with patch.object(dependencies.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, '', '')):
            return [error for error in dependencies.check() if error.startswith('Missing command:')]

    def test_new_perl_install_is_found_without_a_new_shell_and_reaches_builds(self):
        self.assertEqual(self.check_commands(), ['Missing command: pod2man'])
        self.write_tool(self.perl_bin, 'installed Perl tool')
        self.assertEqual(self.check_commands(), [])
        self.assertEqual(subprocess.check_output(['pod2man'], text=True), 'installed Perl tool\n')
        # The same environment is reused by initial, post-install and update checks.
        self.assertEqual(self.check_commands(), [])
        self.assertEqual(os.environ['PATH'].split(os.pathsep).count(str(self.perl_bin)), 1)

    def test_existing_caller_tool_keeps_priority(self):
        self.write_tool(self.bin, 'caller tool')
        self.write_tool(self.perl_bin, 'system tool')
        self.assertEqual(self.check_commands(), [])
        self.assertEqual(subprocess.check_output(['pod2man'], text=True), 'caller tool\n')

    def test_existing_directory_does_not_hide_a_missing_or_unusable_tool(self):
        self.perl_bin.mkdir()
        self.assertEqual(self.check_commands(), ['Missing command: pod2man'])
        (self.perl_bin / 'pod2man').write_text('not executable')
        self.assertEqual(self.check_commands(), ['Missing command: pod2man'])

    def test_debian_system_tools_are_found_and_available_to_child_processes(self):
        commands = ['dmidecode', 'fsck.fat', 'losetup', 'modinfo']
        sbin = self.root/'sbin'
        with patch.object(dependencies, 'COMMANDS', commands), \
             patch.object(dependencies.command_paths, 'SYSTEM_TOOL_DIRS', (str(sbin),)):
            self.assertEqual(self.check_commands(), ['Missing command: '+name for name in commands])
            for name in commands:
                self.write_tool(sbin, 'installed '+name, name)
            self.assertEqual(self.check_commands(), [])
            for name in commands:
                self.assertEqual(subprocess.check_output([name], text=True), 'installed '+name+'\n')
            self.assertEqual(self.check_commands(), [])
            self.assertEqual(os.environ['PATH'].split(os.pathsep).count(str(sbin)), 1)

    def test_system_tools_preserve_existing_path_priority(self):
        sbin = self.root/'sbin'
        self.write_tool(self.bin, 'caller tool', 'modinfo')
        self.write_tool(sbin, 'system tool', 'modinfo')
        with patch.object(dependencies, 'COMMANDS', ['modinfo']), \
             patch.object(dependencies.command_paths, 'SYSTEM_TOOL_DIRS', (str(sbin),)):
            self.assertEqual(self.check_commands(), [])
            self.assertEqual(subprocess.check_output(['modinfo'], text=True), 'caller tool\n')

    def test_system_directories_do_not_hide_genuinely_missing_tools(self):
        sbin = self.root/'sbin'
        sbin.mkdir()
        (sbin/'modinfo').write_text('not executable')
        with patch.object(dependencies, 'COMMANDS', ['modinfo', 'dmidecode']), \
             patch.object(dependencies.command_paths, 'SYSTEM_TOOL_DIRS', (str(sbin),)):
            self.assertEqual(self.check_commands(), ['Missing command: modinfo', 'Missing command: dmidecode'])


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='xetal-install-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.home=self.root/'recipient';self.home.mkdir()
        self.stage=self.root/'prepared';self.target=self.home/'.config/hypr';self.target.parent.mkdir()
        self.state=self.home/'.local/state/xetal-hyprland'
        self.monitors=[{'name':'HDMI-A-1','width':1920,'height':1080,'refreshRate':59.94,'x':0,'y':0,'scale':1,'transform':0},
                       {'name':'eDP-1','width':2560,'height':1600,'refreshRate':165.0,'x':1920,'y':0,'scale':1.25,'transform':0}]

    def render(self,monitors=None,**kwargs):
        return install.render(self.stage,self.home,self.monitors if monitors is None else monitors,**kwargs)

    def test_other_home_connectors_scaling_and_wallpaper(self):
        self.render()
        text=(self.stage/'control_center/displays.conf').read_text()
        self.assertIn('HDMI-A-1,1920x1080@59.940,0x0,1',text)
        self.assertIn('eDP-1,2560x1600@165.000,1920x0,1.25',text)
        self.assertNotIn('DP-5',text)
        state=json.loads((self.stage/'wallpaper/selection.json').read_text())
        self.assertEqual(set(state),{'HDMI-A-1','eDP-1'})
        self.assertTrue(state['eDP-1']['path'].startswith(str(self.target)))
        self.assertEqual(state['eDP-1']['path'],state['eDP-1']['original'])
        self.assertTrue(state['HDMI-A-1']['path'].endswith('/hollowgrove/forgotten-arches.png'))
        self.assertTrue(state['eDP-1']['path'].endswith('/hollowgrove/hollow-grove.png'))
        for p in self.stage.rglob('*'):
            if not p.is_file():continue
            try:text=p.read_text()
            except UnicodeDecodeError:continue
            self.assertNotIn('@HOME@',text,str(p));self.assertNotIn('@HYPR@',text,str(p))
            self.assertNotIn('/home/xetal',text,str(p))

    def test_offline_install_has_wildcard_wallpaper_and_auto_monitor_fallback(self):
        self.render(monitors=[])
        self.assertIn('monitor=,preferred,auto,auto',(self.stage/'hyprland.conf').read_text())
        self.assertRegex((self.stage/'wallpaper/hyprpaper.conf').read_text(),r'monitor =\s*\n')
        self.assertEqual(json.loads((self.stage/'wallpaper/selection.json').read_text()),{})

    def test_fresh_hollow_grove_and_effect_defaults_are_portable_and_ready(self):
        self.render()
        state=json.loads((self.stage/'theme/state.json').read_text())
        self.assertEqual((state['design'],state['mode'],state['bar_variant']),('hollowgrove','dark','full'))
        self.assertIn('XetalHollowgroveDark',(self.stage/'theme/current.colors').read_text())
        self.assertIn('hollowgrove',(self.stage/'waybar/style.css').read_text())
        self.assertIn(str(self.target/'theme'),(self.stage/'waybar/style.css').read_text())
        self.assertNotIn(str(self.stage),(self.stage/'waybar/style.css').read_text())
        values=json.loads((self.stage/'effects/cube/settings.json').read_text())
        self.assertEqual((values['wall_opacity'],values['zoom'],values['sensitivity'],values['duration']),(.65,.64,.35,200))
        self.assertEqual((values['windows_3d'],values['min_cube_size'],values['window_space'],values['window_depth']),(True,60,5,.15))
        for side,wallpaper in [('top_image','lantern-crossing.png'),('bottom_image','gilded-hollow.png')]:
            self.assertEqual((self.stage/'effects/cube'/values[side]).read_bytes(),
                             (self.stage/'wallpaper/gildedhollow'/wallpaper).read_bytes())
        self.assertTrue((self.stage/'effects/cube'/values['sky_image']).is_file())
        # Preparing native textures must succeed in a recipient's new profile.
        probe='''from effects.cube import model
from effects.wobbly import model as wobbly
from effects.minimize import model as minimize
values,_=model.load();assert values==model.DEFAULTS
model.prepare_images(values)
w,_=wobbly.load();assert w==wobbly.DEFAULTS
assert w['enabled'] and w['friction']==3 and w['spring_k']==3
m,_=minimize.load();assert m==minimize.DEFAULTS
assert m['auto_hide'] and m['hide_delay']==1200 and m['dock_duration']==320
assert m['dock_zoom']==125 and m['proximity']==12 and m['hide_animation']=='burn'
assert m['fire_indicator']
'''
        subprocess.run([sys.executable,'-c',probe],env=dict(os.environ,PYTHONPATH=str(self.stage)),check=True,capture_output=True)

    def test_fresh_favorites_include_my_computer_and_bundled_apps(self):
        self.render()
        expected = {'add': ['xetal-files-computer.desktop', 'kitty.desktop', 'xetal-calculator.desktop'], 'hide': []}
        self.assertEqual(json.loads((self.stage/'launcher/favorites.json').read_text()), expected)
        self.assertEqual(json.loads((install.PAYLOAD/'launcher/favorites.json').read_text()), expected)
        self.assertEqual(json.loads((self.stage/'launcher/shortcuts.json').read_text()),
                         {'version': 1, 'overrides': {'xetal-calculator.desktop': {'floating': True}}, 'copies': {}})
        computer = (self.stage/'desktop/data/applications/xetal-files-computer.desktop').read_text()
        self.assertIn('Name=My Computer', computer)
        self.assertIn(f'Exec={self.target}/scripts/files.sh --this-pc', computer)
        self.assertIn('Icon=computer', computer)
        self.assertTrue((self.stage/'file_manager/computer.svg').is_file())
        self.assertIn('inode/directory=xetal-files.desktop;', (self.stage/'desktop/config/mimeapps.list').read_text())
        self.assertIn('$fileManager = ~/.config/hypr/scripts/file-manager.sh', (self.stage/'hyprland.conf').read_text())
        self.assertTrue((self.stage/'control_panel/default_apps.py').is_file())
        self.assertIn('"defaultAppsTab"', (self.stage/'control_panel/tools.json').read_text())
        self.assertIn('bind = $mainMod, E, exec, $fileManager', (self.stage/'keybindings.conf').read_text())
        self.assertIn(f'Exec={self.target}/scripts/files.sh --service',
                      (self.stage/'desktop/data/dbus-1/services/org.freedesktop.FileManager1.service').read_text())
        desktop = (self.stage/'desktop/data/applications/xetal-calculator.desktop').read_text()
        self.assertIn(f'Exec=python3 {self.target}/calculator/app.py', desktop)
        self.assertIn('Icon=accessories-calculator', desktop)
        self.assertTrue((self.stage/'calculator/app.py').is_file())
        self.assertTrue((self.stage/'calculator/programmer_calculator/assets/calculator.svg').is_file())
        self.assertIn('from PyQt6.QtWidgets', (self.stage/'calculator/programmer_calculator/window.py').read_text())

    def test_used_checkout_cannot_seed_personal_launcher_data(self):
        source = self.root/'source'
        shutil.copytree(install.PAYLOAD, source, ignore=shutil.ignore_patterns('__pycache__', '.build', 'build'))
        for name in install.LAUNCHER_DEFAULTS:
            (source/'launcher'/name).write_text('{"developer_only": true}')
        private = ('launcher/favorite-layout.json', 'launcher/floating-sizes.json',
                   'launcher/icons/private.png', 'calculator/state/preferences.ini',
                   'file_manager/state/settings.ini', 'runtime/window_memory/state/windows.json')
        for name in private:
            path = source/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('PRIVATE DEVELOPER DATA')
        kde = self.home/'.config/kactivitymanagerd-statsrc'
        kde.write_text('[Favorites-instance-1-global]\nordering=applications:recipient.desktop\n')
        before = kde.read_bytes()
        with patch.object(install, 'PAYLOAD', source): self.render()
        for name in private: self.assertFalse((self.stage/name).exists(), name)
        for name, expected in install.LAUNCHER_DEFAULTS.items():
            self.assertEqual(json.loads((self.stage/'launcher'/name).read_text()), expected)
        self.assertEqual(kde.read_bytes(), before)

    def test_places_use_recipient_folders_without_importing_private_bookmarks(self):
        (self.home/'Desktop').mkdir()
        (self.home/'Mes documents').mkdir()
        (self.home/'.config/user-dirs.dirs').write_text(
            'XDG_DOCUMENTS_DIR="$HOME/Mes documents"\nXDG_DOWNLOAD_DIR="$HOME"\n'
            'XDG_MUSIC_DIR="/missing/music"\nXDG_VIDEOS_DIR="$(touch '+str(self.home/'unexpected')+')"\n')
        personal=self.home/'.local/share/user-places.xbel';personal.parent.mkdir(parents=True)
        personal.write_text('<xbel><bookmark href="file:///home/developer/private"><title>Author bookmark</title></bookmark></xbel>')
        self.render()
        places=ET.parse(self.stage/'dolphin/data/user-places.xbel').getroot()
        self.assertEqual({item.get('href') for item in places.findall('bookmark')},
                         {self.home.as_uri(),(self.home/'Desktop').as_uri(),(self.home/'Mes documents').as_uri(),'trash:/','remote:/'})
        self.assertFalse((self.home/'unexpected').exists())
        self.assertIn('Author bookmark',personal.read_text())

    def test_private_dolphin_data_is_excluded_even_from_a_used_source_checkout(self):
        source=self.root/'source'
        shutil.copytree(install.PAYLOAD,source,ignore=shutil.ignore_patterns('__pycache__','.build','build'))
        private=('dolphin/data/user-places.xbel','dolphin/data/user-places.xbel.bak',
                 'dolphin/data/recently-used.xbel','dolphin/data/Trash/files/private.txt',
                 'dolphin/data/konsole/Personal.profile','dolphin/config/browser/private.json')
        for name in private:
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('PRIVATE DEVELOPER DATA')
        with patch.object(install,'PAYLOAD',source):self.render()
        for name in private:
            path=self.stage/name
            if path.exists():self.assertNotIn('PRIVATE DEVELOPER DATA',path.read_text(),name)
        self.assertTrue((self.stage/'dolphin/data/kio/servicemenus/hyprland-wallpaper.desktop').is_file())
        self.assertTrue((self.stage/'dolphin/data/konsole/Xetal-Dolphin.profile').is_file())

    def test_embedded_terminal_follows_kitty_colors_when_dolphin_opens(self):
        import configparser
        self.render()
        colors=self.stage/'theme/kitty-colors.conf'
        for background,foreground in (('#10191f','#e5f1f8'),('#ffffff','#1f3043'),('#000000','#ffffff')):
            text=colors.read_text()
            text=re.sub(r'^background .*$', 'background '+background, text, flags=re.M)
            text=re.sub(r'^foreground .*$', 'foreground '+foreground, text, flags=re.M)
            colors.write_text(text)
            install.dolphin_profile.prepare_terminal(self.stage)
            scheme=configparser.ConfigParser()
            scheme.read(self.stage/'dolphin/data/konsole/Xetal-Dolphin.colorscheme')
            for group,expected in (('Background',background),('Foreground',foreground)):
                actual='#'+''.join(f'{int(channel):02x}' for channel in scheme[group]['Color'].split(','))
                self.assertEqual(actual,expected)
            for i in range(8):
                for suffix in ('','Intense','Faint'):self.assertIn('Color',scheme['Color'+str(i)+suffix])
        self.assertIn('DefaultProfile=Xetal-Dolphin.profile',(self.stage/'dolphin/config/dolphinrc').read_text())
        self.assertIn('TerminalApplication=kitty --config '+str(self.target/'kitty.conf'),
                      (self.stage/'dolphin/config/kdeglobals').read_text())

    def test_dolphin_first_install_selects_private_dark_scheme_without_changing_kde(self):
        import configparser
        shared = self.home/'.config/kdeglobals'
        shared.write_text('[General]\nColorScheme=BreezeLight\n')
        self.render()
        config = configparser.ConfigParser(); config.read(self.stage/'dolphin/config/dolphinrc')
        self.assertEqual(config['UiSettings']['ColorScheme'], 'HyperFusion')
        scheme = configparser.ConfigParser()
        scheme.read(self.stage/'dolphin/data/color-schemes/HyperFusion.colors')
        self.assertEqual(scheme['General']['Name'], 'HyperFusion')
        self.assertTrue(all(int(value) < 80 for value in scheme['Colors:Window']['BackgroundNormal'].split(',')))
        self.assertEqual(shared.read_text(), '[General]\nColorScheme=BreezeLight\n')
        launcher = (self.stage/'desktop/data/applications/org.kde.dolphin.desktop').read_text()
        self.assertIn('Exec='+str(self.target/'scripts/dolphin.sh')+' %U', launcher)
        self.assertIn('DBusActivatable=false', launcher)

    def test_dolphin_scheme_refresh_keeps_an_explicit_user_selection(self):
        self.render()
        config = self.stage/'dolphin/config/dolphinrc'
        config.write_text(config.read_text().replace('ColorScheme=HyperFusion', 'ColorScheme=MyFavorite'))
        before = config.read_bytes()
        install.dolphin_profile.prepare_colors(self.stage)
        self.assertEqual(config.read_bytes(), before)

    def test_existing_dolphin_profiles_receive_missing_defaults_without_losing_choices(self):
        self.render()
        config=self.stage/'dolphin/config/dolphinrc'
        config.write_text('MenuBar=Disabled\n[General]\nVersion=202\n')
        globals=self.stage/'dolphin/config/kdeglobals'
        globals.write_text('[General]\nColorScheme=Personal\n[Icons]\nTheme=Personal\n')
        install.dolphin_profile.prepare_terminal(self.stage)
        self.assertIn('DefaultProfile=Xetal-Dolphin.profile',config.read_text())
        self.assertIn('TerminalApplication=kitty --config '+str(self.stage/'kitty.conf'),globals.read_text())
        config.write_text(config.read_text().replace('Xetal-Dolphin.profile','MyTerminal.profile'))
        globals.write_text(globals.read_text().replace('TerminalApplication=kitty --config '+str(self.stage/'kitty.conf'),
                                                     'TerminalApplication=alacritty'))
        before=(config.read_bytes(),globals.read_bytes())
        install.dolphin_profile.prepare_terminal(self.stage)
        self.assertEqual(before,(config.read_bytes(),globals.read_bytes()))

    def test_kvm_runtime_payload_cannot_be_accidentally_shipped(self):
        source=self.root/'payload';(source/'kvm').mkdir(parents=True)
        for name,body in [('runtime.tar.xz',b'archive'),('OVMF_CODE.fd',b'firmware'),('swtpm',b'\x7fELFfixture')]:
            file=source/'kvm'/name;file.write_bytes(body)
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError,'must be downloaded'):
                install.check_kvm_payload(source)
            file.unlink()
        self.render()
        self.assertFalse((self.stage/'kvm/bundled').exists())
        self.assertTrue((self.stage/'kvm/catalog.json').is_file())
        guest = self.stage/'kvm/guest/vmstealth75.bat'
        self.assertTrue(guest.is_file(), 'Guest script must ship independently of the optional kernel module')
        self.assertIn('HOST_LOGIN=YOUR_LINUX_USER@YOUR_LINUX_HOST', guest.read_text())

    def test_bar_options_are_built_and_use_recipient_profile(self):
        self.render()
        bar=json.loads((self.stage/'waybar/config.json').read_text())
        self.assertIn('cffi/bar-options',bar['modules-left'])
        self.assertEqual(bar['cffi/bar-options']['module_path'],str(self.target/'waybar/options/options.so'))
        self.assertEqual(json.loads((self.stage/'waybar/options.json').read_text()),{'version':1,'hidden':[]})
        self.assertTrue((self.stage/'waybar/options/build.sh').is_file())

    def test_update_registration_tracks_delivered_defaults_and_bar_entry(self):
        self.render(); install.register_updates(self.stage)
        inventory=json.loads((self.stage/'.xetal-update.json').read_text())
        self.assertEqual(len(inventory['revision']),40)
        self.assertIn('launcher/favorites.json',inventory['files'])
        self.assertIn('kvm/guest/vmstealth75.bat',inventory['files'])
        self.assertIn('text',inventory['files']['launcher/favorites.json'])
        self.assertNotIn('theme/qt6/libxetal.so',inventory['files'])
        bar=json.loads((self.stage/'waybar/config.json').read_text())
        self.assertEqual(bar['modules-left'][bar['modules-left'].index('custom/keys')+1],'custom/updates')
        self.assertIn('updates.css',(self.stage/'waybar/style.css').read_text())
        self.assertIn('updates/service.py" --activate',(self.stage/'scripts/session.sh').read_text())

    def test_image_viewer_and_image_associations_stay_in_recipient_profile(self):
        self.render()
        desktop=(self.stage/'desktop/data/applications/xetal-image-viewer.desktop').read_text()
        self.assertIn(f'Exec={self.target}/scripts/image-viewer.sh -- %F',desktop)
        associations=(self.stage/'desktop/config/mimeapps.list').read_text()
        for kind in ('png','jpeg','gif','webp','tiff','avif','svg+xml'):
            self.assertIn(f'image/{kind}=xetal-image-viewer.desktop;',associations)
        self.assertIn('inode/directory=',associations)
        self.assertFalse((self.home/'.config/mimeapps.list').exists())
        self.assertTrue((self.stage/'image_viewer/window_size.py').is_file())

    def test_explicit_original_profile_retains_original_display_layout(self):
        self.render(profile='original')
        self.assertEqual((self.stage/'control_center/displays.conf').read_bytes(),(REPO/'profiles/xetal-original/displays.conf').read_bytes())
        self.assertEqual(set(json.loads((self.stage/'wallpaper/selection.json').read_text())),{'DP-4','DP-5','DP-6'})

    def test_disabled_startup_keeps_super_d_shortcut(self):
        self.render(startup=False)
        self.assertNotIn('exec-once = ~/.config/hypr/scripts/startup-scene.sh --login',(self.stage/'hyprland.conf').read_text())
        self.assertIn('startup-scene.sh --toggle',(self.stage/'keybindings.conf').read_text())

    def test_backup_install_and_restore_keep_unrelated_desktops_and_latest_changes(self):
        self.target.mkdir();(self.target/'personal.conf').write_text('before')
        kde=self.home/'.config/kdeglobals';kde.write_text('KDE unchanged')
        self.render();expected=install.tree_digest(self.target)
        backup=install.activate(self.stage,self.target,self.state,expected)
        self.assertEqual((backup/'hypr/personal.conf').read_text(),'before')
        (self.target/'my-later-change').write_text('keep this too')
        replaced=install.restore(backup,self.target,self.state)
        self.assertEqual((self.target/'personal.conf').read_text(),'before')
        self.assertEqual((replaced/'my-later-change').read_text(),'keep this too')
        self.assertEqual(kde.read_text(),'KDE unchanged')

    def test_changed_config_is_not_overwritten(self):
        self.target.mkdir();(self.target/'personal.conf').write_text('before');expected=install.tree_digest(self.target)
        self.render();(self.target/'personal.conf').write_text('concurrent edit')
        with self.assertRaisesRegex(RuntimeError,'changed'):install.activate(self.stage,self.target,self.state,expected)
        self.assertEqual((self.target/'personal.conf').read_text(),'concurrent edit')

    def test_final_rename_failure_restores_previous_profile(self):
        self.target.mkdir();(self.target/'personal.conf').write_text('before');expected=install.tree_digest(self.target)
        self.render();real=os.replace
        def replace(source,destination):
            if Path(source)==self.stage:raise OSError('simulated disk failure')
            return real(source,destination)
        with patch.object(install.os,'replace',side_effect=replace):
            with self.assertRaisesRegex(OSError,'disk failure'):install.activate(self.stage,self.target,self.state,expected)
        self.assertEqual((self.target/'personal.conf').read_text(),'before')

    def test_symlinked_old_profile_is_preserved_without_modifying_its_target(self):
        old=self.root/'old-dotfiles';old.mkdir();(old/'personal.conf').write_text('original')
        self.target.symlink_to(old,target_is_directory=True);expected=install.tree_digest(self.target)
        self.render();backup=install.activate(self.stage,self.target,self.state,expected)
        self.assertFalse(self.target.is_symlink());self.assertTrue((backup/'hypr').is_symlink())
        self.assertEqual((old/'personal.conf').read_text(),'original')
        install.restore(backup,self.target,self.state)
        self.assertTrue(self.target.is_symlink());self.assertEqual(self.target.resolve(),old)

    def test_first_install_restore_retains_new_profile_and_removes_only_install_target(self):
        self.render();backup=install.activate(self.stage,self.target,self.state,'missing')
        replaced=install.restore(backup,self.target,self.state)
        self.assertFalse(self.target.exists());self.assertTrue((replaced/'hyprland.conf').is_file())

    def test_foreign_restore_is_rejected(self):
        self.render();backup=install.activate(self.stage,self.target,self.state,'missing')
        with self.assertRaisesRegex(RuntimeError,'does not belong'):install.restore(backup,self.home/'elsewhere',self.state)
        self.assertTrue(self.target.exists())

    def test_unsafe_home_path_is_rejected_before_copying(self):
        with self.assertRaisesRegex(ValueError,'standard home'):install.render(self.stage,self.root/'bad;home',[])
        self.assertFalse(self.stage.exists())

    def test_repository_excludes_private_profiles_caches_and_prebuilt_native_code(self):
        forbidden={'mozilla','recently-used.xbel','places.sqlite','cookies.sqlite','.parentlock','user-places.xbel'}
        for p in install.PAYLOAD.rglob('*'):
            if '__pycache__' in p.parts:continue
            if any(part in ('.build','build') for part in p.parts) or p.suffix in {'.so','.o','.a'}:
                result=install.subprocess.run(['git','check-ignore','--quiet',str(p)],cwd=REPO)
                self.assertEqual(result.returncode,0,str(p))
                continue
            self.assertFalse(forbidden.intersection(p.parts),str(p))
            self.assertNotIn(p.suffix,{'.so','.o','.a'},str(p))

    def test_grub_design_assets_ship_without_the_machine_specific_installer(self):
        self.assertNotIn('grub', install.payload_ignored(install.PAYLOAD, ['grub']))
        ignored = install.payload_ignored(install.PAYLOAD/'grub', ['hyper-fusion', 'apply-this-machine.py'])
        self.assertIn('apply-this-machine.py', ignored)
        self.assertNotIn('hyper-fusion', ignored)

    def test_native_effect_failure_prevents_an_incomplete_desktop_install(self):
        def command(args,**kwargs):
            optional=any(str(args[-1]).endswith('/effects/'+name+'/build.py') for name in ('burn','cube'))
            return install.subprocess.CompletedProcess(args,1 if optional else 0,stdout='',stderr='Unsupported compositor ABI' if optional else '')
        with patch.object(install,'run_build') as builds, \
             patch.object(install.subprocess,'run',side_effect=command) as run:
            with self.assertRaisesRegex(RuntimeError,'Burn could not be built'):
                install.build(self.stage)
        self.assertEqual(run.call_count,1)
        self.assertTrue(any(str(call.args[0][-1]).endswith('/icon_themes/prepare.py') for call in builds.call_args_list))
        self.assertTrue(any(str(call.args[0][-1]).endswith('/runtime/notices/build.py') for call in builds.call_args_list))
        self.assertTrue(any(str(call.args[0][-1]).endswith('/runtime/cursor_probe/build.py') for call in builds.call_args_list))
        self.assertTrue(any(str(call.args[0][-1]).endswith('/runtime/window_memory/build.py') for call in builds.call_args_list))
        self.assertTrue(any(str(call.args[0][-1]).endswith('/cursors/build.py') for call in builds.call_args_list))

    def test_invalid_config_stops_before_compilation_in_both_install_modes(self):
        self.target.mkdir()
        (self.target/'keep.txt').write_text('existing desktop')
        original=install.tree_digest(self.target)
        def invalid_profile(stage,*args):
            stage.mkdir(parents=True)
            (stage/'hyprland.conf').write_text('general:setting_does_not_exist = 1\n')
        for mode in ([],['--prepare',str(self.stage)]):
            with self.subTest(mode=mode), \
                 patch.object(sys,'argv',['install.py','--yes','--skip-packages',*mode]), \
                 patch.object(Path,'home',return_value=self.home), \
                 patch.object(dependencies,'check',return_value=[]), \
                 patch.object(install,'connected_monitors',return_value=[]), \
                 patch.object(install,'render',side_effect=invalid_profile), \
                 patch.object(install,'register_updates'), \
                 patch.object(install,'build') as build:
                with self.assertRaisesRegex(RuntimeError,'Full Hyprland validation failed'):
                    install.main()
                build.assert_not_called()
                self.assertEqual(install.tree_digest(self.target),original)

    def test_every_shipped_wallpaper_matches_manifest(self):
        import hashlib
        manifest=json.loads((REPO/'assets-manifest.json').read_text())
        for name,digest in manifest.items():self.assertEqual(hashlib.sha256((REPO/name).read_bytes()).hexdigest(),digest)


if __name__=='__main__':unittest.main()
