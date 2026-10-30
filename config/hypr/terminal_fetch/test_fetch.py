import copy
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


if __name__=='__main__':unittest.main()
