"""A resident Theme window must keep explicit choices and recover without reopening."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
import app
import page as theme_page
import runtime

QT=QApplication.instance() or QApplication([])


class ThemeApplyTests(unittest.TestCase):
    def setUp(self):
        self.context=ExitStack();self.addCleanup(self.context.close)
        folder=self.context.enter_context(tempfile.TemporaryDirectory())
        self.state=Path(folder)/'state.json'
        self.write_state(design='ghostbusters',mode='dark',layout='ribbon',avatar='auto')
        self.context.enter_context(patch.object(runtime,'STATE',self.state))
        self.context.enter_context(patch.object(theme_page.backend,'theme_token',side_effect=self.state.read_bytes))
        self.context.enter_context(patch.object(theme_page.ComponentDialog,'exec',return_value=1))
        self.jobs=[]
        self.page=app.ThemePage(lambda fn,done,failed:self.jobs.append((fn,done,failed)))
        self.addCleanup(self.dispose)

    def dispose(self):
        self.page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def write_state(self,**changes):
        value=json.loads(self.state.read_text()) if self.state.exists() else {}
        self.state.write_text(json.dumps({**value,**changes}))

    def submitted(self):
        self.page.save_mode()
        self.assertTrue(self.jobs,'The selected preset did not reach the apply job.')
        with patch.object(theme_page.backend,'apply_components',return_value='saved') as apply:
            self.jobs[-1][0]()
        return apply.call_args.args

    def test_selecting_old_preset_does_not_reapply_current_theme(self):
        self.write_state(design='facadasexu',mode='light',layout='classic',
                         launcher_style='facadasexu',launcher_background_visibility=63)
        self.page.select_preset('ghostbusters')
        # A deferred page refresh must not erase a deliberate re-selection.
        self.page.refresh()
        target,selected,token=self.submitted()
        self.assertEqual(target['theme']['design'],'ghostbusters')
        self.assertEqual(target['theme']['mode'],'dark')
        self.assertEqual(target['theme']['layout'],'ribbon')
        self.assertEqual(target['theme']['launcher_style'],'follow')
        self.assertEqual(target['theme']['launcher_background_visibility'],63)
        self.assertIn('waybar',selected);self.assertIn('wallpaper',selected)
        self.assertEqual(token,self.state.read_bytes())

    def test_third_preset_is_not_blocked_by_stale_desktop_choice(self):
        self.write_state(design='facadasexu',mode='light',layout='classic')
        self.page.select_preset('prisonbreak')
        target,selected,_=self.submitted()
        self.assertEqual(target['theme']['design'],'prisonbreak')
        self.assertIn('colors',selected)
        self.assertTrue(self.page.conflict_actions.isHidden())

    def test_reselecting_active_preset_offers_all_components(self):
        self.page.select_preset('ghostbusters')
        _,selected,_=self.submitted()
        self.assertEqual(selected,set(theme_page.presets.COMPONENTS)-{'icons'})

    def test_other_conflicting_edits_still_need_resolution(self):
        self.page.set_background('mine.png')
        self.write_state(design='facadasexu',launcher_background='theirs.png')
        self.page.select_preset('prisonbreak')
        self.page.save_mode()
        self.assertEqual(self.jobs,[])
        self.assertFalse(self.page.conflict_actions.isHidden())
        self.assertIn('Apps background',self.page.status.text())
        self.assertEqual(self.page.background,'mine.png')
        self.page.resolve_conflicts('saved')
        target,_,_=self.submitted()
        self.assertEqual(target['theme']['design'],'prisonbreak')
        self.assertEqual(target['theme']['launcher_background'],'theirs.png')
        self.assertEqual(target['theme']['layout'],'ribbon')

    def test_component_read_restores_apply_button_on_success_and_failure(self):
        for failed in (False,True):
            with self.subTest(failed=failed):
                self.page.wallpapers.refresh()
                self.assertFalse(self.page.apply.isEnabled())
                self.page.select_preset('prisonbreak')
                if failed:self.jobs[-1][2]('Display read failed')
                else:self.jobs[-1][1](([],{}))
                self.assertFalse(self.page.busy)
                self.assertTrue(self.page.apply.isEnabled())
                self.assertEqual(self.page.design.currentData(),'prisonbreak')

    def test_apply_failure_is_visible_and_retry_uses_same_window(self):
        self.page.select_preset('prisonbreak')
        self.submitted()
        self.assertFalse(self.page.apply.isEnabled())
        with patch('sys.stderr',new_callable=io.StringIO) as log:
            self.jobs[-1][2]('Compositor reload failed')
        self.assertIn('Prison Break',log.getvalue())
        self.assertIn('Compositor reload failed',log.getvalue())
        self.assertFalse(self.page.busy)
        self.assertTrue(self.page.apply.isEnabled())
        error=self.page.findChild(theme_page.QMessageBox,'themeApplyError')
        self.assertIsNotNone(error)
        self.assertEqual(error.informativeText(),'Compositor reload failed')
        error.close()
        target,selected,_=self.submitted()
        self.assertEqual(target['theme']['design'],'prisonbreak')
        self.state.write_text(json.dumps(theme_page.presets.merged_theme(runtime.state(),target,selected)))
        self.jobs[-1][1](self.state.read_bytes())
        self.assertFalse(self.page.busy)
        self.assertFalse(self.page.dirty)
        self.assertTrue(self.page.apply.isEnabled())
        # Completing a later read must not overwrite the success message.
        status=self.page.status.text()
        self.page.wallpapers.refresh();self.jobs[-1][1](([],{}))
        self.assertEqual(self.page.status.text(),status)
        self.page.select_preset('ghostbusters')
        target,_,_=self.submitted()
        self.assertEqual(target['theme']['design'],'ghostbusters')


if __name__=='__main__':unittest.main()
