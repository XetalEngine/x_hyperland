"""Real popup layout and mixer interactions; all audio operations are stubbed."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import app
import model
from protocol import Request
from PyQt6.QtCore import Qt,QPoint,QPointF
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest

sys.path.append(str(Path(__file__).resolve().parents[1]/'control_center'))
import audio_backend as backend

QT=app.QApplication.instance() or app.QApplication([])
app.runtime.install(QT)
app.wheel_guard.install(QT)


def snapshot(count):
    devices=[{'index':1,'name':'speakers','description':'Main speakers','volume':{'mono':{'value':32768}}},
             {'index':2,'name':'headset','description':'Headphones','volume':{'mono':{'value':32768}}}]
    streams=[{'index':i+10,'client':i,'sink':1,'mute':False,'corked':False,
              'properties':{'application.name':f'App {i:02d}','application.id':f'app-{i}','object.serial':str(i+100)},
              'volume':{'mono':{'value':32768}}} for i in range(count)]
    return {'devices':{'sink':devices,'source':[]},'outputs':devices,
            'defaults':{'sink':'speakers','source':''},'apps':{'playback':backend.groups(streams,'playback'),'recording':[]}}


def immediate(fn,done,failed):
    try: result=fn()
    except Exception as error: failed(str(error))
    else: done(result)


class MixerPopupTests(unittest.TestCase):
    def setUp(self):
        self.window=app.Popup('audio',preview=True)
        self.page=self.window.pages['audio'];self.page.async_run=immediate
        self.data=snapshot(10)
        self.snapshot=patch.object(backend,'snapshot',side_effect=lambda **_:copy.deepcopy(self.data));self.snapshot.start()
        self.write=patch.object(backend,'pactl');self.commands=self.write.start()
        self.addCleanup(self.snapshot.stop);self.addCleanup(self.write.stop)
        self.addCleanup(self.window.deleteLater);self.addCleanup(self.window.hide)
        monitor=dict(id=0,x=0,y=0,width=1920,height=1080,reserved=[0,40,0,0])
        self.window.present(dict(kind='audio',**model.placement(monitor,'audio',app_count=10)))
        self.page.refresh();QTest.qWait(30)

    def test_ten_apps_fit_and_main_never_scrolls_with_overflow(self):
        self.assertEqual(len(self.page.columns),10)
        self.assertEqual(self.window.width(),1896)
        self.assertEqual(self.page.scroll.horizontalScrollBar().maximum(),0)
        self.window.audio_request['width_limit']=850;self.window.fit_audio();QTest.qWait(25)
        position=self.page.master.mapTo(self.window,QPoint())
        scroll=self.page.scroll.horizontalScrollBar()
        self.assertGreater(scroll.maximum(),0)
        scroll.setValue(scroll.maximum());QT.processEvents()
        self.assertEqual(self.page.master.mapTo(self.window,QPoint()),position)
        self.assertTrue(self.page.master.isVisible())
        self.commands.assert_not_called()

    def test_popup_follows_apps_without_an_empty_column_or_scrollbar(self):
        for count,width in ((1,408),(2,590),(10,1896),(11,1896),(0,224)):
            self.data=snapshot(count);self.page.refresh();QTest.qWait(140)
            self.assertEqual(self.window.width(),width)
            self.assertEqual(len(self.page.columns),count)
            self.assertEqual(self.page.scroll.isVisible(),count>0)
            if 0<count<=10:
                self.assertEqual(self.page.scroll.horizontalScrollBar().maximum(),0)
                last=list(self.page.columns.values())[-1]
                self.assertEqual(last.mapTo(self.window,QPoint(last.width(),0)).x(),width-12)
            elif count>10:self.assertGreater(self.page.scroll.horizontalScrollBar().maximum(),0)
        self.commands.assert_not_called()

    def test_resize_waits_for_fader_release_and_open_device_menu(self):
        column=next(iter(self.page.columns.values()));column.volume.setSliderDown(True)
        self.data=snapshot(2);self.page.refresh();QTest.qWait(140)
        self.assertEqual(self.window.width(),1896)
        column.volume.blockSignals(True);column.volume.setSliderDown(False);column.volume.blockSignals(False)
        combo=self.page.devices['sink'][0];combo.showPopup();QTest.qWait(140)
        self.assertEqual(self.window.width(),1896)
        combo.hidePopup();QTest.qWait(140)
        self.assertEqual(self.window.width(),590)
        self.commands.assert_not_called()

    def test_mute_fader_and_route_use_existing_group_and_main_actions(self):
        column=next(iter(self.page.columns.values()))
        with patch.object(backend,'apply_app') as change,patch.object(backend,'apply_device') as main:
            column.mute.click()
            self.assertEqual(change.call_args.args[1:],('mute',True))
            column.volume.setValue(37);column.volume.commit()
            self.assertEqual(change.call_args.args[1:],('volume',37))
            column.route.setCurrentIndex(column.route.findData('headset'));column.route_changed()
            self.assertEqual(change.call_args.args[1:],('device','headset'))
            self.page.devices['sink'][3].click()
            self.assertEqual(main.call_args.args[0],'sink')
            self.assertEqual(main.call_args.args[2:],('mute',True))

    def test_updates_reuse_sliders_and_remove_closed_apps(self):
        key,column=next(iter(self.page.columns.items()))
        column.volume.setSliderDown(True);column.volume.setValue(73)
        self.page.refresh()
        self.assertIs(self.page.columns[key],column)
        self.assertEqual(column.volume.value(),73)
        column.volume.delay.stop();column.volume.blockSignals(True);column.volume.setSliderDown(False);column.volume.blockSignals(False)
        self.data['apps']['playback']=[g for g in self.data['apps']['playback'] if g['key']!=key[1]]
        self.page.refresh();self.assertNotIn(key,self.page.columns)
        self.data['apps']['playback']=[];self.page.refresh()
        QTest.qWait(140)
        self.assertFalse(self.page.scroll.isVisible());self.assertTrue(self.page.master.isVisible())
        self.assertEqual(self.page.status.text(),'No apps playing audio.')

    def test_wheel_scrolls_apps_without_changing_volume(self):
        self.window.audio_request['width_limit']=850;self.window.fit_audio();QTest.qWait(20)
        column=next(iter(self.page.columns.values()));before=column.volume.value()
        pos=QPointF(column.volume.rect().center())
        event=QWheelEvent(pos,QPointF(column.volume.mapToGlobal(pos.toPoint())),QPoint(),QPoint(0,-120),
                         Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QT.sendEvent(column.volume,event);QTest.qWait(120)
        self.assertEqual(column.volume.value(),before)
        self.assertGreater(self.page.scroll.horizontalScrollBar().value(),0)
        self.commands.assert_not_called()

    def test_toggle_escape_and_page_switch_stop_audio_subscription(self):
        self.window.present({'kind':'audio'})
        self.assertFalse(self.window.isVisible());self.assertFalse(self.page.active)
        self.window.present({'kind':'audio','width':1600,'height':450})
        self.page.poll.start();QTest.keyClick(self.window,Qt.Key.Key_Escape)
        self.assertFalse(self.page.poll.isActive());self.assertFalse(self.window.isVisible())
        self.window.present({'kind':'audio','width':1600,'height':450})
        self.window.present({'kind':'clock','width':370,'height':440})
        self.assertFalse(self.page.active)
        self.assertFalse(self.page.poll.isActive())

    def test_output_picker_keeps_popup_open_and_does_not_switch_by_browsing(self):
        combo=self.page.devices['sink'][0];combo.showPopup();QT.processEvents()
        self.assertTrue(self.window.dismissal_protected())
        self.commands.assert_not_called();combo.hidePopup()

    def test_lightweight_snapshot_does_not_probe_microphone_hardware(self):
        self.snapshot.stop()
        with patch.object(backend,'listing',return_value=[]) as listing,patch.object(backend,'pactl',return_value='{}'),patch.object(backend.audio_gain,'inspect_source') as gain:
            self.page.refresh()
            gain.assert_not_called()
            self.assertNotIn('source',[c.args[0] for c in listing.call_args_list])
            self.assertNotIn('source-output',[c.args[0] for c in listing.call_args_list])


class MixerPlacementTests(unittest.TestCase):
    def test_width_grows_to_ten_apps_then_uses_scrolling(self):
        monitor=dict(id=0,x=0,y=0,width=1920,height=1080,reserved=[0,40,0,0])
        self.assertEqual(model.placement(monitor,'audio',app_count=1)['width'],408)
        self.assertEqual(model.placement(monitor,'audio',app_count=10)['width'],1896)
        self.assertEqual(model.placement(monitor,'audio',app_count=30)['width'],1896)
        for count in range(11):
            result=model.placement(monitor,'audio',app_count=count)
            self.assertEqual(result['x']+result['width'],1908)

    def test_request_and_scaled_small_output_remain_in_work_area(self):
        self.assertEqual(Request().feed(b'{"kind":"audio"}\n'),{'kind':'audio'})
        monitor=dict(id=2,x=-1280,y=0,width=1920,height=1080,scale=1.5,reserved=[0,40,0,0])
        for edge in ('top','bottom'):
            result=model.placement(monitor,'audio',edge)
            self.assertLessEqual(result['width'],1256)
            self.assertGreaterEqual(result['relative_x'],0)
            self.assertGreaterEqual(result['relative_y'],40)
            self.assertLessEqual(result['relative_y']+result['height'],720)


if __name__=='__main__':unittest.main()
