"""No desktop/audio capture: geometry, preferences and synthetic media only."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recording import backend, service


class SelectionTests(unittest.TestCase):
    def test_scaled_rotated_and_negative_coordinates(self):
        monitors = [dict(name='left', x=-1920, y=180, width=1920, height=1080, scale=1),
                    dict(name='main', x=0, y=0, width=3840, height=2160, scale=2),
                    dict(name='portrait', x=1920, y=-200, width=1920, height=1080, scale=1.5, transform=1)]
        for point, name in [((-1, 200), 'left'), ((0, 200), 'main'), ((1919, 1000), 'main'),
                            ((1920, -199), 'portrait'), ((2639, 1079), 'portrait')]:
            self.assertEqual(backend.monitor_at(monitors, dict(zip(('x', 'y'), point))), name)
        with self.assertRaises(RuntimeError): backend.monitor_at(monitors, {'x': -2, 'y': 0})
        with self.assertRaises(RuntimeError): backend.monitor_at(monitors, {'x': 2640, 'y': 0})

    def test_disabled_outputs_and_invalid_pointer(self):
        monitor = dict(name='off', x=0, y=0, width=1920, height=1080, disabled=True)
        with self.assertRaises(RuntimeError): backend.monitor_at([monitor], dict(x=2, y=2))
        with self.assertRaises(ValueError): backend.monitor_at([], dict(x=float('nan'), y=2))

    def test_desktop_source_uses_output_monitor_and_microphone_uses_input(self):
        sources = [{'name': 'speakers.monitor'}, {'name': 'mic'}]
        def run(args):
            if args[-1] == 'sources': return json.dumps(sources)
            return 'speakers' if args[-1] == 'get-default-sink' else 'mic'
        with patch.object(backend, 'run', side_effect=run):
            self.assertEqual(backend.audio_source('desktop'), 'speakers.monitor')
            self.assertEqual(backend.audio_source('microphone'), 'mic')
        with patch.object(backend, 'run') as command:
            self.assertIsNone(backend.audio_source('off')); command.assert_not_called()
        with patch.object(backend, 'run', side_effect=['[]', 'missing']):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'): backend.audio_source('desktop')

    def test_failed_hardware_probe_falls_back_to_available_software(self):
        with patch.object(backend, 'run', side_effect=RuntimeError('No GPU')):
            self.assertEqual(backend.choose_encoder(backend.DEFAULTS, {'h264_nvenc', 'libopenh264'}), ('libopenh264', None))
        self.assertEqual(backend.software_encoder({'mpeg4', 'aac'}), 'mpeg4')


class PreferenceTests(unittest.TestCase):
    def test_filename_templates_and_unsafe_names(self):
        from datetime import datetime
        now=datetime(2026,11,4,15,2,9)
        self.assertEqual(backend.recording_name('Clip-{date}-{time}-{monitor}', 'DP/1', now), 'Clip-2026-11-04-15-02-09-DP_1.mp4')
        self.assertEqual(backend.recording_name('Movie.mp4'), 'Movie.mp4')
        for name in ('../movie','/absolute','bad\\name','{date.__class__}','{unknown}','{date!r}','{date:>999999}','', 'a'*201):
            with self.subTest(name=name), self.assertRaises(ValueError): backend.recording_name(name)

    def test_defaults_atomic_save_and_external_edit_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            value, token = backend.load(path)
            self.assertEqual((value['fps'], value['audio'], value['directory']), (64, 'desktop', ''))
            updated, new_token = backend.save({**value, 'fps': 30}, token, path)
            self.assertEqual(updated['fps'], 30); self.assertNotEqual(token, new_token)
            path.write_text('{"fps": 24}')
            with self.assertRaisesRegex(ValueError, 'elsewhere'): backend.save(value, new_token, path)
            self.assertEqual(json.loads(path.read_text()), {'fps': 24})

    def test_invalid_settings_do_not_change_file(self):
        for bad in ({'fps': True}, {'fps': 0}, {'fps': 241}, {'directory': 'relative'},
                    {'directory': '/tmp/bad\nname'}, {'audio': 'unknown'}, {'encoder': 'shell'}, {'unexpected': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): backend.validate(bad)


class ControlTests(unittest.TestCase):
    def test_toggle_stops_without_loading_new_preferences_or_monitor(self):
        recorder = Mock(state={'phase': 'recording'})
        with patch.object(backend, 'load') as load:
            service.dispatch(recorder, {'action': 'toggle', 'monitor': None})
            recorder.stop.assert_called_once(); recorder.start.assert_not_called(); load.assert_not_called()

    def test_saving_does_not_launch_a_second_recorder(self):
        recorder = Mock(state={'phase': 'saving'}, busy=True)
        with self.assertRaisesRegex(RuntimeError, 'being saved'): service.dispatch(recorder, {'action': 'toggle', 'monitor': 'A'})
        recorder.start.assert_not_called()

    def test_status_is_read_only_and_bar_hides_when_idle(self):
        recorder = Mock(state={'phase': 'saved', 'file': '/tmp/saved.mp4'})
        self.assertEqual(service.dispatch(recorder, {'action': 'status'}), recorder.state)
        self.assertEqual(service.bar_status(recorder.state)['text'], '')
        state = dict(phase='recording', started=time.time()-65, monitor='A', fps=64, audio='desktop')
        self.assertIn('REC 01:05', service.bar_status(state)['text'])
        self.assertIn('&lt;bad&gt;', service.bar_status({'phase': 'error', 'error': '<bad>'})['tooltip'])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required for synthetic media checks')
class MediaTests(unittest.TestCase):
    def setUp(self):
        if 'libx264' not in backend.encoders(): self.skipTest('Synthetic fixture needs libx264')
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.notifications = Mock()
        self.recorder = backend.Recorder(notify_fn=self.notifications)

    def tearDown(self):
        if hasattr(self, 'recorder'): self.recorder.shutdown(); self.tmp.cleanup()

    def fixture(self):
        path = self.root/'capture.nut'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=128x96:r=64:d=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1', '-c:v', 'libx264',
            '-preset', 'ultrafast', '-bf', '0', '-enc_time_base:v', '1:90000', '-c:a', 'aac', '-f', 'nut', str(path)], check=True, capture_output=True)
        return path

    def prepare_save(self):
        r = self.recorder; r.workspace = self.root; r.capture = self.fixture()
        r.movie = self.root/'encoding.mp4'; r.destination = self.root/'published.mp4'
        r.source = 'synthetic'; r.log = (self.root/'capture.log').open('wb')
        r.state = dict(phase='stopping', fps=64, file=str(r.destination))

    def finish(self):
        until = time.monotonic()+10
        while self.recorder.busy and time.monotonic()<until: self.recorder.tick(); time.sleep(.02)
        self.assertFalse(self.recorder.busy)

    def test_mp4_has_exact_64_fps_audio_and_decodes(self):
        self.prepare_save(); r = self.recorder
        # Published files live outside the disposable capture directory.
        r.workspace = self.root/'work'; r.workspace.mkdir()
        r.capture = self.fixture_path_move(r.capture, r.workspace/'capture.nut')
        r.close_log(); r.log = (r.workspace/'capture.log').open('wb'); r.movie = r.workspace/'encoding.mp4'
        r.begin_save(); self.finish(); self.assertEqual(r.state['phase'], 'saved')
        streams = backend.media_streams(r.destination)
        video = next(s for s in streams if s['codec_type']=='video')
        self.assertEqual(video['avg_frame_rate'], '64/1'); self.assertEqual(video['r_frame_rate'], '64/1')
        self.assertTrue(any(s['codec_type']=='audio' for s in streams))
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(r.destination), '-f', 'null', '-'], check=True, capture_output=True)
        self.assertFalse(r.workspace.exists())
        self.notifications.assert_called_once_with('Recording saved', str(r.destination), r.destination)

    @staticmethod
    def fixture_path_move(source, target): source.rename(target); return target

    def test_existing_movie_is_preserved_and_next_name_is_published(self):
        self.prepare_save(); r = self.recorder; r.destination.write_bytes(b'Existing recording')
        r.workspace=self.root/'work';r.workspace.mkdir();r.capture=self.fixture_path_move(r.capture,r.workspace/'capture.nut')
        r.close_log();r.log=(r.workspace/'capture.log').open('wb');r.movie=r.workspace/'encoding.mp4'
        r.begin_save(); self.finish()
        self.assertEqual(r.state['phase'], 'saved')
        self.assertEqual((self.root/'published.mp4').read_bytes(), b'Existing recording')
        self.assertEqual(r.destination.name, 'published (1).mp4')
        self.assertTrue(r.destination.is_file())

    def test_capture_failure_retains_diagnostic_and_no_final_movie(self):
        self.prepare_save(); r = self.recorder; r.capture.write_bytes(b'bad')
        r.begin_save()
        self.assertEqual(r.state['phase'], 'error'); self.assertFalse(r.destination.exists())
        self.assertTrue((self.root/'capture.log').exists())
        self.assertTrue(self.notifications.called)
        self.assertTrue(all(len(call.args)==2 for call in self.notifications.call_args_list))


if __name__ == '__main__': unittest.main()
