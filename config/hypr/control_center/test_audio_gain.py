"""Microphone hardware gain checks; all hardware writes use disposable fixtures."""
import copy
import ctypes as C
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import audio_gain as gain
import audio_backend as backend
from audio_page import AudioPage, MicrophoneGain

QT = QApplication.instance() or QApplication([])


def source():
    return dict(index=10, name='alsa_input.front-mic', description='Front microphone',
                active_port='analog-input-front-mic', properties={'alsa.card': '2', 'object.serial': '42'},
                volume={'mono': {'value': 65536}})


def control(name='Front Mic Boost', direction='playback', kind='boost'):
    return dict(name=name, index=0, direction=direction, kind=kind, minimum=0, maximum=3,
                value=2, channels=[(0, 2), (1, 1)], steps=[(0, 0), (1, 1000), (2, 2000), (3, 3000)],
                context=gain.source_context(source()), card=2, card_identity=('Generic', 'Example sound card'))


class FakeMixer:
    def __init__(self, controls=None):
        self.controls = controls if controls is not None else [control()]
        self.write = Mock()
        self.identity = ('Generic', 'Example sound card')
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def card_identity(self): return self.identity
    def entries(self): return [(i+1, copy.deepcopy(c)) for i, c in enumerate(self.controls)]
    def steps(self, element, item): return item['steps']


def immediate(fn, done, failed):
    try: value = fn()
    except Exception as error: failed(str(error))
    else: done(value)


class HardwareGainTests(unittest.TestCase):
    def test_alsa_card_is_not_pulseaudio_card_or_device_index(self):
        mic = source();mic['card'] = 99;mic['properties']['device.id'] = '123'
        self.assertEqual(gain.source_card(mic), 2)
        mic['properties'] = {'api.alsa.pcm.card': '5'}
        self.assertEqual(gain.source_card(mic), 5)
        mic['properties'] = {'device.id': '123'}
        self.assertIsNone(gain.source_card(mic))

    def test_monitor_and_virtual_inputs_never_open_a_hardware_mixer(self):
        monitor = source();monitor['monitor_of_sink'] = 0
        virtual = source();virtual['properties'] = {}
        with patch.object(gain, 'Mixer') as mixer:
            for mic in (monitor, virtual, None):
                self.assertFalse(gain.inspect_source(mic)['controls'])
            mixer.assert_not_called()

    def test_invalid_card_names_cannot_be_used_as_alsa_paths(self):
        for value in ('default', '-1', '2;anything', '/dev/snd/controlC2', '1.5', True):
            mic=source();mic['properties']['alsa.card']=value
            self.assertIsNone(gain.source_card(mic))

    def test_only_input_gain_not_playback_loopback_is_supported(self):
        self.assertEqual(gain.control_kind('Mic Boost', 'playback'), 'boost')
        self.assertEqual(gain.control_kind('Capture', 'capture'), 'capture')
        for name in ('Mic', 'Speaker Boost', 'Headphone Gain', 'Mic Playback Volume', 'Mic Loopback', 'Sidetone Gain'):
            self.assertIsNone(gain.control_kind(name, 'playback'))

    def test_front_and_internal_microphones_only_show_their_own_boost(self):
        controls=[control('Mic Boost'),control('Front Mic Boost'),control('Internal Mic Boost')]
        for port,expected in [('analog-input-front-mic','Front Mic Boost'),('analog-input-internal-mic','Internal Mic Boost'),('analog-input-mic','Mic Boost')]:
            result=gain.controls_for_port(controls,port)
            self.assertEqual([c['name'] for c in result],[expected])

    def test_line_in_does_not_offer_a_microphone_preamp(self):
        self.assertEqual(gain.controls_for_port([control('Mic Boost')], 'analog-input-linein'), [])

    def test_inspection_is_read_only_and_keeps_the_real_db_steps(self):
        mixer=FakeMixer()
        with patch.object(gain,'Mixer',return_value=mixer) as factory:
            state=gain.inspect_source(source())
        factory.assert_called_once_with(2);mixer.write.assert_not_called()
        self.assertEqual(state['controls'][0]['steps'],[(0,0),(1,1000),(2,2000),(3,3000)])
        self.assertEqual(gain.gain_label(-1200,4),'-12 dB')
        self.assertEqual(gain.gain_label(0,0),'0 dB')
        self.assertEqual(gain.gain_label(None,4),'Step 4')
        self.assertEqual(gain.gain_label(-9999999,0),'−∞ dB')

    def test_gain_errors_do_not_break_the_rest_of_the_mixer(self):
        with patch.object(gain,'Mixer',side_effect=gain.GainUnavailable('Permission denied')):
            state=gain.inspect_source(source())
        self.assertEqual(state['message'],'Permission denied');self.assertFalse(state['controls'])

    def test_missing_boost_and_capture_only_have_honest_explanations(self):
        with patch.object(gain,'Mixer',return_value=FakeMixer([])):
            self.assertIn('No separate boost',gain.inspect_source(source())['message'])
        with patch.object(gain,'Mixer',return_value=FakeMixer([control('Capture','capture','capture')])):
            self.assertIn('may also change',gain.inspect_source(source())['message'])

    def test_apply_reopens_and_writes_only_selected_control(self):
        mixer=FakeMixer([control('Speaker Boost'),control(),control('Mic Boost')])
        with patch.object(gain,'Mixer',return_value=mixer):gain.apply_gain(source(),control(),0)
        self.assertEqual(mixer.write.call_count,1)
        self.assertEqual(mixer.write.call_args.args[1]['name'],'Front Mic Boost')
        self.assertEqual(mixer.write.call_args.args[-1],0)

    def test_changed_port_is_rejected_before_opening_hardware(self):
        mic=source();mic['active_port']={'name':'analog-input-mic'}
        with patch.object(gain,'Mixer') as mixer:
            with self.assertRaisesRegex(ValueError,'input changed'):gain.apply_gain(mic,control(),0)
            mixer.assert_not_called()

    def test_reused_card_and_changed_range_are_rejected(self):
        for mutate in ('card','range'):
            mixer=FakeMixer()
            if mutate=='card':mixer.identity=('Other','A different USB mic')
            else:mixer.controls[0]['maximum']=4
            with patch.object(gain,'Mixer',return_value=mixer):
                with self.assertRaises(ValueError):gain.apply_gain(source(),control(),0)
            mixer.write.assert_not_called()

    def test_out_of_range_and_non_integer_values_are_rejected(self):
        with patch.object(gain,'Mixer') as mixer:
            for value in (-1,4,1.5,True):
                with self.assertRaises(ValueError):gain.apply_gain(source(),control(),value)
            mixer.assert_not_called()

    def test_disappeared_control_cannot_write_another_control(self):
        mixer=FakeMixer([control('Capture','capture','capture')])
        with patch.object(gain,'Mixer',return_value=mixer):
            with self.assertRaisesRegex(ValueError,'no longer'):gain.apply_gain(source(),control(),0)
        mixer.write.assert_not_called()

    def test_backend_refuses_reused_source_serial_or_new_input_port(self):
        for mutate in ('serial','port'):
            current=source()
            if mutate=='serial':current['properties']['object.serial']='another device'
            else:current['active_port']='analog-input-mic'
            with patch.object(backend,'listing',return_value=[current]),patch.object(gain,'apply_gain') as write:
                with self.assertRaises(ValueError):backend.apply_gain(source(),control(),0)
                write.assert_not_called()

    def test_snapshot_only_probes_the_default_microphone(self):
        another=source();another['name']='other-microphone'
        with patch.object(backend,'pactl',return_value='{"default_source_name":"alsa_input.front-mic"}'),\
             patch.object(backend,'listing',side_effect=lambda kind:[source(),another] if kind=='source' else []),\
             patch.object(gain,'inspect_source',return_value={'controls':[]}) as inspect:
            result=backend.snapshot()
        inspect.assert_called_once_with(source());self.assertIn('microphone_gain',result)

    def test_native_write_can_reduce_gain_and_preserves_channel_offsets(self):
        mixer=object.__new__(gain.Mixer);setter=Mock(return_value=0)
        mixer.lib=SimpleNamespace(snd_mixer_selem_set_playback_volume=setter)
        mixer.write(123,control(),1)
        self.assertEqual([c.args for c in setter.call_args_list],[(123,0,1),(123,1,0)])

    def test_failed_channel_write_restores_channels_already_changed(self):
        mixer=object.__new__(gain.Mixer);setter=Mock(side_effect=[0,-5,0])
        mixer.lib=SimpleNamespace(snd_mixer_selem_set_playback_volume=setter,snd_strerror=lambda _:b'Write failed')
        with self.assertRaises(gain.GainUnavailable):mixer.write(123,control(),3)
        self.assertEqual([c.args for c in setter.call_args_list],[(123,0,3),(123,1,2),(123,0,2)])

    def test_db_curve_is_queried_at_real_steps_not_interpolated(self):
        mixer=object.__new__(gain.Mixer)
        curve={0:-1200,1:0,2:2000,3:3000}
        def db_for(_element,raw,destination):destination._obj.value=curve[raw];return 0
        mixer.lib=SimpleNamespace(snd_mixer_selem_ask_playback_vol_dB=db_for)
        self.assertEqual(mixer.steps(123,control()),list(curve.items()))


class GainWidgetTests(unittest.TestCase):
    def setUp(self):
        self.widget=MicrophoneGain();self.widget.resize(540,210);self.widget.show()
        self.events=[];self.widget.changed.connect(lambda *args:self.events.append(args))
        self.state={'source':source()['name'],'controls':[control()],'message':'Lower boost if speech distorts.'}
        self.widget.set_state(self.state,source());QT.processEvents()
    def tearDown(self):
        self.widget.cancel_pending();self.widget.close();self.widget.deleteLater();QTest.qWait(5)

    def test_read_only_refresh_and_native_db_display(self):
        self.assertEqual(self.widget.slider.maximum(),3)
        self.assertEqual(self.widget.level.text(),'+20 dB')
        self.widget.set_state(self.state,source());QTest.qWait(130)
        self.assertFalse(self.events)

    def test_keyboard_can_reduce_boost(self):
        self.widget.slider.setFocus();QTest.keyClick(self.widget.slider,Qt.Key.Key_Left);QTest.qWait(150)
        self.assertEqual(self.events[-1][-1],1);self.assertEqual(self.widget.level.text(),'+10 dB')

    def test_minimum_is_an_explicit_single_write(self):
        self.widget.minimum.click();QTest.qWait(150)
        self.assertEqual(len(self.events),1);self.assertEqual(self.events[0][-1],0)
        self.assertEqual(self.widget.level.text(),'0 dB')

    def test_minimum_can_select_negative_hardware_gain(self):
        state=copy.deepcopy(self.state);item=state['controls'][0]
        item.update(minimum=-2,maximum=1,value=0,channels=[(0,0)],steps=[(-2,-2000),(-1,-1000),(0,0),(1,1000)])
        self.widget.set_state(state,source());self.widget.minimum.click()
        self.assertEqual(self.events[-1][-1],-2)
        self.assertEqual(self.widget.level.text(),'-20 dB')

    def test_switching_mics_cancels_delayed_change(self):
        self.widget.slider.setValue(1)
        mic=source();mic['properties']['object.serial']='new-microphone'
        self.widget.set_state(self.state,mic);QTest.qWait(150)
        self.assertFalse(self.events)

    def test_refresh_does_not_override_drag_or_emit_a_write(self):
        self.widget.slider.setSliderDown(True);self.widget.slider.setValue(1)
        self.widget.set_state(self.state,source())
        self.assertEqual(self.widget.slider.value(),1)
        self.widget.cancel_pending();QTest.qWait(150);self.assertFalse(self.events)

    def test_unsupported_hardware_hides_fader_and_explains(self):
        self.widget.set_state({'source':source()['name'],'controls':[],'message':'No separate boost is exposed.'},source())
        self.assertFalse(self.widget.fader.isVisible());self.assertFalse(self.widget.minimum.isVisible())
        self.assertIn('No separate boost',self.widget.help.text());self.assertFalse(self.events)

    def test_switching_controls_cancels_delayed_change(self):
        state=copy.deepcopy(self.state);other=control('Input Gain','capture');state['controls'].append(other)
        self.widget.set_state(state,source());self.widget.slider.setValue(1)
        self.widget.combo.setCurrentIndex(1);self.widget.select_control(1);QTest.qWait(150)
        self.assertFalse(self.events)


class PageGainTests(unittest.TestCase):
    def test_gain_uses_existing_queue_and_does_not_touch_output_or_apps(self):
        data={'devices':{'source':[source()],'sink':[]},'defaults':{'source':source()['name'],'sink':''},
              'apps':{'playback':[],'recording':[]},
              'microphone_gain':{'source':source()['name'],'controls':[control()],'message':'Mic boost'}}
        with patch.object(backend,'snapshot',return_value=data),patch.object(backend,'apply_gain') as write,\
             patch.object(backend,'apply_app') as app_write,patch.object(backend,'apply_device') as device_write:
            page=AudioPage(immediate,listen=False);page.show();page.refresh()
            write.assert_not_called();page.mic_gain.minimum.click()
            self.assertEqual(write.call_args.args[0]['name'],source()['name'])
            self.assertEqual(write.call_args.args[-1],0)
            app_write.assert_not_called();device_write.assert_not_called()
            page.close();page.deleteLater();QTest.qWait(10)


if __name__=='__main__':unittest.main(verbosity=2)
