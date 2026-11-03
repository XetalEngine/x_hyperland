import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import model
import rules
import controller


class RuleTests(unittest.TestCase):
    def test_inheritance_and_exact_application_identity(self):
        app=dict(rules.DEFAULTS,mode='always',anchor='bottom-left',size=42)
        window=dict(app,mode='off')
        self.assertEqual(rules.effective(dict(model.DEFAULTS,size=50))['size'],50)
        self.assertEqual(rules.effective(model.DEFAULTS,app),app)
        self.assertEqual(rules.effective(model.DEFAULTS,app,window),window)
        key='app "café" .*'
        data={'version':1,'apps':{key:app}}
        self.assertEqual(json.loads(rules.encode(data)),data)
        for change in ({'mode':'guess'},{'size':True},{'size':90},{'x':-5},{'anchor':'outside'},{'extra':0}):
            with self.assertRaises(ValueError):rules.validate(dict(app,**change))

    def test_apply_rollback_conflict_and_window_lifetime(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rules.json';info={'app':'fixture','id':'12'}
            def ipc(*args):
                return json.dumps({'windows':['12','13']}) if args==('xetal-windowbuttons',) else 'ok'
            with patch.object(controller,'window_info',return_value=info), \
                 patch.object(controller,'rule_file',return_value=(path,'windows')), \
                 patch.object(controller,'hypr',side_effect=ipc):
                _,token=rules.load(path,'windows')
                values,token=controller.save_rule('12','window',rules.DEFAULTS,token)
                self.assertEqual(values['windows'],{'12':rules.DEFAULTS})
                path.write_text(rules.encode({'version':1,'windows':{'12':rules.DEFAULTS,'99':rules.DEFAULTS}},'windows'))
                before=path.read_bytes()
                with self.assertRaisesRegex(ValueError,'changed elsewhere'):controller.save_rule('12','window',None,token)
                self.assertEqual(path.read_bytes(),before)
                _,token=rules.load(path,'windows')
                with patch.object(controller,'hypr',side_effect=RuntimeError('fixture failure')):
                    with self.assertRaises(RuntimeError):controller.save_rule('12','window',None,token)
                self.assertEqual(path.read_bytes(),before)
                values,_=controller.save_rule('12','window',None,token)
                self.assertEqual(values['windows'],{})
            with patch.object(controller,'window_info',side_effect=ValueError('This window has closed.')):
                before=path.read_bytes()
                with self.assertRaisesRegex(ValueError,'closed'):controller.save_rule('12','window',rules.DEFAULTS,'invalid')
                self.assertEqual(path.read_bytes(),before)

    def test_app_apply_rolls_back_when_native_reload_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rules.json'
            with patch.object(controller,'window_info',return_value={'app':'fixture'}), \
                 patch.object(controller,'rule_file',return_value=(path,'apps')), \
                 patch.object(controller,'hypr',side_effect=RuntimeError('rejected')):
                _,token=rules.load(path)
                with self.assertRaisesRegex(RuntimeError,'rejected'):controller.save_rule('12','app',rules.DEFAULTS,token)
                self.assertFalse(path.exists())


if __name__=='__main__':unittest.main()
