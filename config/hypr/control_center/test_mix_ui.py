import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QEvent,Qt
from PyQt6.QtWidgets import QApplication
import app
import runtime
import presets
from preset_page import ComponentDialog

QT=QApplication.instance() or QApplication([])


class MixUi(unittest.TestCase):
    def test_layouts_use_each_palette_and_preserve_page_drafts(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'state.json';state.write_text(json.dumps({'design':'binaryknife','mode':'dark','layout':'classic'}))
            with patch.object(runtime,'STATE',state),patch.object(app,'async_run',lambda *args:None):
                runtime.install(QT,app.STYLE);window=app.Window('theme')
                try:
                    theme=window.pages['theme'];theme.set_visibility(43)
                    for design in runtime.DESIGNS:
                        for layout in runtime.layouts.LAYOUTS:
                            state.write_text(json.dumps({'design':design,'mode':'dark','layout':layout}));QT.hypr_theme.apply();QT.processEvents()
                            self.assertEqual(window.tabs.currentWidget(),theme);self.assertEqual(theme.visibility,43)
                            self.assertEqual(window.modern_rail.isVisible(),layout!='classic')
                            self.assertEqual(window.tabs.tabBar().isVisible(),layout=='classic')
                            if layout=='sidebar':self.assertEqual(window.rail_buttons['theme'].toolButtonStyle(),Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                            self.assertIn(runtime.colors()['Accent'],QT.styleSheet())
                            if design=='binaryknife':
                                theme.tabs.setCurrentWidget(theme.layout_page)
                                QT.processEvents();window.grab().save('/tmp/fusion-layout-'+layout+'.png')
                finally:window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    def test_component_picker_empty_selection_and_cancel_write_nothing(self):
        with patch.object(app,'async_run',lambda *args:None):
            page=app.ThemePage(lambda *args:None);target=presets.builtin('modern','dark')
            try:
                dialog=ComponentDialog('Modern',target,page);dialog.select(False)
                self.assertEqual(dialog.selection(),set());self.assertFalse(dialog.apply.isEnabled())
                dialog.checks['layout'].setChecked(True);self.assertEqual(dialog.selection(),{'layout'})
                self.assertTrue(dialog.apply.isEnabled());dialog.deleteLater()
                with patch.object(ComponentDialog,'exec',return_value=0),patch.object(app.ThemePage,'async_run',create=True),patch('backend.apply_components') as apply:
                    page.apply_target('Modern',target,'token');apply.assert_not_called()
            finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)


if __name__=='__main__':unittest.main()
