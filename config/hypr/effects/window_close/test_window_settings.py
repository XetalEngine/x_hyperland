from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
import window_settings as ui


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.files={'app':(root/'apps.json','apps'),'window':(root/'windows.json','windows')}
        self.app_rule=dict(ui.rules.DEFAULTS,mode='always',size=42)
        self.window_rule=dict(ui.rules.DEFAULTS,mode='off',size=54,x=80,y=36)
        for scope,key,value in [('app','fixture',self.app_rule),('window','12',self.window_rule)]:
            path,section=self.files[scope];path.write_text(ui.rules.encode({'version':1,section:{key:value}},section))
        info={'app':'fixture','id':'12','rule':self.window_rule,'window_override':True,'app_override':True,'size':[900,600]}
        self.stack.enter_context(patch.object(ui.controller,'window_info',return_value=info))
        self.stack.enter_context(patch.object(ui.controller,'rule_file',side_effect=lambda scope:self.files[scope]))
        self.stack.enter_context(patch.object(ui.model,'load',return_value=(dict(ui.model.DEFAULTS,size=36,inset=10),'global')))
        self.save=self.stack.enter_context(patch.object(ui.controller,'save_rule'))
        self.end=self.stack.enter_context(patch.object(ui.controller,'end_preview'))
        self.dialog=ui.RuleDialog('12');self.addCleanup(self.dialog.reject)

    def test_app_scope_starts_with_this_windows_effective_settings(self):
        self.assertTrue(self.dialog.valid,self.dialog.status.text())
        self.assertEqual(self.dialog.scope.currentData(),'app')
        self.assertEqual(self.dialog.values(),self.window_rule)
        self.dialog.x.slider.setValue(126);self.dialog.size.slider.setValue(46)
        self.assertEqual(self.dialog.values()['x'],126);self.assertEqual(self.dialog.values()['size'],46)
        self.dialog.scope.setCurrentIndex(self.dialog.scope.findData('window'))
        self.assertEqual(self.dialog.values()['x'],126)
        self.dialog.scope.setCurrentIndex(self.dialog.scope.findData('app'))
        expected=self.dialog.values();self.dialog.apply()
        self.save.assert_called_once_with('12','app',expected,self.dialog.tokens['app'],window_token=self.dialog.tokens['window'])

    def test_reset_is_window_only_and_draft_until_applied(self):
        self.dialog.reset.click()
        self.assertEqual(self.dialog.scope.currentData(),'window')
        expected=dict(ui.rules.DEFAULTS,size=36,x=10,y=10)
        self.assertEqual(self.dialog.values(),expected);self.save.assert_not_called()
        self.dialog.apply()
        self.save.assert_called_once_with('12','window',expected,self.dialog.tokens['window'],window_token=None)

    def test_close_discards_draft_and_releases_preview_once(self):
        self.dialog.y.slider.setValue(121);self.dialog.reject();self.dialog.end_preview()
        self.save.assert_not_called();self.end.assert_called_once_with('12',self.dialog.preview_token)
        self.assertFalse(self.dialog.heartbeat.isActive())

    def test_inheritance_and_reload_show_current_values(self):
        self.dialog.scope.setCurrentIndex(self.dialog.scope.findData('window'));self.dialog.use_inherited()
        self.assertEqual(self.dialog.values(),self.app_rule);self.assertTrue(self.dialog.remove_override)
        self.dialog.load();self.assertEqual(self.dialog.values(),self.window_rule);self.assertFalse(self.dialog.remove_override)


if __name__=='__main__':unittest.main()
