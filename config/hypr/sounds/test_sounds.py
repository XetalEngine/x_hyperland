"""Settings, notification etiquette and ownership; never play real audio."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sounds import actions, model, play


class SoundTests(unittest.TestCase):
    def test_settings_conflicts_and_unrelated_fields_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            value,token=model.load(path);self.assertIsNone(token)
            value['volume']=21;value['events']['warning']=False
            saved,token=model.save(value,token,path)
            other=copy.deepcopy(saved);other['pack']='gildedhollow'
            model.save(other,token,path)
            with self.assertRaisesRegex(ValueError,'another window'):model.save(saved,token,path)
            current,_=model.load(path);self.assertEqual(current['volume'],21);self.assertFalse(current['events']['warning'])
            self.assertEqual(current['pack'],'gildedhollow')
            for changes in ({'pack':'../../something'},{'volume':101},{'volume':True},{'enabled':'true'},{'events':{'unknown':True}}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):model.validate(dict(model.DEFAULTS,**changes))

    def test_follow_theme_resolves_at_play_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'theme').mkdir()
            for pack in model.PACKS:
                (root/'theme/state.json').write_text(json.dumps({'design':pack}))
                self.assertEqual(model.resolve('follow',root),pack)
                self.assertEqual(model.resolve('raw',root),'raw')
            with self.assertRaises(ValueError):model.asset('raw','../error',root)

    def test_notification_hints_suppression_and_replacements(self):
        cases=[({},'notification'),({'SWAYNC_URGENCY':'Critical'},'error'),
            ({'SWAYNC_SOUND_NAME':'dialog-warning'},'warning'),({'SWAYNC_SOUND_NAME':'dialog-information'},'info'),
            ({'SWAYNC_SOUND_NAME':'dialog-question'},'question'),({'SWAYNC_CATEGORY':'transfer.complete'},'success'),
            ({'SWAYNC_REPLACES_ID':'32'},None),({'SWAYNC_HINT_suppress-sound':'true'},None),
            ({'SWAYNC_HINT_SUPPRESS_SOUND':'1','SWAYNC_URGENCY':'Critical'},None),
            ({'SWAYNC_SOUND_FILE':'$(touch /tmp/nope)','SWAYNC_BODY':'error; shutdown'},'notification')]
        for env,expected in cases:
            with self.subTest(env=env):self.assertEqual(play.notification_event(env),expected)

    def test_dnd_and_no_server_are_bounded(self):
        with patch.object(play.shutil,'which',return_value='/usr/bin/swaync-client'),patch.object(play.subprocess,'run') as run:
            run.return_value=subprocess.CompletedProcess([],0,'true\n','');self.assertTrue(play.do_not_disturb())
            self.assertLess(run.call_args.kwargs['timeout'],1)
            run.side_effect=subprocess.TimeoutExpired('swaync-client',.45);self.assertFalse(play.do_not_disturb())

    def test_mute_event_switch_dnd_and_preview_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(play,'session_directory',return_value=root),patch.object(play.socket,'socket'),patch.object(play.model,'load') as load, \
                 patch.object(play,'do_not_disturb',return_value=False) as dnd,patch.object(play.subprocess,'Popen') as start, \
                 patch.object(play,'command',return_value=['test-player']),patch.object(play.model,'asset',return_value=Path(__file__)):
                start.return_value.poll.return_value=0;start.return_value.returncode=0
                load.return_value=(dict(model.DEFAULTS,enabled=False),None);play.play('info');start.assert_not_called()
                load.return_value=(dict(model.DEFAULTS,events=dict(model.DEFAULTS['events'],info=False)),None);play.play('info');start.assert_not_called()
                load.return_value=(copy.deepcopy(model.DEFAULTS),None);dnd.return_value=True;play.play('info');start.assert_not_called()
                play.play('info',preview=True);start.assert_called_once();start.reset_mock()
                load.return_value=(dict(model.DEFAULTS,volume=0),None);play.play('info',preview=True);start.assert_not_called()

    def test_compositor_disconnect_stops_only_our_player_and_startup_is_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(play,'session_directory',return_value=root),patch.object(play.socket,'socket') as sock, \
                 patch.object(play.model,'load',return_value=(copy.deepcopy(model.DEFAULTS),None)),patch.object(play,'do_not_disturb',return_value=False), \
                 patch.object(play.subprocess,'Popen') as start,patch.object(play,'command',return_value=['test-player']), \
                 patch.object(play.model,'asset',return_value=Path(__file__)),patch.object(play.select,'select') as select:
                lifetime=sock.return_value.__enter__.return_value;lifetime.recv.return_value=b''
                select.return_value=([lifetime],[],[])
                child=start.return_value;child.poll.return_value=None;child.returncode=0
                play.play('startup',once=True)
                child.terminate.assert_called_once();self.assertTrue((root/'fusion-startup-sound.done').exists())
                start.reset_mock();play.play('startup',once=True);start.assert_not_called()

    def test_missing_session_never_starts_audio(self):
        with patch.dict(os.environ,{},clear=True),patch.object(play.subprocess,'Popen') as start:
            self.assertIsNone(play.session_directory());play.play('error');start.assert_not_called()

    def test_power_music_never_runs_commands_or_blocks_on_failure(self):
        with patch.object(actions.subprocess,'run') as run:
            actions.before_power(['systemctl','suspend']);actions.before_power(['hyprlock']);run.assert_not_called()
            for command in actions.EXIT_ACTIONS:
                run.reset_mock();run.side_effect=subprocess.TimeoutExpired('player',5.5)
                actions.before_power(command)
                self.assertEqual(run.call_args.args[0][-1],'shutdown')
                self.assertNotIn('poweroff',run.call_args.args[0]);self.assertEqual(run.call_args.kwargs['timeout'],5.5)


if __name__=='__main__':unittest.main()
