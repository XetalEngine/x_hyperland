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
                       {'follow_theme': 1}, {'color': 'red'}, {'shape': 'alien'}, {'speed': 0}, {'bubbles': 101}, {'surface': 'unknown'},
                       {'edge': 'center'}, {'order': 'sideways'}, {'presentation':'panel'}, {'dock_style':'missing'},
                       {'dock_edge':'middle'}, {'hide_delay':0}, {'dock_duration':99}, {'proximity':65},
                       {'dock_zoom':151}, {'auto_hide':1}):
            with patch.object(controller, 'hypr') as hypr, self.assertRaises(ValueError):
                controller.save(dict(model.DEFAULTS, **change), 'unused')
            hypr.assert_not_called()
        with self.assertRaises(ValueError):
            model.decode(model.encode(model.DEFAULTS)+'enabled=0\n')

    def test_legacy_migration_preserves_preferences_and_new_fields_round_trip(self):
        old = model.decode('enabled=0\neffect=fireball\nduration=650\nsize=100\n')
        self.assertEqual(old, dict(model.DEFAULTS, enabled=False, duration=650, size=100, presentation='stack',hide_animation='slide',fire_indicator=False))
        for missing in ({'surface','edge','order'}, {'edge','order'}, set()):
            previous={k:v for k,v in model.DEFAULTS.items() if k in model.PRE_DOCK-missing}
            text=''.join(f'{k}={int(v) if type(v) is bool else v}\n' for k,v in previous.items())
            self.assertEqual(model.decode(text),dict(model.DEFAULTS,presentation='stack',hide_animation='slide',fire_indicator=False))
        for shape in model.SHAPES:
            new = dict(old, effect='splat', shape=shape, follow_theme=False, color='#aabbcc', bubbles=0)
            self.assertEqual(model.decode(model.encode(new)), dict(new,effect='fireball'))
        for style in model.DOCK_STYLES:
            new=dict(model.DEFAULTS,dock_style=style,hide_delay=2500,proximity=24)
            self.assertEqual(model.decode(model.encode(new)),new)
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
 assert(s.effect=="fireball" && s.shape==5);
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
 Minimize::Column c(1280,800,0,40,0,0,76,20,999,false,false);
 assert(c.capacity==8 && c.offset==12 && !c.visible(11) && c.visible(19));
 assert(c.box(12).x==8 && c.box(12).y==52);
 assert(c.box(19).y+76<800);
 for(bool right:{false,true})for(bool up:{false,true}){
   Minimize::Column column(1280,800,32,40,56,28,76,20,999,right,up);
   auto first=column.box(column.offset),last=column.box(column.offset+column.capacity-1);
   assert(first.x==(right?1140:40));
   assert(first.y==(up?684:52));
   assert((up && last.y<first.y) || (!up && last.y>first.y));
   assert(last.y>=40 && last.y+last.h<=772);
 }
 Minimize::Column small(320,120,0,36,0,0,120,2,-9);
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

    def test_dock_controls_keep_custom_color_and_draft_until_apply(self):
        from effects.minimize.page import MinimizePage
        page = MinimizePage(lambda *args: None)
        page.follow_theme.setChecked(False); page.color = '#61e897'
        page.dock_style.cards['hollowgrove'].click()
        page.dock_edge.setCurrentIndex(page.dock_edge.findData('top'));page.hide_delay.setValue(2200)
        page.edge.setCurrentIndex(page.edge.findData('right')); page.order.setCurrentIndex(page.order.findData('top-to-bottom'))
        page.edited()
        self.assertTrue(page.dirty); self.assertTrue(page.color_button.isEnabled())
        self.assertFalse(page.preview.isEnabled()); self.assertEqual(page.values()['dock_style'], 'hollowgrove')
        self.assertEqual(page.values()['dock_edge'],'top');self.assertEqual(page.values()['hide_delay'],2200)
        self.assertEqual(page.values()['edge'],'right'); self.assertEqual(page.values()['order'],'top-to-bottom')
        self.assertEqual(page.effect.count(),1);self.assertEqual(page.effect.itemData(0),'fireball')
        page.presentation.setCurrentIndex(page.presentation.findData('stack'))
        self.assertFalse(page.dock_options.isEnabled());self.assertFalse(page.edge.isHidden())
        page.presentation.setCurrentIndex(page.presentation.findData('dock'))
        self.assertTrue(page.dock_options.isEnabled());self.assertTrue(page.edge.isHidden())
        page.reset(); self.assertFalse(page.dirty)
        page.close()

    def test_gallery_previews_drafts_without_touching_live_settings(self):
        from effects.minimize.page import MinimizePage
        from effects.minimize.gallery import runtime
        with patch.object(model, 'load', return_value=(dict(model.DEFAULTS), 'token')), \
             patch.object(controller, 'save') as save, patch.object(controller, 'activate') as activate, \
             patch.object(runtime, 'design', return_value='hollowgrove'):
            page = MinimizePage(lambda *args: self.fail('Browsing must not invoke a live operation'))
            page.follow_theme.setChecked(False); page.color = '#61e897'; page.edited()
            for style in model.DOCK_STYLES:
                page.dock_style.cards[style].click()
                self.assertEqual(page.values()['dock_style'], style)
                self.assertEqual(page.dock_preview.scene.style, 'hollowgrove' if style == 'follow' else style)
                self.assertEqual(page.dock_preview.scene.colors['Accent'], '#61e897')
                self.assertTrue(page.dirty); self.assertTrue(page.apply.isEnabled())
            page.reset()
            self.assertFalse(page.dirty); self.assertEqual(page.dock_style.value(), 'follow')
            save.assert_not_called(); activate.assert_not_called(); page.close()

    def test_visual_picker_cancel_and_accept_keep_quick_selection_explicit(self):
        from PyQt6.QtCore import QTimer
        from effects.minimize.gallery import DesignButton, DesignDialog
        field = DesignButton(); field.setValue('tidalglass')
        def finish(accept):
            dialog = next(w for w in self.app.topLevelWidgets() if isinstance(w, DesignDialog) and w.isVisible())
            dialog.designs.cards['hollowgrove'].click()
            dialog.accept() if accept else dialog.reject()
        QTimer.singleShot(0, lambda: finish(False)); field.click()
        self.assertEqual(field.value(), 'tidalglass')
        QTimer.singleShot(0, lambda: finish(True)); field.click()
        self.assertEqual(field.value(), 'hollowgrove'); field.close()

    def test_preview_animation_stops_when_hidden_and_empty_dock_collapses(self):
        from PyQt6.QtTest import QTest
        from effects.minimize.gallery import PreviewPanel
        panel = PreviewPanel(); panel.resize(480, 430); panel.show(); QTest.qWait(50)
        scene = panel.scene; self.assertTrue(scene.animation.isActive())
        phase = scene.phase
        for _ in range(3): panel.remove.click()
        self.assertFalse(panel.remove.isEnabled()); self.assertTrue(panel.add.isEnabled())
        QTest.qWait(550)
        self.assertEqual(scene.weights, []); self.assertEqual(scene.slots, [])
        self.assertGreater(scene.phase, phase)
        panel.add.click(); QTest.qWait(100)
        self.assertEqual(scene.count, 1); self.assertTrue(scene.slots)
        panel.hide(); self.assertFalse(scene.animation.isActive()); panel.close()


if __name__ == '__main__':
    unittest.main()
