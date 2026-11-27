import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from account_avatars import model

class GalleryTests(unittest.TestCase):
    def test_full_replacement_collection_and_original_animation(self):
        icons=model.icons();self.assertEqual(len(icons),301)
        self.assertEqual(len({i['id'] for i in icons}),301)
        self.assertEqual(sum(i['animated'] for i in icons),1)
        self.assertEqual(model.verify('original').read_bytes(),(Path(__file__).resolve().parents[1]/'theme/assets/account.gif').read_bytes())
        from PIL import Image
        for icon in icons:
            path=model.verify(icon['id'])
            with Image.open(path) as image:
                image.load();self.assertGreaterEqual(min(image.size),80,icon['id'])
                if icon['animated']:self.assertGreater(image.n_frames,1)

    def test_unknown_picture_cannot_select_an_arbitrary_file(self):
        for key in ('../../etc/shadow','',None):
            with self.assertRaises(ValueError):model.verify(key)

    def test_catalog_hash_failure_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'icons.json').write_text(json.dumps({'icons':[model.selected('fedora')]}))
            (root/'fedora.png').write_bytes(b'changed')
            with patch.object(model,'ASSETS',root),self.assertRaises(ValueError):model.verify('fedora')

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.account=SimpleNamespace(pw_name='demo',pw_uid=os.getuid(),pw_gid=os.getgid(),pw_dir='/home/demo')
        self.home=self.root/'home/demo';self.theme=self.home/'.config/hypr/theme';self.theme.mkdir(parents=True)
        self.state=self.theme/'state.json';self.state.write_text(json.dumps({'avatar':'assets/account.gif','design':'integra','mode':'light','launcher_background':'keep.png'}))
        (self.home/'.face').write_bytes(b'old-face');(self.home/'.face.icon').write_bytes(b'old-icon')

    def test_self_service_preserves_theme_and_gif_bytes(self):
        result=model.update(self.account,'original',root=self.root)
        self.assertTrue(result['ok']);self.assertTrue(result['animated'])
        data=model.verify('original').read_bytes()
        for name in ('.face','.face.icon','.config/hypr/theme/state/account-avatar.gif'):
            self.assertEqual((self.home/name).read_bytes(),data)
        saved=json.loads(self.state.read_text());self.assertEqual(saved['avatar'],'state/account-avatar.gif')
        self.assertEqual(saved['design'],'integra');self.assertEqual(saved['mode'],'light');self.assertEqual(saved['launcher_background'],'keep.png')
        self.assertFalse((self.root/'var').exists())

    def test_switching_back_to_png_preserves_exact_pixels(self):
        model.update(self.account,'original',root=self.root);model.update(self.account,'red-panda',root=self.root)
        self.assertEqual((self.home/'.face').read_bytes(),model.verify('red-panda').read_bytes())
        self.assertEqual(json.loads(self.state.read_text())['avatar'],'state/account-avatar.png')

    def test_other_account_requires_authentication(self):
        self.account.pw_uid+=1
        with self.assertRaises(PermissionError):model.update(self.account,'fedora',root=self.root)
        self.assertEqual((self.home/'.face').read_bytes(),b'old-face')

    def test_authenticated_update_preserves_accounts_service_options(self):
        config=self.root/'var/lib/AccountsService/users/demo';config.parent.mkdir(parents=True)
        config.write_text('[User]\nLanguage=en_US.UTF-8\nXSession=hyprland\nIcon=/old.png\n')
        result=model.update(self.account,'flat-cap',root=self.root,administrator=True)
        self.assertTrue(result['ok']);self.assertIn('Language=en_US.UTF-8',config.read_text());self.assertIn('XSession=hyprland',config.read_text())
        self.assertIn('Icon=/var/lib/AccountsService/icons/demo',config.read_text())
        self.assertEqual(config.stat().st_mode&0o777,0o600)
        self.assertEqual((self.root/'var/lib/AccountsService/icons/demo').read_bytes(),model.verify('flat-cap').read_bytes())

    def test_invalid_theme_leaves_pictures_untouched(self):
        self.state.write_text('{broken')
        with self.assertRaises(ValueError):model.update(self.account,'fedora',root=self.root)
        self.assertEqual((self.home/'.face').read_bytes(),b'old-face')

    def test_symlink_destinations_are_rejected_without_touching_target(self):
        target=self.root/'outside';target.write_bytes(b'protected')
        (self.home/'.face').unlink();(self.home/'.face').symlink_to(target)
        with self.assertRaises(ValueError):model.update(self.account,'fedora',root=self.root)
        self.assertEqual(target.read_bytes(),b'protected')

    def test_partial_write_rolls_back_existing_picture_and_state(self):
        state=self.state.read_bytes();real=model.atomic;count=0
        def fail_once(*args,**kwargs):
            nonlocal count
            count+=1
            if count==3:raise OSError('Synthetic disk error')
            return real(*args,**kwargs)
        with patch.object(model,'atomic',side_effect=fail_once),self.assertRaises(OSError):
            model.update(self.account,'fedora',root=self.root)
        self.assertEqual((self.home/'.face').read_bytes(),b'old-face');self.assertEqual((self.home/'.face.icon').read_bytes(),b'old-icon')
        self.assertEqual(self.state.read_bytes(),state);self.assertFalse((self.theme/'state/account-avatar.png').exists())

if __name__=='__main__':unittest.main()
