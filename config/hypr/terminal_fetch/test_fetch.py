import copy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import model


class FetchTests(unittest.TestCase):
    def test_choice_round_trip_and_invalid_fields(self):
        value=copy.deepcopy(model.DEFAULTS);value.update(logo='fusion',fields=['os','shell'],enabled=False)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';model.save(value,path);self.assertEqual(model.load(path),value)
        for change in ({'logo':'alien'},{'enabled':'yes'},{'fields':['os','os']},{'fields':['command']}):
            with self.assertRaises(ValueError):model.validate({**value,**change})
    def test_plain_html_and_narrow_terminal_rendering(self):
        data={key:'A < B & C' for key in model.FIELDS}
        plain=model.render(model.DEFAULTS,data,colored=False,width=60)
        self.assertNotIn('\x1b',plain);self.assertTrue(all(len(line)<=58 for line in plain.splitlines()))
        self.assertNotIn('██',plain)
        markup=model.render(model.DEFAULTS,data,markup=True);self.assertIn('A &lt; B &amp; C',markup)
        self.assertEqual(model.clean('\x1b[31mred\x1b[0m\x00'),'red')
    def test_disabled_welcome_does_not_probe_system(self):
        with patch.object(model,'load',return_value={**model.DEFAULTS,'enabled':False}),patch.object(model.sys,'argv',['fetch']),patch.object(model,'system_data') as probe:
            self.assertEqual(model.main(),0);probe.assert_not_called()

    def test_existing_settings_and_managed_image_paths(self):
        legacy = {key: value for key, value in model.DEFAULTS.items() if key != 'logo_image'}
        self.assertEqual(model.validate(legacy), model.DEFAULTS)
        name = 'c' * 64 + '.png'
        settings = model.validate({**legacy, 'logo': 'custom', 'logo_image': name})
        self.assertEqual(model.logo_path(settings), model.ROOT / 'logos' / name)
        for name in ('', '../image.png', '/tmp/image.png', 'file:///tmp/image.png', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                model.validate({**legacy, 'logo': 'custom', 'logo_image': name})

    def test_custom_image_is_sent_to_kitty_only_when_supported(self):
        import artwork
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'logos').mkdir(); name = 'd' * 64 + '.png'
            path = root / 'logos' / name; path.write_bytes(b'preview image data')
            settings = {**model.DEFAULTS, 'logo': 'custom', 'logo_image': name}
            for term, width, multiplexed, plain, graphical in (
                    ('xterm-kitty', 110, False, False, True),
                    ('xterm-256color', 110, False, False, False),
                    ('xterm-kitty', 60, False, False, False),
                    ('xterm-kitty', 110, True, False, False),
                    ('xterm-kitty', 110, False, True, False)):
                output = io.StringIO(); output.isatty = lambda: True
                with self.subTest(term=term, width=width, multiplexed=multiplexed, plain=plain), \
                        patch.object(model, 'ROOT', root), patch.object(model, 'load', return_value=settings), \
                        patch.object(model, 'system_data', return_value={'os': 'Test OS'}), \
                        patch.object(model.sys, 'stdout', output), \
                        patch.object(model.sys, 'argv', ['fetch', *(['--plain'] if plain else [])]), \
                        patch.object(model.shutil, 'get_terminal_size', return_value=os.terminal_size((width, 24))), \
                        patch.dict(os.environ, {'TERM': term, 'TMUX': 'test' if multiplexed else '', 'STY': ''}), \
                        patch.object(artwork, 'kitty_image', wraps=artwork.kitty_image) as graphic:
                    self.assertEqual(model.main(), 0)
                    if graphical:
                        graphic.assert_called_once_with(model.runtime.colors(), path=path)
                        self.assertIn('\x1b_Ga=T,f=100,U=1,', output.getvalue())
                    else: graphic.assert_not_called()
                    self.assertIn('Test OS', output.getvalue())
            path.unlink()
            with patch.object(model, 'ROOT', root), patch.object(model, 'load', return_value=settings), \
                    patch.object(model, 'system_data', return_value={'os': 'Still readable'}), \
                    patch.object(model.sys, 'stdout', output), patch.object(model.sys, 'argv', ['fetch']), \
                    patch.dict(os.environ, {'TERM': 'xterm-kitty', 'TMUX': '', 'STY': ''}):
                self.assertEqual(model.main(), 0)
                self.assertIn('Still readable', output.getvalue())


if __name__=='__main__':unittest.main()
