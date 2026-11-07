import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cursors import model,effects


class EffectsTests(unittest.TestCase):
    def test_general_effects_have_visible_cards_and_are_not_tied_to_a_theme(self):
        from PyQt6.QtWidgets import QApplication
        from cursors.mouse_page import MouseEffectsPage
        app=QApplication.instance() or QApplication([])
        with patch.object(model,'load',return_value=(dict(model.DEFAULTS),'token')):
            page=MouseEffectsPage(lambda *args:None)
            for effect in effects.GENERAL:
                self.assertIn(effect,page.cards);page.cards[effect].click()
                self.assertEqual(page.draft['trail'],effect);self.assertTrue(page.color.isEnabled())
                for theme in effects.THEMES:self.assertEqual(effects.resolve(effect,theme),effect)
            page.enabled.setChecked(False)
            self.assertEqual(page.draft['trail'],'none');self.assertEqual(page.trail.currentData(),'none')
            page.enabled.setChecked(True)
            self.assertEqual(page.draft['trail'],'sparkle')
            self.assertEqual(set(effects.GENERAL)&set(effects.THEMES.values()),set())
            page.close()
    def test_native_theme_trails_are_distinct_and_mixing_is_independent(self):
        from theme.designs import DESIGNS
        self.assertLessEqual(set(effects.THEMES),set(DESIGNS))
        self.assertEqual(len(set(effects.THEMES.values())),len(effects.THEMES))
        for theme,style in effects.THEMES.items():
            self.assertEqual(effects.resolve('follow',theme),style)
            self.assertEqual(effects.resolve('ink',theme),'ink')
            self.assertEqual(model.validate(dict(model.DEFAULTS,trail=style))['trail'],style)
    def test_native_art_is_distinct_bounded_and_time_based(self):
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/'cursor-art'
            subprocess.run(['g++','-std=c++23','-O2',str(ROOT/'effects/cube/native/test_cursor_art.cpp'),'-o',str(exe)],check=True,capture_output=True)
            result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
            self.assertIn('passed',result.stdout)
    def test_legacy_trails_keep_the_selected_click_feedback_color(self):
        for trail in ('none','comet','glow','sparkle'):
            self.assertEqual(effects.colors(dict(model.DEFAULTS,trail=trail,color='#123456')),('#123456','#123456'))
    def test_controls_preserve_cursor_artwork_and_unsaved_changes(self):
        from PyQt6.QtWidgets import QApplication
        from cursors.mouse_page import MouseEffectsPage
        app=QApplication.instance() or QApplication([])
        with patch.object(model,'load',return_value=(dict(model.DEFAULTS,style='sumi',size=48),'token')):
            page=MouseEffectsPage(lambda *args:None);page.select('tidal');page.fields['intensity'].setValue(42);page.refresh()
            self.assertTrue(page.dirty);self.assertEqual(page.draft['trail'],'tidal');self.assertEqual(page.draft['style'],'sumi')
            page.reset_defaults();self.assertEqual(page.draft['size'],48);self.assertEqual(page.draft['trail'],'follow')
            page.resize(1120,720);page.show();app.processEvents();page.preview.advance();page.grab()
            page.hide();self.assertFalse(page.preview.timer.isActive());page.close()
    def test_every_preset_selects_a_supported_trail_and_preserves_timing(self):
        sys.path[:0]=[str(ROOT/'theme'),str(ROOT/'control_center')]
        import presets
        current={'version':1,'theme':{'design':'raw','mode':'dark'},'transfer':{},'icons':{},'sounds':{},
                 'cursors':dict(model.DEFAULTS,duration=750,intensity=40)}
        with patch.object(presets,'current',side_effect=lambda *args:copy.deepcopy(current)):
            for theme in presets.runtime.DESIGNS:
                value=presets.builtin(theme)
                # New designs may deliberately pair original cursor artwork with
                # a general trail instead of introducing another native effect.
                if theme in effects.THEMES:self.assertEqual(value['cursors']['trail'],'follow')
                else:self.assertIn(value['cursors']['trail'],effects.GENERAL)
                self.assertEqual(model.validate(value['cursors']),value['cursors'])
                self.assertEqual(value['cursors']['duration'],750)
                self.assertEqual(value['cursors']['intensity'],40)

if __name__=='__main__':unittest.main()
