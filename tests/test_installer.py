"""Portable installer tests use disposable homes, never the live desktop."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'installer'))
import install
import dependencies


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
            self.assertFalse(forbidden.intersection(p.parts),str(p))
            self.assertNotIn(p.suffix,{'.so','.o','.a'},str(p))

    def test_optional_native_effect_failure_keeps_the_desktop_installable(self):
        def command(args,**kwargs):
            optional=any(str(args[-1]).endswith('/effects/'+name+'/build.py') for name in ('burn','cube'))
            return install.subprocess.CompletedProcess(args,1 if optional else 0,stdout='',stderr='Unsupported compositor ABI' if optional else '')
        with patch.object(install.subprocess,'run',side_effect=command) as run,patch('builtins.print') as message:
            install.build(self.stage)
        self.assertEqual(run.call_count,7)
        self.assertTrue(any('Optional Burn effect unavailable' in str(call) for call in message.call_args_list))
        self.assertTrue(any('Optional Desktop Cube & 3D Windows effect unavailable' in str(call) for call in message.call_args_list))

    def test_every_shipped_wallpaper_matches_manifest(self):
        import hashlib
        manifest=json.loads((REPO/'assets-manifest.json').read_text())
        for name,digest in manifest.items():self.assertEqual(hashlib.sha256((REPO/name).read_bytes()).hexdigest(),digest)


if __name__=='__main__':unittest.main()
