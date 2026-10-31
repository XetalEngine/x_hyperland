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
        for change in ({'enabled': 1}, {'effect': 'unknown'}, {'size': 0}, {'duration': 1.5},
                       {'follow_theme': 1}, {'color': 'red'}, {'shape': 'alien'}, {'speed': 0}, {'bubbles': 101}):
            with patch.object(controller, 'hypr') as hypr, self.assertRaises(ValueError):
                controller.save(dict(model.DEFAULTS, **change), 'unused')
            hypr.assert_not_called()
        with self.assertRaises(ValueError):
            model.decode(model.encode(model.DEFAULTS)+'enabled=0\n')

    def test_legacy_migration_preserves_preferences_and_new_fields_round_trip(self):
        old = model.decode('enabled=0\neffect=fireball\nduration=650\nsize=100\n')
        self.assertEqual(old, dict(model.DEFAULTS, enabled=False, duration=650, size=100))
        for shape in model.SHAPES:
            new = dict(old, effect='splat', shape=shape, follow_theme=False, color='#aabbcc', bubbles=0)
            self.assertEqual(model.decode(model.encode(new)), new)
        with self.assertRaises(ValueError):
            model.decode('enabled=1\neffect=splat\nduration=420\n')

    def test_native_settings_theme_colors_and_fixed_step_particles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config = root/'settings.conf'; palette = root/'current.colors'
            config.write_text(model.encode(dict(model.DEFAULTS, effect='splat', shape='coral')))
            palette.write_text('[Colors:Selection]\nDecorationFocus=1,2,3\n[Colors:Window]\nDecorationFocus=57,169,255\n')
            source = root/'check.cpp'; binary = root/'check'
            source.write_text('''#include "settings.hpp"
#include "fire.hpp"
#include <cassert>
#include <cmath>
int main(int argc,char** argv){
 auto s=Minimize::readSettings(argv[1],argv[2]);
 assert(s.effect=="splat" && s.shape==5);
 assert(std::abs(s.rgb[0]-57.F/255)<.001 && s.rgb[2]==1);
 Minimize::Fire a(42),b(42);
 for(int i=0;i<100;++i){a.advance(.016);b.advance(.008);b.advance(.008);}
 assert(a.particles.size()==384);
 int live=0;for(size_t i=0;i<a.particles.size();++i){
   auto& p=a.particles[i];assert(std::isfinite(p.x) && std::isfinite(p.y));
   assert(p.life==b.particles[i].life && p.x==b.particles[i].x);
   if(p.life>0)++live;
 }
 assert(live>80 && live<384);
 a.advance(3600); // A resumed session must not replay thousands of frames.
}''')
            subprocess.run(['g++', '-std=c++23', '-I'+str(ROOT/'native'), str(source), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary), str(config), str(palette)], check=True, timeout=10)

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

    def test_splat_controls_keep_custom_color_and_draft_until_apply(self):
        from effects.minimize.page import MinimizePage
        page = MinimizePage(lambda *args: None)
        page.effect.setCurrentIndex(page.effect.findData('splat'))
        page.follow_theme.setChecked(False); page.color = '#61e897'
        page.shape.setCurrentIndex(page.shape.findData('claw')); page.bubbles.setValue(95)
        page.edited()
        self.assertTrue(page.dirty); self.assertTrue(page.color_button.isEnabled())
        self.assertFalse(page.preview.isEnabled()); self.assertEqual(page.values()['shape'], 'claw')
        page.reset(); self.assertFalse(page.dirty)
        page.close()


if __name__ == '__main__':
    unittest.main()
