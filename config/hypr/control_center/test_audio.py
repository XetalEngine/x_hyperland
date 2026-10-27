import copy
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt,QPoint,QPointF
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import audio_backend as backend
from audio_page import AudioPage
import app

QT=QApplication.instance() or QApplication([])
QT.setStyle('Fusion');QT.setStyleSheet(app.STYLE)


def stream(index,name='Echo',left=65536,right=32768,kind='playback'):
    return {'index':index,'client':index//10,'sink':1,'source':2,'mute':False,'corked':False,
            'channel_map':'front-left,front-right',
            'volume':{'front-left':{'value':left},'front-right':{'value':right}},
            'properties':{'application.name':name,'application.id':name.lower(),
                          'object.serial':str(1000+index),'media.name':name+' audio'}}


def fixture(count=7):
    sink={'index':1,'name':'speakers','description':'Studio speakers','volume':{'mono':{'value':43909}}}
    source={'index':2,'name':'microphone','description':'Desk microphone','volume':{'mono':{'value':65536}}}
    return {'devices':{'sink':[sink],'source':[source]},'defaults':{'sink':'speakers','source':'microphone'},
            'apps':{'playback':backend.groups([stream(10+n,['Echo','Browser','Music','Game','Video player','Editor','Other app'][n]) for n in range(count)],'playback'),
                    'recording':backend.groups([stream(90)],'recording')}}


def immediate(fn,done,failed):
    try:result=fn()
    except Exception as error:failed(str(error))
    else:done(result)


class BackendTests(unittest.TestCase):
    def test_multiple_streams_are_one_app_and_meter_probes_are_hidden(self):
        probe=stream(33,'PulseAudio Volume Control');probe['properties'].update({'application.id':'org.PulseAudio.pavucontrol','media.name':'Peak detect'})
        grouped=backend.groups([stream(10),stream(11),stream(20,'Browser'),probe],'playback')
        self.assertEqual([g['name'] for g in grouped],['Browser','Echo'])
        self.assertEqual(len(grouped[1]['streams']),2)

    def test_volume_changes_preserve_channel_and_stream_balance(self):
        streams=[stream(10),stream(11,left=32768,right=16384)]
        group=backend.groups(streams,'playback')[0]
        with patch.object(backend,'listing',return_value=streams),patch.object(backend,'pactl') as command:
            backend.apply_app(group,'volume',50)
        self.assertEqual([call.args for call in command.call_args_list],
                         [('set-sink-input-volume','10','32768','16384'),('set-sink-input-volume','11','16384','8192')])

    def test_reused_stream_index_is_not_changed(self):
        original=stream(10);reused=stream(10);reused['properties']['object.serial']='new-stream'
        group=backend.groups([original],'playback')[0]
        with patch.object(backend,'listing',return_value=[reused]),patch.object(backend,'pactl') as command:
            with self.assertRaisesRegex(ValueError,'no longer'):backend.apply_app(group,'mute',True)
            command.assert_not_called()

    def test_recording_mute_and_route_target_only_selected_application(self):
        selected=stream(10);other=stream(20,'Browser');group=backend.groups([selected],'recording')[0]
        def listing(kind):return [{'name':'mic-two'}] if kind=='source' else [selected,other]
        with patch.object(backend,'listing',side_effect=listing),patch.object(backend,'pactl') as command:
            backend.apply_app(group,'mute',True);backend.apply_app(group,'device','mic-two')
        self.assertEqual([call.args for call in command.call_args_list],
                         [('set-source-output-mute','10','1'),('move-source-output','10','mic-two')])

    def test_closed_stream_during_write_is_not_retried(self):
        original=stream(10);group=backend.groups([original],'playback')[0]
        with patch.object(backend,'listing',side_effect=[[original],[]]),patch.object(backend,'pactl',side_effect=RuntimeError('No such entity')) as command:
            self.assertEqual(backend.apply_app(group,'mute',True),0)
            self.assertEqual(command.call_count,1)

    def test_unplugged_route_stops_before_any_write(self):
        original=stream(10);group=backend.groups([original],'playback')[0]
        with patch.object(backend,'listing',side_effect=[[original],[]]),patch.object(backend,'pactl') as command:
            with self.assertRaisesRegex(ValueError,'disconnected'):backend.apply_app(group,'device','gone')
            command.assert_not_called()


class MixerTests(unittest.TestCase):
    def setUp(self):
        self.data=fixture();self.snapshot=patch.object(backend,'snapshot',side_effect=lambda:copy.deepcopy(self.data));self.snapshot.start()
        self.action=patch.object(backend,'apply_app',return_value=1);self.apply=self.action.start()
        self.device=patch.object(backend,'apply_device');self.change_device=self.device.start()
        self.page=AudioPage(immediate,listen=False);self.page.resize(1140,650);self.page.show();self.page.refresh();QTest.qWait(30)
    def tearDown(self):
        self.page.close();self.page.deleteLater();QTest.qWait(10)
        self.snapshot.stop();self.action.stop();self.device.stop()

    def test_horizontal_overflow_wheel_scroll_and_refresh_are_read_only(self):
        bar=self.page.scroll.horizontalScrollBar();self.assertGreater(bar.maximum(),0)
        viewport=self.page.scroll.viewport();pos=QPointF(viewport.rect().center())
        event=QWheelEvent(pos,QPointF(viewport.mapToGlobal(pos.toPoint())),QPoint(),QPoint(0,-120),
                         Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(viewport,event);self.assertGreater(bar.value(),0)
        before=bar.value();self.page.refresh();self.assertEqual(bar.value(),before)
        self.apply.assert_not_called();self.change_device.assert_not_called()
        self.assertTrue(all(c.volume.orientation()==Qt.Orientation.Vertical for c in self.page.columns.values()))

    def test_keyboard_fader_and_mute_update_the_correct_app(self):
        column=next(iter(self.page.columns.values()));name=column.group['name']
        column.volume.setFocus();QTest.keyClick(column.volume,Qt.Key.Key_Down);QTest.qWait(160)
        self.assertEqual(self.apply.call_args.args[0]['name'],name)
        self.assertEqual(self.apply.call_args.args[1:],('volume',99))
        QTest.mouseClick(column.mute,Qt.MouseButton.LeftButton)
        self.assertEqual(self.apply.call_args.args[0]['name'],name)
        self.assertEqual(self.apply.call_args.args[1:],('mute',True))

    def test_refresh_preserves_drag_and_removes_closed_apps(self):
        key,column=next(iter(self.page.columns.items()));column.volume.setSliderDown(True);column.volume.setValue(72)
        self.page.refresh();self.assertIs(self.page.columns[key],column);self.assertEqual(column.volume.value(),72)
        column.volume.delay.stop();column.volume.blockSignals(True);column.volume.setSliderDown(False);column.volume.blockSignals(False)
        self.data['apps']['playback']=[g for g in self.data['apps']['playback'] if g['key']!=key[1]]
        self.page.refresh();self.assertNotIn(key,self.page.columns)

    def test_recording_and_empty_states_stay_in_audio_tab(self):
        self.page.modes.setCurrentIndex(1);self.assertEqual(len(self.page.columns),1)
        self.assertEqual(next(iter(self.page.columns.values())).group['kind'],'recording')
        self.data['apps']['recording']=[];self.page.refresh()
        self.assertFalse(self.page.columns);self.assertTrue(self.page.empty.isVisible())
        self.assertIn('No apps are recording',self.page.empty.text())

    def test_stale_async_read_cannot_overwrite_pending_changes(self):
        queued=[];self.page.async_run=lambda fn,done,failed:queued.append((fn,done,failed))
        self.page.refresh();old_read=queued.pop(0)
        group=next(iter(self.page.columns.values())).group
        self.page.app_action(copy.deepcopy(group),'volume',32)
        old_read[1](fixture(1));self.assertEqual(len(self.page.columns),7)
        self.page.app_action(copy.deepcopy(group),'volume',50)
        self.page.app_action(copy.deepcopy(group),'volume',65)
        self.assertEqual(len(self.page.pending),1)
        queued.pop(0)[1](1);pending=queued.pop(0);pending[0]();pending[1](1)
        self.assertEqual(self.apply.call_args.args[-1],65)
        if queued:queued.pop(0)[1](self.data)


if __name__=='__main__':unittest.main(verbosity=2)
