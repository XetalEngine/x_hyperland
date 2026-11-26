"""Following the main output and pinned app choices are different intentions."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
import audio_backend as backend
import audio_routing as routing
from audio_page import AudioPage

QT=QApplication.instance() or QApplication([])


def devices():
    return [{'index':1,'name':'speakers','description':'Speakers','properties':{'object.id':'31','object.serial':'101'}},
            {'index':2,'name':'headphones','description':'Headphones','properties':{'object.id':'32','object.serial':'102'}}]


def stream():
    return {'index':90,'sink':1,'source':2,'client':10,
            'properties':{'object.id':'40','object.serial':'900','application.id':'music','application.name':'Music'}}


class RoutingTests(unittest.TestCase):
    def test_new_stream_and_explicit_default_marker_follow_main(self):
        for metadata in ({},{'40':{'target.node':'-1'}},{'40':{'target.object':'-1','target.node':'32'}}):
            self.assertEqual(routing.selection(stream(),'sink',devices(),'speakers',metadata),routing.SYSTEM_DEFAULT)

    def test_pin_to_current_default_is_not_mistaken_for_following(self):
        self.assertEqual(routing.selection(stream(),'sink',devices(),'speakers',{'40':{'target.object':'101'}}),'speakers')
        self.assertEqual(routing.selection(stream(),'sink',devices(),'headphones',{'40':{'target.node':'31'}}),'speakers')

    def test_client_target_elsewhere_unknown_metadata_and_missing_device_are_honest(self):
        selected=stream();selected['properties']['target.object']='headphones'
        self.assertEqual(routing.selection(selected,'sink',devices(),'speakers',{}),'headphones')
        self.assertEqual(routing.selection(selected,'sink',devices(),'headphones',{}),routing.SYSTEM_DEFAULT)
        self.assertEqual(routing.selection(stream(),'sink',devices(),'speakers',None),'speakers')
        self.assertEqual(routing.selection(stream(),'sink',devices(),'speakers',{'40':{'target.object':'999'}}),'unavailable:999')

    def test_metadata_parser_uses_only_default_routing_keys(self):
        payload=[{'type':'PipeWire:Interface:Metadata','props':{'metadata.name':'default'},'metadata':[
            {'subject':40,'key':'target.object','value':101},
            {'subject':40,'key':'target.node','value':-1},
            {'subject':0,'key':'default.audio.sink','value':{'name':'speakers'}}]}]
        with patch.object(routing.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(payload))) as run:
            self.assertEqual(routing.targets(),{'40':{'target.object':'101','target.node':'-1'}})
            self.assertEqual(run.call_args.args[0],['pw-dump','-N','default'])

    def test_system_default_resolves_at_the_server_and_keeps_other_streams(self):
        selected=stream();other=copy.deepcopy(selected);other['index']=91;other['properties']['object.serial']='901'
        group=backend.groups([selected],'playback')[0]
        with patch.object(backend,'listing',return_value=[selected,other]),patch.object(backend,'pactl') as command:
            backend.apply_app(group,'device',routing.SYSTEM_DEFAULT)
            command.assert_called_once_with('move-sink-input','90','@DEFAULT_SINK@')

    def test_explicit_choice_pins_with_serial_and_never_changes_default(self):
        selected=stream();group=backend.groups([selected],'playback')[0]
        def listing(kind):return devices() if kind=='sink' else [selected]
        with patch.object(backend,'listing',side_effect=listing),patch.object(backend,'pactl') as pulse,\
             patch.object(routing.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as command:
            backend.apply_app(group,'device','speakers')
            self.assertEqual(command.call_args.args[0],['pw-metadata','-n','default','40','target.object','101','Spa:Id'])
            pulse.assert_not_called()

    def test_recycled_node_is_not_pinned(self):
        selected=stream();replacement=copy.deepcopy(selected);replacement['properties']['object.serial']='new'
        seen=iter([[selected],devices(),[replacement]])
        with patch.object(backend,'listing',side_effect=lambda _:next(seen)),patch.object(routing,'pin') as pin:
            self.assertEqual(backend.apply_app(backend.groups([selected],'playback')[0],'device','speakers'),0)
            pin.assert_not_called()

    def test_main_device_change_does_not_issue_per_app_moves(self):
        with patch.object(backend,'listing',return_value=devices()),patch.object(backend,'pactl') as command:
            backend.apply_device('sink',devices()[1],'default',None)
            command.assert_called_once_with('set-default-sink','headphones')


class RoutingUiTests(unittest.TestCase):
    def test_both_mixers_follow_default_then_display_and_clear_an_override(self):
        for compact in (False,True):
            with self.subTest(compact=compact):
                queued=[];page=AudioPage(lambda *args:queued.append(args),listen=False,compact=compact)
                self.addCleanup(page.deleteLater);self.addCleanup(page.close)
                page.data={'devices':{'sink':devices(),'source':[]},'defaults':{'sink':'speakers','source':''},
                    'routes':{},'apps':{'playback':backend.groups([stream()],'playback'),'recording':[]}}
                page.render();column=next(iter(page.columns.values()))
                self.assertEqual(column.route.currentText(),'System Default')
                self.assertIn('Speakers',column.route.toolTip());self.assertFalse(queued)
                page.data['routes']={'40':{'target.object':'101'}};page.render()
                self.assertEqual(column.route.currentData(),'speakers')
                page.data['defaults']['sink']='headphones';page.render()
                self.assertEqual(column.route.currentData(),'speakers')
                column.route.setCurrentIndex(column.route.findData(routing.SYSTEM_DEFAULT));column.route_changed()
                with patch.object(backend,'apply_app') as write:
                    queued.pop()[0]();self.assertEqual(write.call_args.args[1:],('device',routing.SYSTEM_DEFAULT))
                page.data['routes']={'40':{'target.object':'-1'}};page.render()
                self.assertEqual(column.route.currentText(),'System Default')
                self.assertIn('Headphones',column.route.toolTip())


if __name__=='__main__':unittest.main()
