import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent))
from effects.minimize import model, controller


class SettingsTests(unittest.TestCase):
    def test_invalid_input_never_reaches_compositor(self):
        for change in ({'enabled': 1}, {'effect': 'unknown'}, {'size': 0}, {'duration': 1.5}):
            with patch.object(controller, 'hypr') as hypr, self.assertRaises(ValueError):
                controller.save(dict(model.DEFAULTS, **change), 'unused')
            hypr.assert_not_called()
        with self.assertRaises(ValueError):
            model.decode(model.encode(model.DEFAULTS)+'enabled=0\n')

    def test_failed_activation_restores_file_and_keeps_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.conf'; path.write_text(model.encode(model.DEFAULTS))
            before = path.read_bytes(); values, token = model.load(path); values['enabled'] = False
            with patch.object(controller, 'instance_dir', return_value=Path(directory)), \
                 patch.object(controller, 'activate', side_effect=RuntimeError('Cannot load')):
                with self.assertRaises(RuntimeError):
                    controller.save(values, token, path)
            self.assertEqual(path.read_bytes(), before)

    def test_conflicting_edit_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.conf'; values, token = model.load(path)
            external = dict(values, size=100); path.write_text(model.encode(external))
            with patch.object(controller, 'instance_dir', return_value=Path(directory)), \
                 patch.object(controller.build, 'build', return_value=Path('/unused')), self.assertRaisesRegex(ValueError, 'elsewhere'):
                controller.save(values, token, path)
            self.assertEqual(model.load(path)[0], external)

    def test_off_at_login_still_loads_window_order_handler(self):
        with patch.object(model, 'load', return_value=(dict(model.DEFAULTS, enabled=False), 'token')), \
             patch.object(controller, 'activate') as activate:
            controller.start()
        activate.assert_called_once_with(dict(model.DEFAULTS, enabled=False))

    def test_column_overflow_and_travel_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'motion.cpp'; binary = Path(directory)/'motion'
            source.write_text('''#include "motion.hpp"
#include <cassert>
int main(){
 Minimize::Column c(1280,800,0,40,0,76,20,999);
 assert(c.capacity==8 && c.offset==12 && !c.visible(11) && c.visible(19));
 assert(c.box(12).x==8 && c.box(12).y==52);
 assert(c.box(19).y+76<800);
 Minimize::Column small(320,120,0,36,0,120,2,-9);
 assert(small.capacity==1 && small.offset==0 && small.box(0).y+small.size<=120);
 Minimize::Rect a{100,200,800,600},b{8,50,76,76};
 auto start=Minimize::travel(a,b,0),end=Minimize::travel(a,b,1);
 assert(start.x==a.x && start.w==a.w && end.x==b.x && end.w==b.w);
}''')
            subprocess.run(['g++', '-std=c++23', '-I'+str(ROOT/'native'), str(source), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, timeout=10)


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_save_failure_keeps_edits_and_recovery_accessible(self):
        from effects.minimize.page import MinimizePage
        def run(work, done, failed):
            try: result = work()
            except Exception as exc: failed(str(exc))
            else: done(result)
        page = MinimizePage(run); page.enabled.setChecked(False)
        with patch.object(controller, 'save', side_effect=RuntimeError('Load failed')):
            page.save()
        self.assertTrue(page.dirty); self.assertFalse(page.busy)
        self.assertTrue(page.restore.isEnabled()); self.assertIn('Load failed', page.status.text())
        page.close()

    def test_corrupt_settings_do_not_break_theme_page(self):
        from effects.minimize.page import MinimizePage
        with patch.object(model, 'load', side_effect=ValueError('bad setting')):
            page = MinimizePage(lambda *args: None)
        self.assertIn('Cannot read', page.status.text()); self.assertFalse(page.preview.isEnabled())
        page.close()


if __name__ == '__main__':
    unittest.main()
