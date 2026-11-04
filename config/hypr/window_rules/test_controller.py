from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'control_center')]
from window_rules import controller,model
from keys import hypr_compat


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);rules=root/'window_rules';rules.mkdir()
        self.document=rules/'rules.json';self.document.write_text('{"version":1,"rules":[]}\n')
        self.config=rules/'rules.conf';self.config.write_text('# Previous rules\n')
        self.main=root/'hyprland.conf';self.main.write_text('source = ~/.config/hypr/window_rules/rules.conf\n')
        self.original={p:p.read_bytes() for p in (self.document,self.config)}
        load=model.load
        for name,value in [('ROOT',rules),('PATH',self.document),('CONFIG',self.config)]:
            p=patch.object(model,name,value);p.start();self.addCleanup(p.stop)
        for p in (patch.object(model,'load',side_effect=lambda:load(self.document)),
                  patch.object(controller.buttons,'instance_dir'),
                  patch.object(hypr_compat,'candidate',return_value=self.main)):
            p.start();self.addCleanup(p.stop)
        self.expected=model.load()[1]
        self.changed={'version':1,'rules':[dict(model.DEFAULT,id='a'*32,app='org.kde.kate',layout='floating')]}
        self.valid=SimpleNamespace(returncode=0,stdout='config ok',stderr='')

    def test_apply_without_button_plugin(self):
        with patch('subprocess.run',return_value=self.valid),patch.object(controller.buttons,'hypr',side_effect=lambda *args:'[]' if args==('-j','plugin','list') else '') as hypr:
            document,_=controller.save(self.changed,self.expected)
        self.assertEqual(document,self.changed)
        self.assertIn('float = on',self.config.read_text())
        self.assertFalse(any(call.args[:1]==('dispatch',) for call in hypr.call_args_list))

    def test_failed_reload_restores_both_files(self):
        def hypr(*args):return 'Test failure' if args==('configerrors',) else '[]' if args==('-j','plugin','list') else ''
        with patch('subprocess.run',return_value=self.valid),patch.object(controller.buttons,'hypr',side_effect=hypr),self.assertRaisesRegex(ValueError,'Test failure'):
            controller.save(self.changed,self.expected)
        for path,content in self.original.items():self.assertEqual(path.read_bytes(),content)

    def test_concurrent_config_change_is_preserved(self):
        def validate(*args,**kwargs):
            self.main.write_text(self.main.read_text()+'# External edit\n');return self.valid
        with patch('subprocess.run',side_effect=validate),patch.object(controller.buttons,'hypr') as hypr,self.assertRaisesRegex(ValueError,'changed during validation'):
            controller.save(self.changed,self.expected)
        hypr.assert_not_called()
        for path,content in self.original.items():self.assertEqual(path.read_bytes(),content)
        self.assertIn('External edit',self.main.read_text())


if __name__=='__main__':unittest.main()
