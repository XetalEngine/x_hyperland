"""Design changes retain the editor engine and dispose animated artwork safely."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
import app
import keys
import runtime
import page as theme_page

QT=QApplication.instance() or QApplication([])


class DesignTests(unittest.TestCase):
    def test_background_applies_after_external_update_without_losing_other_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'theme.json'
            state.write_text(json.dumps({'design':'breakpoint','mode':'dark','avatar':'auto'}))
            def save(mode,token,design,avatar,enabled,background,surfaces,launcher_style,**options):
                current=json.loads(state.read_text())
                current.update(design=design,mode=mode,avatar=avatar,launcher_wallpaper=enabled,
                    launcher_background=background,launcher_surfaces=surfaces,launcher_style=launcher_style,**options)
                state.write_text(json.dumps(current));return 'after'
            with patch.object(runtime,'STATE',state),patch.object(theme_page.backend,'theme_token',side_effect=lambda:state.read_text()),patch.object(theme_page.backend,'apply_mode',side_effect=save) as apply:
                page=app.ThemePage(lambda fn,done,failed:done(fn()))
                try:
                    page.refresh();page.set_background('chosen.png');page.set_visibility(52)
                    page.start_menu_page.label_controls['names'].click();page.start_menu_page.label_controls['hotkeys'].click()
                    external=json.loads(state.read_text());external.update(design='modern',mode='light',unrelated='preserved')
                    state.write_text(json.dumps(external));page.save_mode()
                    self.assertEqual(apply.call_count,1);self.assertFalse(page.dirty)
                    saved=json.loads(state.read_text())
                    self.assertEqual(saved['launcher_background'],'chosen.png');self.assertEqual(saved['launcher_background_visibility'],52)
                    self.assertEqual(saved['launcher_labels'],{'names':False,'hotkeys':False})
                    self.assertEqual(saved['design'],'modern');self.assertEqual(saved['mode'],'light');self.assertEqual(saved['unrelated'],'preserved')
                    for style in runtime.DESIGNS:
                        page.design.setCurrentIndex(page.design.findData(style))
                        self.assertEqual(page.labels,{'names':False,'hotkeys':False});self.assertEqual(page.visibility,52)
                finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_conflicting_background_keeps_draft_until_user_resolves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'theme.json';state.write_text(json.dumps({'design':'breakpoint','mode':'dark'}))
            with patch.object(runtime,'STATE',state),patch.object(theme_page.backend,'theme_token',side_effect=lambda:state.read_text()),patch.object(theme_page.backend,'apply_mode') as apply:
                page=app.ThemePage(lambda fn,done,failed:done(fn()))
                try:
                    page.refresh();page.set_background('mine.png');page.set_visibility(42)
                    saved=json.loads(state.read_text());saved['launcher_background']='other.png';state.write_text(json.dumps(saved))
                    page.save_mode();apply.assert_not_called();self.assertEqual(page.background,'mine.png')
                    self.assertFalse(page.conflict_actions.isHidden())
                    page.resolve_conflicts('saved');self.assertEqual(page.background,'other.png');self.assertEqual(page.visibility,42)
                    self.assertTrue(page.dirty);self.assertTrue(page.conflict_actions.isHidden())
                finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_menu_choice_previews_and_edits_its_own_surfaces_and_survives_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'theme.json'
            state.write_text(json.dumps({'design':'modern','mode':'dark','avatar':'auto'}))
            def save(mode,token,design,avatar,enabled,background,surfaces,launcher_style,**options):
                state.write_text(json.dumps({'design':design,'mode':mode,'avatar':avatar,
                    'launcher_wallpaper':enabled,'launcher_background':background,
                    'launcher_surfaces':surfaces,'launcher_style':launcher_style}))
                return 'new-token'
            with patch.object(runtime,'STATE',state),patch.object(theme_page.backend,'theme_token',return_value='token'),patch.object(theme_page.backend,'apply_mode',side_effect=save):
                page=app.ThemePage(lambda fn,done,failed:done(fn()))
                try:
                    page.refresh()
                    page.launcher_style.setCurrentIndex(page.launcher_style.findData('raw'))
                    self.assertTrue(page.apply.isEnabled())
                    self.assertEqual(page.design.currentData(),'modern')
                    self.assertEqual(page.start_menu_page.surface_preview.design,'raw')
                    for card in page.design_page.cards.values():self.assertEqual(card.launcher_design,'raw')
                    page.start_menu_page.opacity_controls['tile_opacity'][0].setValue(12)
                    page.set_surface('group_image','backgrounds/custom.gif')
                    self.assertEqual(page.surfaces['raw']['tile_opacity'],12)
                    self.assertEqual(page.surfaces['modern']['tile_opacity'],100)
                    page.save_mode();self.assertFalse(page.dirty)
                    page.design.setCurrentIndex(page.design.findData('raw'))
                    page.launcher_style.setCurrentIndex(page.launcher_style.findData('modern'))
                    self.assertEqual(page.start_menu_page.surface_preview.design,'modern')
                    page.reset_surfaces()
                    self.assertEqual(page.surfaces['raw']['group_image'],'backgrounds/custom.gif')
                    page.save_mode();self.assertFalse(page.dirty)
                    reopened=app.ThemePage(lambda fn,done,failed:done(fn()))
                    try:
                        reopened.refresh()
                        self.assertEqual(reopened.design.currentData(),'raw')
                        self.assertEqual(reopened.launcher_style.currentData(),'modern')
                        self.assertFalse(reopened.dirty)
                    finally:reopened.deleteLater()
                    page.launcher_style.setCurrentIndex(page.launcher_style.findData('follow'))
                    self.assertEqual(page.start_menu_page.surface_preview.design,'raw')
                    for name,card in page.design_page.cards.items():self.assertEqual(card.launcher_design,name)
                    page.design.setCurrentIndex(page.design.findData('modern'))
                    self.assertEqual(page.start_menu_page.surface_preview.design,'modern')
                finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_surfaces_remember_separate_drafts_and_saved_images_for_each_design(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'theme.json';gif=Path(directory)/'strip.gif'
            state.write_text(json.dumps({'design':'modern','mode':'dark','avatar':'auto'}))
            Image.new('RGB',(20,10),'red').save(gif,save_all=True,
                append_images=[Image.new('RGB',(20,10),'blue')],duration=80,loop=0)
            def save(mode,token,design,avatar,enabled,background,surfaces,launcher_style,**options):
                surfaces['raw']['group_image']='backgrounds/saved.gif'
                state.write_text(json.dumps({'design':design,'mode':mode,'avatar':avatar,'launcher_wallpaper':enabled,
                    'launcher_background':background,'launcher_surfaces':surfaces,'launcher_style':launcher_style}))
                return 'new-token'
            with patch.object(runtime,'STATE',state),patch.object(theme_page.backend,'theme_token',return_value='token'),patch.object(theme_page.backend,'apply_mode',side_effect=save):
                page=app.ThemePage(lambda fn,done,failed:done(fn()))
                try:
                    page.refresh();original=page.baseline
                    page.start_menu_page.opacity_controls['tile_opacity'][0].setValue(30)
                    page.start_menu_page.opacity_controls['group_opacity'][0].setValue(40)
                    page.design.setCurrentIndex(page.design.findData('raw'))
                    self.assertEqual(page.start_menu_page.opacity_controls['group_opacity'][0].value(),0)
                    with patch.object(theme_page.ImagePicker,'choose',return_value=str(gif)):page.choose_group_image()
                    self.assertEqual(page.surfaces['raw']['group_opacity'],100)
                    self.assertIsNotNone(page.start_menu_page.surface_preview.strip_image.movie)
                    page.set_surface('tile_opacity',0)
                    page.design.setCurrentIndex(page.design.findData('modern'))
                    self.assertEqual(page.start_menu_page.opacity_controls['tile_opacity'][1].text(),'30%')
                    self.assertEqual(page.start_menu_page.surface_preview.options['group_opacity'],40)
                    self.assertEqual(page.baseline,original)
                    self.assertTrue(page.dirty)
                    page.save_mode();self.assertFalse(page.dirty)
                    self.assertEqual(page.surfaces['raw']['group_image'],'backgrounds/saved.gif')
                    self.assertEqual(page.surfaces['modern']['tile_opacity'],30)
                    page.design.setCurrentIndex(page.design.findData('raw'))
                    page.reset_surfaces()
                    self.assertEqual(page.surfaces['raw']['group_image'],'')
                    self.assertEqual(page.surfaces['modern']['tile_opacity'],30)
                    before=page.choice()
                    with patch.object(theme_page.ImagePicker,'choose',return_value=''):page.choose_group_image()
                    self.assertEqual(page.choice(),before)
                finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_apps_background_picker_keeps_avatar_separate_and_tracks_saved_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'theme.json'
            state.write_text(json.dumps({'design':'modern','mode':'dark','avatar':'auto','launcher_wallpaper':False}))
            chosen=str(Path(directory)/'my-background.png');saved='backgrounds/saved-copy.png'
            def run(fn,done,failed):done(fn())
            def save(mode,token,design,avatar,enabled,background,surfaces,launcher_style,**options):
                state.write_text(json.dumps({'design':design,'mode':mode,'avatar':avatar,'launcher_wallpaper':enabled,'launcher_background':saved,'launcher_surfaces':surfaces,'launcher_style':launcher_style}))
                return 'new-token'
            with patch.object(runtime,'STATE',state),patch.object(theme_page.backend,'theme_token',return_value='token'),patch.object(theme_page.backend,'apply_mode',side_effect=save) as apply:
                page=app.ThemePage(run)
                try:
                    page.refresh()
                    with patch.object(theme_page.ImagePicker,'choose',return_value=chosen):page.choose_background()
                    self.assertTrue(page.start_menu_page.wallpaper.isChecked())
                    self.assertEqual(page.avatar,'auto')
                    page.design.setCurrentIndex(page.design.findData('raw'))
                    self.assertTrue(page.dirty);page.save_mode()
                    apply.assert_called_once_with('dark','token','raw','auto',True,chosen,runtime.launcher_surfaces(),'follow',launcher_labels={'names':True,'hotkeys':True},launcher_background_visibility=18)
                    self.assertEqual(page.background,saved)
                    self.assertFalse(page.dirty)
                    page.set_background('')
                    self.assertTrue(page.dirty)
                    self.assertEqual(page.background,'')
                    self.assertEqual(page.avatar,'auto')
                    page.start_menu_page.wallpaper.click()
                    self.assertFalse(page.backdrop)
                    choice=page.choice()
                    with patch.object(theme_page.ImagePicker,'choose',return_value=''):page.choose_background()
                    self.assertEqual(page.choice(),choice)
                finally:page.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_switch_preserves_hotkey_draft_and_original_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'theme.json'
            state.write_text(json.dumps({'design':'raw','mode':'dark'}))
            (root/'keybindings.conf').write_text('bind = SUPER, Q, exec, kitty\n')
            (root/'hyprland.conf').write_text('$mainMod = SUPER\n'+keys.SOURCE+'\n')
            store=keys.Store(root,root/'history')
            original=(root/'keybindings.conf').read_bytes()
            with patch.object(runtime,'STATE',state),patch.object(keys,'Store',return_value=store),patch.object(app,'async_run'):
                window=app.Window(visible=False)
                try:
                    editor=window.pages['hotkeys']
                    editor.fields['label'].setText('A pending edit')
                    editor.edit(refresh=False)
                    self.assertTrue(editor.dirty)
                    draft=keys.serialize(editor.records)
                    for design in ('modern','raw','modern'):
                        state.write_text(json.dumps({'design':design,'mode':'dark'}))
                        window.apply_design()
                        self.assertIs(window.pages['hotkeys'],editor)
                        self.assertTrue(editor.dirty)
                        self.assertEqual(keys.serialize(editor.records),draft)
                        self.assertEqual(window.modern_rail.isHidden(),design=='raw')
                        self.assertEqual(window.tabs.indexOf(window.home)>=0,design=='modern')
                    self.assertEqual((root/'keybindings.conf').read_bytes(),original)
                finally:
                    window.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_animated_profile_and_control_desk_exit_cleanly_in_both_designs(self):
        script='''
import json,sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import app, runtime
runtime.STATE=Path(sys.argv[1])
application=QApplication([])
runtime.install(application,app.STYLE)
app.async_run=lambda *args:None
window=app.Window('theme')
QTimer.singleShot(70,window.hide)
QTimer.singleShot(100,window.show)
QTimer.singleShot(200,application.quit)
sys.exit(application.exec())
'''
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json'
            for design in ('raw','modern'):
                state.write_text(json.dumps({'design':design,'mode':'dark','avatar':'assets/account.gif',
                    'launcher_surfaces':{name:{'group_image':'assets/account.gif','group_opacity':65} for name in runtime.DESIGNS}}))
                result=subprocess.run([sys.executable,'-c',script,str(state)],cwd=Path(app.__file__).parent,
                    env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QPA_PLATFORMTHEME':'','GSETTINGS_BACKEND':'memory'},
                    capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,(design,result.stderr))


if __name__=='__main__':unittest.main()
