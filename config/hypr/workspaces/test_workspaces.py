from contextlib import ExitStack
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspaces import model, controller
from effects.window_close import rules


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.path=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))/'rules.json'
        self.stack.enter_context(patch.object(controller.buttons,'instance_dir',return_value=self.path.parent))
        self.stack.enter_context(patch.object(controller.button_settings,'load',return_value=(dict(controller.button_settings.DEFAULTS,size=36,inset=10),'global')))
        self.activate=self.stack.enter_context(patch.object(controller,'activate'))

    def test_missing_defaults_are_individual_without_a_write(self):
        data,_=model.load(self.path)
        self.assertEqual(model.effective(data,3),model.DEFAULT)
        self.assertFalse(self.path.exists())

    def test_choices_merge_per_workspace_and_survive_reload(self):
        controller.save(3,layout='tile',path=self.path)
        controller.save(8,controls='off',path=self.path)
        controller.save(3,controls='on',path=self.path)
        data,_=model.load(self.path)
        self.assertEqual(data['workspaces']['3']['layout'],'tile')
        self.assertEqual(data['workspaces']['3']['controls'],'on')
        self.assertEqual(data['workspaces']['8']['controls'],'off')
        self.assertEqual(data['workspaces']['3']['rule']['size'],36)
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)

    def test_cycle_keeps_all_four_modes_and_other_choices(self):
        controller.save(203,controls='off',path=self.path)
        controller.save(204,layout='tile',path=self.path)
        for expected in ('tile','floating','kde','off','tile'):
            data,_=controller.save(203,cycle_layout=True,path=self.path)
            self.assertEqual(data['workspaces']['203']['layout'],expected)
            self.assertEqual(data['workspaces']['203']['controls'],'off')
            self.assertEqual(data['workspaces']['204']['layout'],'tile')
        before=self.path.read_bytes()
        with patch.object(controller,'activate',side_effect=RuntimeError('rejected')):
            with self.assertRaises(RuntimeError):controller.save(203,cycle_layout=True,path=self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_disabling_override_retains_shared_geometry(self):
        rule=dict(rules.DEFAULTS,size=10,x=83,background='manual',background_color='#123456')
        controller.save(3,controls='on',rule=rule,path=self.path)
        controller.save(3,controls='individual',path=self.path)
        data,_=controller.save(3,controls='on',path=self.path)
        self.assertEqual(data['workspaces']['3']['rule'],dict(rule,mode='always'))

    def test_editor_conflict_does_not_overwrite_newer_menu_choice(self):
        _,token=controller.save(3,controls='on',path=self.path)
        controller.save(3,controls='off',path=self.path)
        before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):
            controller.save(3,rule=rules.DEFAULTS,token=token,path=self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_moved_window_cannot_save_to_its_previous_workspace(self):
        _,token=controller.save(3,controls='on',path=self.path)
        with patch.object(controller.buttons,'window_info',return_value={'workspace':4,'workspace_controls':'on'}):
            with self.assertRaisesRegex(ValueError,'workspace settings changed'):
                controller.save(3,rule=rules.DEFAULTS,token=token,path=self.path,window_id='12')

    def test_failed_activation_restores_previous_bytes_or_missing_file(self):
        for existed in (False,True):
            if existed:controller.save(3,layout='tile',path=self.path)
            before=self.path.read_bytes() if self.path.exists() else None
            with patch.object(controller,'activate',side_effect=RuntimeError('fixture failure')):
                with self.assertRaisesRegex(RuntimeError,'fixture failure'):controller.save(3,controls='on',path=self.path)
            self.assertEqual(self.path.read_bytes() if self.path.exists() else None,before)

    def test_invalid_file_is_not_replaced(self):
        self.path.write_text('{')
        with self.assertRaises(ValueError):controller.save(3,layout='tile',path=self.path)
        self.assertEqual(self.path.read_text(),'{')
        self.activate.assert_not_called()

    def test_validation_rejects_bad_id_type_mode_and_oversized_buttons(self):
        for key in ('0','01','-2','special:1',True,2.5,'2147483648'):
            with self.subTest(key=key),self.assertRaises(ValueError):model.identity(key)
        for field,value in [('layout',[]),('controls','always'),('layout','maximized')]:
            data={'version':1,'workspaces':{'3':copy.deepcopy(model.DEFAULT)}}
            data['workspaces']['3'][field]=value
            with self.assertRaises(ValueError):model.validate(data)
        data={'version':1,'workspaces':{'3':copy.deepcopy(model.DEFAULT)}}
        data['workspaces']['3']['rule']['size']=65
        with self.assertRaises(ValueError):model.validate(data)

    def test_workspace_preview_payload_has_explicit_scope(self):
        import json
        payload=json.loads(controller.buttons.preview_payload('12','a'*32,rules.DEFAULTS,workspace=3))
        self.assertEqual(payload['workspace'],3)
        self.assertNotIn('workspace',json.loads(controller.buttons.preview_payload('12','a'*32,rules.DEFAULTS)))

    def test_cube_display_number_does_not_change_saved_identity(self):
        (self.path.parent/'xetal-cube-faces').write_text('enabled\n203 3\t203\n204 4\t204\n')
        self.assertEqual(controller.display_number(203),'3')
        self.assertEqual(controller.display_number(8),'8')
        data,_=controller.save(203,controls='on',path=self.path)
        self.assertIn('203',data['workspaces']);self.assertNotIn('3',data['workspaces'])


class ActivationTests(unittest.TestCase):
    def test_non_ok_native_response_is_a_failed_save(self):
        import json
        plugins=json.dumps([{'name':'Xetal Window Memory'},{'name':'Xetal Window Close'}])
        with patch.object(controller.buttons,'hypr',side_effect=[plugins,'ok','Workspace reload rejected']):
            with self.assertRaisesRegex(RuntimeError,'reload rejected'):controller.activate()


if __name__=='__main__':unittest.main()
