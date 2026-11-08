"""Apps must keep tool identities when an external icon pack lacks Fusion names."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication,QPushButton
import app
from icon_themes import art,model

QT=QApplication.instance() or QApplication([])


class ToolIconTests(unittest.TestCase):
    def test_builtin_and_external_packs_keep_three_distinct_tool_icons(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'theme/state.json'
            state.parent.mkdir();(root/'icon_themes').mkdir()
            (root/'icon_themes/packs').symlink_to(model.ROOT/'icon_themes/packs')
            with patch.object(app.theme_runtime,'STATE',state),patch.object(app.catalog,'applications',return_value={}),patch.object(app.catalog,'favorites',return_value=[]):
                state.write_text(json.dumps({'design':'raw'}))
                window=app.Menu(preview=True)
                try:
                    control=next(button for button in window.findChildren(QPushButton) if button.text().strip()=='Control Panel')
                    for system in ('follow','other'):
                        model.save({**model.DEFAULTS,'system':system,'other':'auto'},model.load(root)[1],root)
                        for style in art.STYLES:
                            for mode in model.MODES:
                                with self.subTest(system=system,style=style,mode=mode):
                                    state.write_text(json.dumps({'design':style,'mode':mode}))
                                    model.apply_qt(root,style,mode);window.apply_design()
                                    settings=window.fusion_settings_button.icon().pixmap(20,20).toImage()
                                    chip=window.kvm_button.icon().pixmap(20,20).toImage()
                                    panel=control.icon().pixmap(20,20).toImage()
                                    self.assertFalse(settings.isNull());self.assertFalse(chip.isNull())
                                    self.assertNotEqual(settings,panel);self.assertNotEqual(settings,chip)
                                    self.assertNotEqual(chip,QIcon.fromTheme('computer').pixmap(20,20).toImage())
                                    for image,name in ((settings,'xetal-fusion-settings'),(chip,'xetal-kvm-settings')):
                                        if system=='follow':
                                            expected=QIcon(str(root/'icon_themes/packs'/('Xetal-System-'+style)/'scalable'/(name+'.svg')))
                                            self.assertEqual(image,expected.pixmap(20,20).toImage())
                finally:window.close();window.deleteLater()


if __name__=='__main__':unittest.main()
