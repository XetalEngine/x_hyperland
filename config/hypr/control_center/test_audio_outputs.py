"""Monitor routing uses fake cards; no test changes the host's audio profile."""
from copy import deepcopy
import itertools
import json
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import audio_backend as backend
import audio_outputs as outputs
from audio_page import AudioPage

QT = QApplication.instance() or QApplication([])


class AudioServer:
    def __init__(self):
        self.profiles = ['output:hdmi-stereo', 'output:hdmi-stereo-extra1', 'output:hdmi-stereo-extra2']
        self.card = {'index': 7, 'name': 'alsa_card.gpu', 'active_profile': self.profiles[0],
                     'properties': {'object.serial': '700', 'device.description': 'Graphics audio'},
                     'profiles': {}, 'ports': {}}
        for i, profile in enumerate(self.profiles):
            self.card['profiles'][profile] = {'sinks': 1, 'sources': 0, 'available': True, 'priority': 5900-i*100}
            self.card['ports'][f'hdmi-output-{i}'] = {
                'description': 'HDMI / DisplayPort '+str(i+1), 'type': 'HDMI', 'availability': 'available',
                'properties': {'device.product.name': 'Screen '+str(i+1)}, 'profiles': [profile]}
        self.speakers = {'index': 1, 'name': 'speakers', 'description': 'USB speakers',
                         'volume': {'mono': {'value': 32000}}, 'mute': False}
        self.microphone = {'index': 2, 'name': 'microphone', 'description': 'USB microphone',
                           'volume': {'mono': {'value': 24000}}, 'mute': False}
        self.streams = [{'index': 90, 'sink': 1, 'properties': {'object.serial': '900', 'application.name': 'Music'}}]
        self.default = 'speakers'
        self.commands = []
        self.delay = 0
        self.fail_profile = None
        self.changed_elsewhere = False

    def sink(self, i):
        return {'index': 10+i, 'name': 'monitor-'+str(i+1), 'description': 'Graphics audio',
                'properties': {'device.name': self.card['name'], 'object.serial': str(100+i)},
                'active_port': f'hdmi-output-{i}', 'ports': [{'name': f'hdmi-output-{i}'}],
                'volume': {'mono': {'value': 30000}}, 'mute': False}

    def listing(self, kind):
        if kind == 'card': return [deepcopy(self.card)]
        if kind == 'source': return [deepcopy(self.microphone)]
        if kind == 'sink-input': return deepcopy(self.streams)
        if kind == 'source-output': return []
        if kind != 'sink': raise AssertionError(kind)
        result = [deepcopy(self.speakers)]
        profile = self.card['active_profile']
        if self.delay:
            self.delay -= 1
        elif profile in self.profiles and profile != self.fail_profile:
            result.append(self.sink(self.profiles.index(profile)))
        return result

    def command(self, *args):
        if args == ('-f', 'json', 'info'):
            return json.dumps({'default_sink_name': self.default, 'default_source_name': 'microphone'})
        self.commands.append(args)
        if args[0] == 'set-card-profile':
            self.card['active_profile'] = 'pro-audio' if self.changed_elsewhere else args[2]
        elif args[0] == 'set-default-sink': self.default = args[1]
        elif args[0] == 'move-sink-input': pass
        else: raise AssertionError(args)

    def choices(self):
        return outputs.choices(self.listing('card'), self.listing('sink'))

    def choice(self, number=2):
        return next(choice for choice in self.choices() if choice['description'].startswith('Screen '+str(number)))


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.server = AudioServer()
        for name, value in [('listing', self.server.listing), ('pactl', self.server.command)]:
            mock = patch.object(backend, name, side_effect=value);mock.start();self.addCleanup(mock.stop)
        mock = patch.object(outputs.time, 'sleep');mock.start();self.addCleanup(mock.stop)

    def test_all_connected_monitors_are_listed_once_and_current_output_keeps_its_identity(self):
        choices = self.server.choices()
        self.assertEqual(len(choices), 4)
        self.assertEqual(choices[0]['name'], 'speakers')
        self.assertEqual(choices[1]['name'], 'monitor-1')
        self.assertEqual([choice['description'].split(' — ')[0] for choice in choices[1:]],
                         ['Screen 1', 'Screen 2', 'Screen 3'])
        self.assertFalse(self.server.commands)

    def test_snapshot_does_not_enable_outputs_or_change_the_default(self):
        before = deepcopy(self.server.card)
        with patch.object(backend.audio_gain, 'inspect_source', return_value={}),patch.object(backend.audio_routing,'targets',return_value={}):
            data = backend.snapshot()
        self.assertEqual(len(data['outputs']), 4)
        self.assertEqual(len(data['devices']['sink']), 2)
        self.assertEqual(data['defaults']['sink'], 'speakers')
        self.assertEqual(self.server.card, before)
        self.assertFalse(self.server.commands)

    def test_selection_waits_for_the_monitor_then_routes_current_and_future_playback(self):
        choice = self.server.choice();self.server.delay = 2
        before = deepcopy(self.server.microphone), deepcopy(self.server.speakers)
        backend.apply_output(choice)
        self.assertEqual(self.server.commands, [
            ('set-card-profile', 'alsa_card.gpu', 'output:hdmi-stereo-extra1'),
            ('set-default-sink', 'monitor-2')])
        self.assertEqual(self.server.default, 'monitor-2')
        self.assertEqual((self.server.microphone, self.server.speakers), before)

    def test_active_monitor_does_not_recreate_its_profile(self):
        backend.apply_output(self.server.choice(1))
        self.assertEqual(self.server.commands[0], ('set-default-sink', 'monitor-1'))
        self.assertNotIn('set-card-profile', [call[0] for call in self.server.commands])

    def test_ordinary_speakers_keep_the_existing_device_path(self):
        backend.apply_output(self.server.choices()[0])
        self.assertEqual(self.server.commands[0], ('set-default-sink', 'speakers'))

    def test_app_monitor_selection_moves_only_that_app_and_keeps_default(self):
        group=backend.groups(self.server.streams,'playback')[0]
        self.server.streams.append({'index':91,'sink':1,'properties':{'object.serial':'901','application.name':'Other app'}})
        backend.apply_app_output(group,self.server.choice(3))
        self.assertEqual(self.server.commands,[
            ('set-card-profile','alsa_card.gpu','output:hdmi-stereo-extra2'),
            ('move-sink-input','90','monitor-3')])
        self.assertEqual(self.server.default,'speakers')

    def test_closed_or_reused_app_stream_does_not_activate_a_profile(self):
        group=backend.groups(self.server.listing('sink-input'),'playback')[0]
        self.server.streams[0]['properties']['object.serial']='replacement'
        with self.assertRaisesRegex(ValueError,'no longer'):backend.apply_app_output(group,self.server.choice(2))
        self.assertFalse(self.server.commands)

    def test_failed_app_move_rolls_back_our_profile_change(self):
        group=backend.groups(self.server.streams,'playback')[0]
        with patch.object(backend,'apply_app',side_effect=ValueError('App closed')):
            with self.assertRaisesRegex(ValueError,'App closed'):backend.apply_app_output(group,self.server.choice(2))
        self.assertEqual(self.server.commands,[
            ('set-card-profile','alsa_card.gpu','output:hdmi-stereo-extra1'),
            ('set-card-profile','alsa_card.gpu','output:hdmi-stereo')])
        self.assertEqual(self.server.default,'speakers')

    def test_unplug_or_replaced_monitor_aborts_before_writing(self):
        choice = self.server.choice()
        port = self.server.card['ports']['hdmi-output-1']
        for change, message in [({'availability': 'not available'}, 'disconnected'),
                                ({'availability': 'available', 'properties': {'device.product.name': 'Replacement'}}, 'changed')]:
            port.update(change)
            with self.assertRaisesRegex(ValueError, message): backend.apply_output(choice)
        self.assertFalse(self.server.commands)

    def test_reused_card_name_and_index_cannot_target_a_replacement(self):
        choice = self.server.choice()
        self.server.card['properties']['object.serial'] = 'new-card'
        with self.assertRaisesRegex(ValueError, 'disconnected'): backend.apply_output(choice)
        self.assertFalse(self.server.commands)

    def test_failed_activation_restores_the_old_profile_without_routing_apps(self):
        choice = self.server.choice();self.server.fail_profile = self.server.profiles[1]
        with patch.object(outputs.time, 'monotonic', side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError, 'did not become ready'): backend.apply_output(choice)
        self.assertEqual(self.server.commands, [
            ('set-card-profile', 'alsa_card.gpu', 'output:hdmi-stereo-extra1'),
            ('set-card-profile', 'alsa_card.gpu', 'output:hdmi-stereo')])
        self.assertEqual(self.server.default, 'speakers')

    def test_failure_does_not_undo_another_controllers_profile_change(self):
        choice = self.server.choice();self.server.changed_elsewhere = True
        with self.assertRaisesRegex(ValueError, 'configuration changed'): backend.apply_output(choice)
        self.assertEqual(len(self.server.commands), 1)
        self.assertEqual(self.server.card['active_profile'], 'pro-audio')

    def test_disconnected_ports_and_unavailable_profiles_are_not_offered(self):
        self.server.card['ports']['hdmi-output-1']['availability'] = 'not available'
        self.server.card['profiles'][self.server.profiles[2]]['available'] = False
        self.assertEqual(len(self.server.choices()), 2)

    def test_a_card_that_is_off_still_offers_its_connected_monitors(self):
        self.server.card['active_profile'] = 'off'
        self.assertEqual(len(self.server.choices()), 4)
        backend.apply_output(self.server.choice(3))
        self.assertEqual(self.server.default, 'monitor-3')

    def test_profile_selection_preserves_capture_and_existing_surround(self):
        card = self.server.card;port = card['ports']['hdmi-output-1']
        card['active_profile'] += '+input:analog-stereo'
        duplex = self.server.profiles[1]+'+input:analog-stereo'
        card['profiles'][duplex] = {'sinks': 1, 'sources': 1, 'available': True, 'priority': 100}
        port['profiles'].append(duplex)
        self.assertEqual(outputs.profile_for_port(card, port), duplex)
        card['active_profile'] = 'output:hdmi-surround-extra1'
        card['profiles'][card['active_profile']] = {'sinks': 1, 'available': True, 'priority': 10}
        port['profiles'].append(card['active_profile'])
        self.assertEqual(outputs.profile_for_port(card, port), card['active_profile'])

    def test_a_monitor_port_on_an_existing_sink_uses_port_switching(self):
        port = self.server.card['ports']['hdmi-output-1'];port['profiles'] = [self.server.profiles[0]]
        sink = self.server.sink(0);sink['ports'].append({'name': 'hdmi-output-1'})
        choice = next(c for c in outputs.choices([self.server.card], [sink]) if c['description'].startswith('Screen 2'))
        selected = deepcopy(sink);selected['active_port'] = 'hdmi-output-1'
        calls = []
        seen = iter([[sink], [sink], [selected]])
        def listing(kind): return [deepcopy(self.server.card)] if kind == 'card' else next(seen)
        result = outputs.activate(choice, listing, lambda *args: calls.append(args))
        self.assertEqual(result['active_port'], 'hdmi-output-1')
        self.assertEqual(calls, [('set-sink-port', 'monitor-1', 'hdmi-output-1')])

    def test_pulseaudio_card_indices_and_list_shaped_ports_are_supported(self):
        sink = self.server.sink(0);sink['properties'] = {};sink['card'] = 7
        self.server.card['ports'] = list(outputs.entries(self.server.card['ports']).values())
        choices = outputs.choices([self.server.card], [sink])
        self.assertEqual(len(choices), 3)
        self.assertEqual(choices[0]['name'], sink['name'])


class OutputPageTests(unittest.TestCase):
    def test_both_app_mixers_show_all_monitors_and_queue_the_chosen_route(self):
        for compact in (False,True):
            with self.subTest(compact=compact):
                server=AudioServer();queued=[]
                page=AudioPage(lambda *args:queued.append(args),listen=False,compact=compact)
                self.addCleanup(page.deleteLater);self.addCleanup(page.close)
                page.data={'devices':{'sink':server.listing('sink'),'source':[]},'outputs':server.choices(),
                           'defaults':{'sink':'speakers','source':''},
                           'apps':{'playback':backend.groups(server.streams,'playback'),'recording':[]}}
                page.render();column=next(iter(page.columns.values()))
                main=page.devices['sink'][0]
                self.assertEqual(column.route.itemText(0),'System Default')
                self.assertEqual([column.route.itemText(i) for i in range(1,column.route.count())],
                                 [main.itemText(i) for i in range(main.count())])
                self.assertEqual(column.route.currentData(),backend.audio_routing.SYSTEM_DEFAULT)
                choice=server.choice(3)
                column.route.setCurrentIndex(column.route.findData(choice['name']));column.route_changed()
                self.assertEqual(len(queued),1)
                with patch.object(backend,'apply_app_output') as select:
                    queued[0][0]();self.assertEqual(select.call_args.args[1],choice)

    def test_monitor_selection_is_queued_and_does_not_send_stale_volume(self):
        server = AudioServer();queued = []
        page = AudioPage(lambda *args: queued.append(args), listen=False)
        self.addCleanup(page.deleteLater);self.addCleanup(page.close)
        page.data = {'devices': {'sink': server.listing('sink'), 'source': []},
                     'defaults': {'sink': 'speakers', 'source': ''}, 'apps': {'playback': [], 'recording': []},
                     'outputs': server.choices()}
        page.render();combo, volume, _, mute = page.devices['sink']
        self.assertEqual(combo.count(), 4)
        self.assertEqual(combo.currentData(), 'speakers')
        self.assertEqual(queued, [])
        volume.setValue(70);self.assertTrue(volume.delay.isActive())
        choice = server.choice()
        combo.setCurrentIndex(combo.findData(choice['name']));combo.activated.emit(combo.currentIndex())
        self.assertFalse(volume.delay.isActive());self.assertFalse(volume.isEnabled());self.assertFalse(mute.isEnabled())
        self.assertEqual(len(queued), 1)
        with patch.object(backend, 'apply_output') as select:
            queued[0][0]();select.assert_called_once_with(choice)
        self.assertEqual(page.devices['source'][0].count(), 1)
        self.assertIsNone(page.devices['source'][0].currentData())

    def test_card_hotplug_events_schedule_an_inventory_refresh(self):
        page = AudioPage(lambda *args: None, listen=False)
        self.addCleanup(page.deleteLater);self.addCleanup(page.close)
        page.active = True
        with patch.object(page.events, 'readAllStandardOutput', return_value=b"Event 'change' on card #7\n"):
            page.audio_events()
        self.assertTrue(page.refresh_delay.isActive())


if __name__ == '__main__': unittest.main()
