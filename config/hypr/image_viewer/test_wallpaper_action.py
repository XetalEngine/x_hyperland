"""Wallpaper context action with isolated files and mocked desktop changes."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QColor,QImage
from PyQt6.QtWidgets import QApplication,QDialog,QWidget
import wallpaper_action as action

QT=QApplication.instance() or QApplication([])


def immediate(fn,done,failed,**_):
    try: result=fn()
    except Exception as error: failed(str(error))
    else: done(result)


class WallpaperActionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'my # image.png'
        self.image=QImage(80,60,QImage.Format.Format_RGB32)
        self.image.fill(QColor('navy'));self.image.setPixelColor(0,0,QColor('red'))
        self.image.save(str(self.source))
        self.before=self.source.read_bytes()
        self.owner=QWidget();self.flow=action.WallpaperAction(self.owner)
        self.messages=[];self.flow.message.connect(self.messages.append)
        self.models=[dict(name='DP-1',enabled=True,mirror=''),dict(name='DP-2',enabled=True,mirror='')]
        self.current={'DP-1':{'path':'/old/one.png'},'DP-2':{'path':'/old/two.png'}}
        self.apply=self.enterContext(patch.object(action.backend,'apply_wallpapers'))
        self.enterContext(patch.object(action.settings,'monitors',return_value=[]))
        self.models_query=self.enterContext(patch.object(action.settings,'display_models',return_value=self.models))
        self.enterContext(patch.object(action.backend,'read_wallpapers',return_value=copy.deepcopy(self.current)))
        self.enterContext(patch.object(self.flow.jobs,'run',side_effect=immediate))

    def tearDown(self):
        self.flow.shutdown();self.owner.deleteLater();QT.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertEqual(self.source.read_bytes(),self.before)

    def test_one_display_applies_rotated_copy_without_picker(self):
        self.models_query.return_value=self.models[:1]
        copies=[]
        def applied(draft,current):
            self.assertEqual(set(draft),{'DP-1'});self.assertEqual(current,self.current)
            choice=draft['DP-1'];self.assertEqual(choice['original'],str(self.source))
            copy=QImage(choice['path']);self.assertEqual((copy.width(),copy.height()),(60,80))
            self.assertEqual(copy.pixelColor(59,0),QColor('red'));copies.append(choice['path'])
        self.apply.side_effect=applied
        with patch.object(action,'ScreenPicker') as picker:
            self.flow.start(self.source,self.image,90);picker.assert_not_called()
        self.apply.assert_called_once();self.assertFalse(self.flow.busy)
        self.assertIsNone(self.flow.temporary);self.assertFalse(Path(copies[0]).exists())
        self.assertIn('Wallpaper applied to DP-1.',self.messages)

    def test_multiple_displays_apply_only_clicked_screen(self):
        with patch.object(action,'ScreenPicker') as picker:
            picker.return_value.exec.return_value=QDialog.DialogCode.Accepted
            picker.return_value.selected=self.models[1]
            self.flow.start(self.source,self.image)
            picker.assert_called_once();self.assertEqual(picker.call_args.kwargs['cancel_text'],'Back to image')
            self.assertEqual(set(self.apply.call_args.args[0]),{'DP-2'})
            self.assertEqual(self.apply.call_args.args[1],self.current)

    def test_cancel_cleans_staged_copy_without_applying(self):
        with patch.object(action,'ScreenPicker') as picker:
            picker.return_value.exec.return_value=QDialog.DialogCode.Rejected
            self.flow.start(self.source,self.image)
            path=picker.call_args.args[2].path
        self.apply.assert_not_called();self.assertFalse(Path(path).exists())
        self.assertFalse(self.flow.busy);self.assertEqual(self.messages[-1],'')

    def test_mirrored_and_disabled_outputs_do_not_force_picker(self):
        self.models_query.return_value=[*self.models[:1],dict(self.models[1],mirror='DP-1'),
                                       dict(name='DP-3',enabled=False,mirror='')]
        with patch.object(action,'ScreenPicker') as picker:
            self.flow.start(self.source,self.image);picker.assert_not_called()
        self.assertEqual(set(self.apply.call_args.args[0]),{'DP-1'})

    def test_no_display_or_failed_save_cleans_up_and_keeps_action_retryable(self):
        self.models_query.return_value=[]
        self.flow.start(self.source,self.image)
        self.apply.assert_not_called();self.assertIn('No active display',self.messages[-1])
        self.assertFalse(self.flow.busy);self.assertIsNone(self.flow.temporary)
        self.models_query.return_value=self.models[:1]
        self.apply.side_effect=ValueError('DP-1 disconnected')
        self.flow.start(self.source,self.image)
        self.assertIn('DP-1 disconnected',self.messages[-1])
        self.assertFalse(self.flow.busy);self.assertIsNone(self.flow.temporary)


if __name__=='__main__':unittest.main()
