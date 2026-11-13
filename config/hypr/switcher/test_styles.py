"""Real Qt rendering/lifecycle tests, with no live compositor or configuration writes."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent, QPixmap, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QScrollArea

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from switcher import app, preferences, geometry
from switcher.scene import Scene, sample_clients, sample_pictures
from switcher.page import TaskSwitcherPage
from switcher.previews import PreviewQueue
from theme import wheel_guard

QT = QApplication.instance() or QApplication([])
QT.setStyle('Fusion'); wheel_guard.install(QT)


def synchronous(fn, done, failed):
    try: result = fn()
    except Exception as error: failed(str(error))
    else: done(result)


class SettingsTests(unittest.TestCase):
    def test_saved_style_profiles_survive_reloads_and_conflicting_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'preferences.json'
            options, token = preferences.load(path)
            options['style'] = 'ring'; options['profiles']['ring']['ring_width'] = 82
            saved, new_token = preferences.save(options, token, path)
            self.assertEqual(preferences.load(path), (saved, new_token))
            with self.assertRaisesRegex(ValueError, 'changed elsewhere'):
                preferences.save(options, token, path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_malformed_and_out_of_range_configuration_is_rejected(self):
        for value in ([], {'version': True}, {'version': 2}, {'style': 'unknown'}, {'scope': []},
                      {'duration': -1}, {'inactive_opacity': 101}, {'live_previews': 1}, {'profiles': []},
                      {'preview_fps': 0}, {'preview_fps': 145}, {'preview_fps': True}, {'preview_fps': 59.5},
                      {'profiles': {'flip': {'flip_rotation': 90}}}):
            with self.subTest(value=value), self.assertRaises(ValueError): preferences.normalize(value)

    def test_legacy_panel_opacity_is_ignored_without_resetting_saved_choices(self):
        saved = preferences.normalize({'style': 'ring', 'duration': 315, 'opacity': 47,
                                       'profiles': {'ring': {'ring_width': 82}}})
        self.assertNotIn('opacity', saved)
        self.assertEqual((saved['style'], saved['duration'], saved['profiles']['ring']['ring_width']), ('ring', 315, 82))


class GeometryTests(unittest.TestCase):
    def test_every_style_handles_empty_single_pair_and_large_window_lists(self):
        for style in preferences.STYLES:
            options = preferences.normalize({'style': style})
            self.assertEqual(geometry.layout([], 0, 0, options), [])
            for count in (1, 2, 3, 6, 17, 80):
                clients = [dict(size=[480+i*37, 300+(i%4)*100]) for i in range(count)]
                for selected in (0, count-1):
                    with self.subTest(style=style, count=count, selected=selected):
                        tiles = geometry.layout(clients, selected, selected, options)
                        self.assertIn(selected, [t.index for t in tiles])
                        self.assertEqual(len({t.index for t in tiles}), len(tiles))
                        self.assertTrue(all(0 <= t.index < count and t.width > 0 and t.height > 0 for t in tiles))
                        self.assertTrue(all(math.isfinite(n) for t in tiles for point in t.polygon() for n in point))
                        if style == 'ring': self.assertEqual(tiles[-1].index, selected)
                        if count == 2: self.assertEqual(len(tiles), 2)

    def test_cyclic_transitions_are_continuous_at_ring_boundary(self):
        options = preferences.normalize({'style': 'ring'}); clients = sample_clients()
        first = {t.index: t for t in geometry.layout(clients, -.001, 0, options)}
        last = {t.index: t for t in geometry.layout(clients, len(clients)-.001, 0, options)}
        for i in first:
            self.assertAlmostEqual(first[i].x, last[i].x); self.assertAlmostEqual(first[i].y, last[i].y)

    def test_all_styles_render_and_selected_window_is_clickable_on_small_stage(self):
        scene = Scene(); scene.resize(420, 220); clients = sample_clients()
        scene.pictures = sample_pictures(clients)
        for style in preferences.STYLES:
            scene.configure(preferences.normalize({'style': style}), clients); scene.select(1, False)
            pixmap = scene.grab(); self.assertFalse(pixmap.isNull())
            index, polygon = next((i, p) for i, p in scene.hitboxes if i == 1)
            self.assertTrue(scene.rect().contains(polygon.boundingRect().center().toPoint()))
            selected = []
            scene.activated.connect(selected.append)
            QTest.mouseClick(scene, Qt.MouseButton.LeftButton, pos=polygon.boundingRect().center().toPoint())
            self.assertEqual(selected[-1], 1, style)
            scene.activated.disconnect(selected.append)
        scene.deleteLater()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.options = preferences.normalize({})
        self.pref_patch = patch.object(preferences, 'current', return_value=self.options); self.pref_patch.start()
        self.theme_patch = patch.object(app.theme_runtime, 'install'); self.theme_patch.start()
        self.window = app.Switcher()
        self.clients = sample_clients(); self.active = self.clients[0]
        self.monitor = dict(id=0, name='test', focused=True, width=800, height=600, x=0, y=0, scale=1, reserved=[0, 32, 0, 0])
        self.calls = []
        def ctl(*args):
            self.calls.append(args)
            if args == ('-j', 'clients'): return json.dumps([{k: v for k, v in c.items() if k != '_icon'} for c in self.clients])
            if args == ('-j', 'activewindow'): return json.dumps({k: v for k, v in self.active.items() if k != '_icon'})
            if args == ('-j', 'monitors'): return json.dumps([self.monitor])
            return 'ok'
        self.ctl_patch = patch.object(app, 'ctl', side_effect=ctl); self.ctl_patch.start()

    def tearDown(self):
        self.window.hide(); self.window.queue.shutdown(); self.window.deleteLater()
        QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.ctl_patch.stop(); self.theme_patch.stop(); self.pref_patch.stop()

    def test_fast_tap_commits_once_and_cancels_delayed_position(self):
        self.window.begin(1); self.window.commit(); QTest.qWait(50)
        dispatches = [c for c in self.calls if c[0] == 'dispatch']
        self.assertEqual(dispatches, [('dispatch', 'focuswindow', 'address:0x2'),
                                      ('dispatch', 'alterzorder', 'top,address:0x2')])
        self.assertFalse(self.window.isVisible()); self.assertFalse(self.window.queue.active)
        self.window.commit()
        self.assertEqual([c for c in self.calls if c[0] == 'dispatch'], dispatches)

    def test_repeated_and_reverse_steps_then_cancel_keep_original_focus(self):
        self.window.begin(-1); self.assertEqual(self.window.index, 5)
        self.window.begin(1); self.assertEqual(self.window.index, 0)
        self.window.begin(1); self.assertEqual(self.window.index, 1)
        self.window.cancel()
        self.assertEqual(self.calls[-1], ('dispatch', 'focuswindow', 'address:0x1'))

    def test_closed_window_keeps_selected_identity_and_last_close_dismisses(self):
        self.window.begin(1)
        self.window.remove_window('0x1'); self.assertEqual(self.window.clients[self.window.index]['address'], '0x2')
        self.window.remove_window('0x2'); self.assertEqual(self.window.clients[self.window.index]['address'], '0x3')
        for client in list(self.window.clients): self.window.remove_window(client['address'])
        self.assertFalse(self.window.isVisible())

    def test_scope_filters_and_rotated_scaled_monitor_fit(self):
        self.options['scope'] = 'monitor'
        self.window.begin(); self.assertEqual({c['monitor'] for c in self.window.clients}, {0})
        self.assertLessEqual(self.window.width(), 776); self.assertLessEqual(self.window.height(), 544)
        self.window.cancel(); self.monitor.update(width=1080, height=1920, scale=1.5, transform=1)
        self.window.begin(); self.assertLessEqual(self.window.width(), 1256); self.assertLessEqual(self.window.height(), 664)
        self.options['scope'] = 'workspace'
        self.assertEqual({c['workspace']['id'] for c in app.scoped(self.clients, self.options, self.active, self.monitor)}, {1})
        self.options['scope'] = 'application'
        self.assertEqual([c['address'] for c in app.scoped(self.clients, self.options, self.active, self.monitor)], ['0x1'])

    def test_narrow_monitor_keeps_overlay_on_screen(self):
        self.options['style'] = 'static'; self.monitor.update(width=640, height=480)
        self.window.begin(); QT.processEvents()
        self.assertLessEqual(self.window.width(), 616); self.assertLessEqual(self.window.height(), 424)

    def test_empty_overlay_click_cancels_and_restores_original_window(self):
        self.window.begin(); self.window.grab()
        QTest.mouseClick(self.window.scene, Qt.MouseButton.LeftButton, pos=QPoint(3, 3))
        self.assertFalse(self.window.isVisible())
        self.assertEqual(self.calls[-1], ('dispatch', 'focuswindow', 'address:0x1'))

    def test_empty_session_does_not_show_or_capture(self):
        self.clients = []; self.active = {}; self.window.begin()
        self.assertFalse(self.window.isVisible()); self.assertFalse(self.window.queue.active)


class PageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name)/'preferences.json'
        self.path_patch = patch.object(preferences, 'PATH', self.path); self.path_patch.start()
        self.page = TaskSwitcherPage(synchronous); self.page.resize(1000, 600); self.page.show(); QTest.qWait(10)

    def tearDown(self):
        self.page.close(); self.page.deleteLater(); QT.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.path_patch.stop(); self.tmp.cleanup()

    def test_styles_remember_drafts_and_apply_is_atomic(self):
        for style in preferences.STYLES:
            self.page.style.setCurrentIndex(self.page.style.findData(style)); self.page.grab()
        self.page.style.setCurrentIndex(self.page.style.findData('ring'))
        self.page.profile_fields['ring_width'].setValue(88)
        self.page.style.setCurrentIndex(self.page.style.findData('cover'))
        self.page.style.setCurrentIndex(self.page.style.findData('ring'))
        self.assertEqual(self.page.profile_fields['ring_width'].value(), 88)
        self.assertTrue(self.page.dirty); self.assertFalse(self.path.exists())
        self.page.save(); self.assertFalse(self.page.dirty)
        self.assertEqual(preferences.load()[0]['profiles']['ring']['ring_width'], 88)
        self.assertFalse(self.page.apply.isEnabled())

    def test_wheel_on_focused_settings_scrolls_page_and_preserves_values(self):
        self.page.style.setCurrentIndex(self.page.style.findData('ring')); self.page.play.setChecked(False)
        scroll = self.page.findChild(QScrollArea)
        for field in (self.page.style, self.page.scope, self.page.fields['duration'], self.page.profile_fields['ring_width']):
            scroll.verticalScrollBar().setValue(0); field.setFocus()
            before = copy.deepcopy(self.page.draft)
            center = field.rect().center()
            event = QWheelEvent(QPointF(center), QPointF(field.mapToGlobal(center)), QPoint(), QPoint(0, -120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            QT.sendEvent(field, event)
            self.assertEqual(self.page.draft, before)
            # Header widgets have no scroll-area ancestor, but are still protected.
            if field is not self.page.style: self.assertGreater(scroll.verticalScrollBar().value(), 0)

    def test_preview_never_saves_and_stops_when_tab_is_hidden(self):
        self.page.style.setCurrentIndex(self.page.style.findData('flip'))
        self.page.open_preview(); dialog = self.page.dialogs[0]
        dialog.step(1); self.assertEqual(dialog.scene.selected, 1); self.assertFalse(self.path.exists())
        dialog.close(); self.assertEqual(self.page.dialogs, [])
        self.page.hide(); self.assertFalse(self.page.timer.isActive())
        self.page.reset(); self.assertFalse(self.page.dirty)

    def test_external_edit_conflict_preserves_draft(self):
        self.page.style.setCurrentIndex(self.page.style.findData('cover'))
        self.path.write_text('{"style":"ring"}')
        self.page.save()
        self.assertTrue(self.page.dirty); self.assertFalse(self.page.busy)
        self.assertIn('changed elsewhere', self.page.status.text())
        self.assertEqual(preferences.load()[0]['style'], 'ring')


class CaptureTests(unittest.TestCase):
    def test_capture_is_bounded_async_and_cleared_on_hide(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            helper = folder/'helper'; helper.write_text('''#!/usr/bin/python3
import time, pathlib, sys, struct, select
line = sys.stdin.readline().split()
pathlib.Path(__file__).with_name('request.txt').write_text(' '.join(line))
fps = int(line[0]); addresses = [int(v,16) for v in line[1:]]
frame = 0
while True:
    for address in addresses:
        pixels = bytes((frame%255,100,150,255))*80*50
        packet = struct.pack('<4sQIII',b'XTPF',address,80,50,len(pixels))+pixels
        sys.stdout.buffer.write(packet[:11]); sys.stdout.buffer.flush()
        sys.stdout.buffer.write(packet[11:]); sys.stdout.buffer.flush()
    frame += 1
    time.sleep(1/fps)
'''); helper.chmod(0o700)
            queue = PreviewQueue(helper=helper)
            try:
                queue.request([f'0x{i:x}' for i in range(40)])
                self.assertEqual(len(queue.wanted), 24); queue.start(30); queue.tick()
                self.assertEqual(len(queue.workers), 1)
                QTest.qWait(120); self.assertGreater(len(queue.cache), 0)
                self.assertTrue((folder/'request.txt').read_text().startswith('30 '))
                first = queue.cache['0x1'].toImage().pixelColor(0,0).blue()
                QTest.qWait(110)
                self.assertGreater(queue.cache['0x1'].toImage().pixelColor(0,0).blue(), first)
                self.assertLessEqual(len(queue.cache), 24)
                queue.stop(); self.assertEqual(len(queue.cache), 0); self.assertFalse(queue.timer.isActive())
                QTest.qWait(80); self.assertEqual(len(queue.workers), 0)
                queue.request(['0x1']); queue.start(60)
                QTest.qWait(80); self.assertIn('0x1',queue.cache)
            finally: queue.shutdown()

    def test_corrupt_stream_is_rejected_and_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp)/'helper'
            helper.write_text("#!/usr/bin/python3\nimport sys,time\nsys.stdin.readline()\nsys.stdout.buffer.write(b'BAD!'+b'x'*100);sys.stdout.buffer.flush()\ntime.sleep(4)\n")
            helper.chmod(0o700); queue = PreviewQueue(helper=helper)
            try:
                queue.request(['0x1']); queue.start(); QTest.qWait(80)
                self.assertEqual(len(queue.cache),0); self.assertEqual(len(queue.workers),0)
            finally: queue.shutdown()

    def test_legacy_preferences_default_to_60_fps(self):
        self.assertEqual(preferences.normalize({'style':'ring'})['preview_fps'],60)
        self.assertEqual(preferences.normalize({'preview_fps':120})['preview_fps'],120)


if __name__ == '__main__': unittest.main()
