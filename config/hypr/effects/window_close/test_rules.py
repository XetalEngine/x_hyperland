import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import model
import rules
import controller


class RuleTests(unittest.TestCase):
    def test_kde_profile_keeps_standard_and_other_windows_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);standard=root/'rules.json'
            standard.write_text(rules.encode({'version':1,'apps':{'fixture':dict(rules.DEFAULTS,size=42)}}))
            before=standard.read_bytes()
            info={'app':'fixture','control_profile':'kde','workspace_controls':'individual'}
            def ipc(*args):return '{"windows":["12","13"]}' if args==('xetal-windowbuttons',) else 'ok'
            with patch.object(rules,'PATH',standard),patch.object(controller,'instance_dir',return_value=root), \
                 patch.object(controller,'window_info',return_value=info),patch.object(controller,'hypr',side_effect=ipc):
                path,section=controller.rule_file('app','kde');_,token=rules.load(path,section)
                controller.save_rule('12','app',dict(rules.DEFAULTS,mode='off'),token,profile='kde')
                self.assertEqual(rules.load(path)[0]['apps']['fixture']['mode'],'off')
                self.assertEqual(standard.read_bytes(),before)
                windows,kind=controller.rule_file('window','kde');_,token=rules.load(windows,kind)
                controller.save_rule('12','window',dict(rules.DEFAULTS,mode='always'),token,profile='kde')
                self.assertEqual(rules.load(windows,kind)[0]['windows']['12']['mode'],'always')
                self.assertFalse(controller.rule_file('window')[0].exists())
                old=windows.read_bytes();_,token=rules.load(windows,kind)
                with patch.object(controller,'window_info',side_effect=[info,dict(info,control_profile='standard')]):
                    with self.assertRaisesRegex(ValueError,'mode changed'):
                        controller.save_rule('12','window',None,token,profile='kde')
                self.assertEqual(windows.read_bytes(),old)
                with self.assertRaisesRegex(ValueError,'mode changed'):
                    controller.save_rule('12','window',None,token)
        self.assertEqual(rules.effective(model.DEFAULTS,profile='kde')['mode'],'auto')
        self.assertEqual(rules.effective(model.DEFAULTS)['mode'],'super')
        self.assertEqual(json.loads(controller.preview_payload('12','a'*32,rules.DEFAULTS,profile='kde'))['profile'],'kde')

    def test_background_upgrade_and_native_color_selection(self):
        legacy={key:rules.DEFAULTS[key] for key in rules.LEGACY_KEYS}
        old={'version':1,'apps':{'fixture':dict(legacy,size=46)}}
        upgraded=rules.validate_document(old)
        self.assertEqual(upgraded['apps']['fixture'],dict(rules.DEFAULTS,size=46))
        self.assertNotIn('background',old['apps']['fixture'])
        for change in ({'background':'guess'},{'background_color':'#fff'},
                       {'background_color':'#80ffffff'},{'background_color':'red'}):
            with self.assertRaises(ValueError):rules.validate(dict(rules.DEFAULTS,**change))
        self.assertEqual(rules.validate(dict(rules.DEFAULTS,background_color='#AABBCC'))['background_color'],'#aabbcc')
        with tempfile.TemporaryDirectory() as directory:
            executable=Path(directory)/'background'
            subprocess.run(['g++','-std=c++23','-O2',str(Path(__file__).parent/'native/test_background.cpp'),'-ljson-c','-o',str(executable)],check=True,capture_output=True)
            subprocess.run([str(executable)],check=True,capture_output=True)

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

    def test_app_editor_clears_only_its_window_override_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Path(directory)/'app.json';windows=Path(directory)/'windows.json'
            app.write_text(rules.encode({'version':1,'apps':{'fixture':rules.DEFAULTS}}))
            off=dict(rules.DEFAULTS,mode='off')
            windows.write_text(rules.encode({'version':1,'windows':{'12':off,'13':off}},'windows'))
            _,app_token=rules.load(app);_,window_token=rules.load(windows,'windows')
            def file(scope):return (app,'apps') if scope=='app' else (windows,'windows')
            def ipc(*args,**kwargs):return '{"windows":["12","13"]}' if args==('xetal-windowbuttons',) else 'ok'
            before=(app.read_bytes(),windows.read_bytes())
            with patch.object(controller,'window_info',return_value={'app':'fixture'}),patch.object(controller,'rule_file',side_effect=file),patch.object(controller,'hypr',side_effect=ipc):
                def reject(*args,**kwargs):
                    if args[0]=='dispatch':raise RuntimeError('native rejected')
                    return ipc(*args,**kwargs)
                with patch.object(controller,'hypr',side_effect=reject):
                    with self.assertRaisesRegex(RuntimeError,'native rejected'):
                        controller.save_rule('12','app',dict(off,mode='always'),app_token,window_token=window_token)
                self.assertEqual((app.read_bytes(),windows.read_bytes()),before)
                with self.assertRaisesRegex(ValueError,'changed elsewhere'):
                    controller.save_rule('12','app',off,app_token,window_token='stale')
                self.assertEqual((app.read_bytes(),windows.read_bytes()),before)
                controller.save_rule('12','app',dict(off,mode='always'),app_token,window_token=window_token)
                self.assertEqual(rules.load(app)[0]['apps']['fixture']['mode'],'always')
                self.assertEqual(rules.load(windows,'windows')[0]['windows'],{'13':off})


if __name__=='__main__':unittest.main()
