import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import projects_model as model
import launch


class CatalogTests(unittest.TestCase):
    def test_minimal_login_environment_gives_dashboard_a_real_interpreter(self):
        command=launch.command_for('projects',{'width':1280,'scale':1})
        environment=dict(os.environ);environment.pop('PATH',None)
        result=subprocess.run([*command[:3],'-c','import sys; print(sys.executable)'],env=environment,
                              capture_output=True,text=True,check=True)
        self.assertTrue(Path(result.stdout.strip()).is_absolute())
        self.assertTrue(Path(result.stdout.strip()).is_file())

    def test_portable_catalog_preserves_community_artwork(self):
        entries=model.catalog()
        self.assertEqual({p.id for p in entries},{'echo','binaryknife','linuxstudio','cachyostools','xmusic','xvideo'})
        hashes=json.loads((model.ROOT/'assets/projects/SOURCE.json').read_text())['sha256']
        for p in entries:
            self.assertEqual(hashlib.sha256(p.icon.read_bytes()).hexdigest(),hashes[p.icon.name])
            self.assertEqual(p.url,'https://www.xetal.net/community/site/?p='+p.id)

    def test_catalog_rejects_foreign_links_and_asset_traversal(self):
        original=json.loads((model.ROOT/'projects.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for changes in [{'url':'file:///etc/passwd'},{'url':'https://example.com/?p=echo'},
                            {'icon':'../private.png'},{'id':'../echo'},{'accent':'not-a-color'}]:
                items=[dict(original[0],**changes)]
                (root/'projects.json').write_text(json.dumps(items))
                with self.assertRaises(ValueError):model.catalog(root)

    def test_click_hides_dashboard_before_opening_exact_page(self):
        calls=[];environment={'HYPRLAND_INSTANCE_SIGNATURE':'test'};project=model.catalog()[0]
        with patch.object(model,'hide_dashboard',side_effect=lambda:calls.append('hide')),patch.object(model.subprocess,'Popen',side_effect=lambda *a,**k:calls.append((a,k))):
            model.open_project(project,environment)
        self.assertEqual(calls[0],'hide')
        self.assertEqual(calls[1][0][0],['xdg-open',project.url])
        self.assertEqual(calls[1][1]['env'],environment)
        self.assertNotIn('shell',calls[1][1])

    def test_hide_never_opens_an_already_hidden_workspace(self):
        for name,focused,expected in [('special:xetal-startup',True,2),('',True,1),('special:other',True,1),('special:xetal-startup',False,1)]:
            monitor={'focused':focused,'specialWorkspace':{'name':name}}
            with patch.object(model.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,json.dumps([monitor])),subprocess.CompletedProcess([],0,'ok')]) as run:
                model.hide_dashboard();self.assertEqual(run.call_count,expected)

    def test_dashboard_upgrade_reuses_three_consoles(self):
        monitors=[{'name':'test','focused':True,'width':1280,'scale':1,'specialWorkspace':{'name':launch.WORKSPACE}}]
        clients=[{'class':'xetal-startup-'+m,'mapped':True,'address':str(i)} for i,m in enumerate(('info','matrix','clock','hero'))]
        calls=[]
        def ctl(*args,**kwargs):
            calls.append(args)
            if args[0]=='monitors':return monitors
            if args[0]=='clients':return clients
            if args[:2]==('dispatch','exec'):clients.append({'class':'xetal-startup-projects','mapped':True,'address':'new'})
            return 'ok'
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'hypr/test').mkdir(parents=True)
            with patch.dict(os.environ,{'XDG_RUNTIME_DIR':directory,'HYPRLAND_INSTANCE_SIGNATURE':'test'}),patch.object(sys,'argv',['launch.py']),patch.object(launch,'ctl',side_effect=ctl),patch.object(launch.time,'sleep'):
                launch.main()
        executed=[c for c in calls if c[:2]==('dispatch','exec')]
        self.assertEqual(len(executed),1);self.assertIn('projects.py',executed[0][2])
        self.assertIn(('dispatch','closewindow','address:3'),calls)
        self.assertNotIn(('dispatch','togglespecialworkspace','xetal-startup'),calls)


class GalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_login_checkbox_shares_startup_setting_and_rolls_back_failed_saves(self):
        import projects
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, XETAL_HYPR_ROOT=directory):
            window=projects.Dashboard(model.catalog())
            self.assertTrue(window.login_toggle.isChecked())
            window.login_toggle.setChecked(False)
            self.assertFalse(projects.login_settings.enabled())
            with patch.object(sys,'argv',['launch.py','--login']),patch.object(launch,'ctl') as ctl:
                launch.main();ctl.assert_not_called()
            projects.login_settings.save(True)  # The existing Control Panel toggle.
            window.set_motion(True)
            self.assertTrue(window.login_toggle.isChecked())
            with patch.object(projects.login_settings,'save',side_effect=OSError('Read-only settings')):
                window.login_toggle.setChecked(False)
            self.assertTrue(window.login_toggle.isChecked())
            self.assertIn('Could not save',window.login_status.text())
            window.close()

    def test_all_icons_render_and_small_layout_scrolls_without_overlap(self):
        import projects
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        with patch.object(projects.theme_runtime,'state',return_value={'design':'breakpoint','mode':'dark'}):
            self.app.setPalette(projects.theme_runtime.palette())
            window=projects.Dashboard(model.catalog());window.show()
            for width,height,columns in [(1120,820,3),(600,500,2),(400,450,1)]:
                window.resize(width,height)
                for _ in range(4):self.app.processEvents();window.fit_gallery()
                self.assertEqual(window.gallery.columns,columns)
                buttons=window.gallery.buttons
                for b in buttons:
                    self.assertFalse(b.pixmap.isNull());self.assertGreaterEqual(b.pixmap.width(),256)
                    self.assertGreaterEqual(b.height(),205)
                for i,b in enumerate(buttons):
                    for other in buttons[i+1:]:self.assertFalse(b.geometry().intersects(other.geometry()))
                self.assertFalse(window.grab().isNull())
            button=window.gallery.buttons[0]
            with patch.object(window,'run_action') as action:
                button.setFocus();QTest.keyClick(button,Qt.Key.Key_Return)
                action.assert_called_once_with('--open','echo')
            window.set_motion(False);self.assertFalse(window.motion.isActive())
            window.set_motion(True);self.assertTrue(window.motion.isActive())
            window.close()

    def test_motion_changes_projection_without_moving_click_targets(self):
        import projects
        button=projects.ProjectCube(model.catalog()[0],0);button.resize(320,300);button.show();self.app.processEvents()
        geometry=button.geometry();button.advance(0);first=button.grab().toImage();button.advance(3);second=button.grab().toImage()
        self.assertNotEqual(first,second);self.assertEqual(button.geometry(),geometry);button.close()

    def test_tour_and_feedback_are_separate_accessible_actions(self):
        import projects
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, XETAL_HYPR_ROOT=directory):
            window=projects.Dashboard(model.catalog());window.show()
            for width,height,stacked in [(1200,900,False),(600,700,True),(400,700,True),(1000,800,False)]:
                window.resize(width,height)
                for _ in range(5):self.app.processEvents()
                self.assertEqual(window.intro_stacked,stacked)
                self.assertEqual(len(window.gallery.buttons),6)
                self.assertFalse(window.tour_button.geometry().intersects(window.feedback_button.geometry()))
                for button in (window.tour_button,window.feedback_button):
                    self.assertTrue(button.isVisible())
                    self.assertGreaterEqual(button.height(),30)
            for button,flag in [(window.tour_button,'--tour'),(window.feedback_button,'--feedback')]:
                with patch.object(window,'run_action') as action:
                    button.setFocus();QTest.keyClick(button,Qt.Key.Key_Space)
                    action.assert_called_once_with(flag)
            window.close()

    def test_welcome_actions_start_even_when_python_executable_is_empty(self):
        import projects
        window=projects.Dashboard(model.catalog())
        try:
            with patch.object(projects.sys,'executable',''),patch.object(window.worker,'start') as start:
                for args in [('--tour',),('--feedback',),('--open','echo')]:
                    window.run_action(*args)
                    self.assertEqual(start.call_args.args,('/usr/bin/python3',[str(projects.ROOT/'projects.py'),*args]))
        finally:window.close()


if __name__=='__main__':unittest.main()
