import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QRect, QSettings, QSize
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget
import window_size as sizes

APPLICATION = QApplication.instance() or QApplication([])


def screen(name='DP-1', width=2560, height=1440, scale=1):
    value = Mock()
    value.name.return_value = name
    value.geometry.return_value = QRect(0, 0, width, height)
    value.availableGeometry.return_value = QRect(0, 38, width, height - 38)
    value.devicePixelRatio.return_value = scale
    return value


def output(name='DP-1', width=2560, height=1440, **extra):
    return dict(name=name, width=width, height=height, scale=1, x=0, y=0,
                reserved=[0, 38, 0, 0], focused=True, **extra)


class SizeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-image-sizes-')
        self.addCleanup(temporary.cleanup)
        self.path = str(Path(temporary.name) / 'sizes.ini')
        self.settings = QSettings(self.path, QSettings.Format.IniFormat)
        self.store = sizes.Store(self.settings)
        self.large = sizes.Display.for_screen(screen(), [output()])
        self.small = sizes.Display.for_screen(screen(), [output(width=1920, height=1080)])

    def test_distinct_resolutions_and_scales_restore_independent_sizes_from_disk(self):
        scaled = sizes.Display.for_screen(screen(), [dict(output(), scale=1.25)])
        for display, size in [(self.large, QSize(1500, 1000)), (self.small, QSize(900, 650)),
                              (scaled, QSize(1100, 700))]:
            self.store.save(display, size)
        reloaded = sizes.Store(QSettings(self.path, QSettings.Format.IniFormat))
        self.assertEqual(reloaded.load(self.large), QSize(1500, 1000))
        self.assertEqual(reloaded.load(self.small), QSize(900, 650))
        self.assertEqual(reloaded.load(scaled), QSize(1100, 700))
        # Another connector with the same resolution/scale uses the same size.
        other = sizes.Display.for_screen(screen('HDMI-1'), [output('HDMI-1')])
        self.assertEqual(reloaded.load(other), QSize(1500, 1000))

    def test_restore_fits_reserved_area_including_side_panels_and_screen_edges(self):
        display = sizes.Display.for_screen(screen(), [dict(output(width=1920, height=1080),
                                                         reserved=[50, 38, 10, 20])])
        self.store.save(display, QSize(3000, 2000))
        self.assertEqual(display.area, QRect(50, 38, 1860, 1022))
        self.assertEqual(self.store.load(display), QSize(1836, 998))
        self.assertEqual(display.key, self.small.key)  # Panel changes do not lose the preference.
        self.assertEqual(sizes.Display('tiny', QRect(0, 0, 500, 350)).fit(QSize(1080, 760)), QSize(476, 326))

    def test_rotated_scaled_screen_uses_logical_area_and_oriented_resolution(self):
        display = sizes.Display.for_screen(screen(), [dict(output(), transform=1, scale=1.5)])
        self.assertEqual(display.key, '1440x2560@1.5')
        self.assertEqual(display.area.size(), QSize(960, 1669))
        self.assertEqual(display.fit(QSize(1500, 1400)), QSize(936, 1400))

    def test_old_global_size_migrates_once_without_spreading_to_other_resolutions(self):
        self.settings.setValue('size', QSize(1700, 900))
        self.assertEqual(self.store.load(self.large), QSize(1700, 900))
        self.assertFalse(self.settings.contains('size'))
        self.assertEqual(self.store.load(self.small), sizes.DEFAULT)

    def test_invalid_sizes_fall_back_without_crashing(self):
        for value in ('corrupt', QSize(-1, 0), QSize(40000, 50000), None):
            self.settings.setValue('sizes/' + self.small.key, value)
            self.assertEqual(self.store.load(self.small), sizes.DEFAULT)

    def test_launch_uses_focused_monitor_instead_of_primary(self):
        primary, focused = screen('DP-1'), screen('DP-2', 1920, 1080)
        with patch.object(sizes.QApplication, 'primaryScreen', return_value=primary):
            self.assertIs(sizes.launch_screen([primary, focused], [output('DP-2')]), focused)
            self.assertIs(sizes.launch_screen([primary, focused], []), primary)

    def test_missing_compositor_falls_back_to_qt_available_area(self):
        with patch.dict(os.environ, {'HYPRLAND_INSTANCE_SIGNATURE': 'test'}), \
             patch.object(sizes.subprocess, 'run', side_effect=subprocess.TimeoutExpired('hyprctl', 1)):
            self.assertEqual(sizes.monitors(), [])
        display = sizes.Display.for_screen(screen(width=1920, height=1080), [])
        self.assertEqual(display.key, '1920x1080@1')
        self.assertEqual(display.area, QRect(0, 38, 1920, 1042))

    def window(self):
        window = QWidget()
        self.addCleanup(window.close)
        outputs = [output(APPLICATION.primaryScreen().name())]
        memory = sizes.Memory(window, self.store, query=lambda: outputs)
        window.show(); APPLICATION.processEvents()
        QTest.qWait(180)
        self.assertTrue(memory.ready)
        return window, memory, outputs

    def test_resize_saves_while_open_and_close_flushes_without_waiting(self):
        window, memory, _ = self.window()
        window.resize(960, 640); QTest.qWait(450)
        self.assertEqual(self.store.load(memory.display), QSize(960, 640))
        window.resize(980, 680); window.close()
        self.assertEqual(self.store.load(memory.display), QSize(980, 680))
        reopened, _, _ = self.window()
        self.assertEqual(reopened.size(), QSize(980, 680))

    def test_fullscreen_and_maximize_do_not_replace_normal_window_size(self):
        for action in ('showFullScreen', 'showMaximized'):
            window, memory, _ = self.window()
            window.resize(700, 500); APPLICATION.processEvents()
            getattr(window, action)(); APPLICATION.processEvents()
            window.close()
            self.assertEqual(self.store.load(memory.display), QSize(700, 500))

    def test_moving_to_smaller_screen_clamps_and_keeps_old_resolution_preference(self):
        window, memory, outputs = self.window()
        window.resize(1700, 1100); APPLICATION.processEvents()
        small_screen = screen('HDMI-1', 1280, 720)
        outputs.append(output('HDMI-1', 1280, 720))
        old = memory.display
        with patch.object(window, 'screen', return_value=small_screen):
            memory.refresh()
            self.assertEqual(window.size(), QSize(1256, 658))
            memory.save()
            self.assertEqual(self.store.load(old), QSize(1700, 1100))
            self.assertEqual(self.store.load(memory.display), QSize(1256, 658))

    def test_transient_primary_screen_during_mapping_cannot_overwrite_preferences(self):
        self.store.save(self.small, QSize(900, 620))
        self.store.save(self.large, QSize(1240, 840))
        window = QWidget(); self.addCleanup(window.close)
        outputs = [output(APPLICATION.primaryScreen().name()), output('temporary', 1920, 1080)]
        memory = sizes.Memory(window, self.store, query=lambda: outputs)
        window.show(); APPLICATION.processEvents()
        with patch.object(window, 'screen', return_value=screen('temporary', 1920, 1080)):
            memory.refresh()
        QTest.qWait(180)
        self.assertTrue(memory.ready)
        self.assertEqual(window.size(), QSize(1240, 840))
        self.assertEqual(self.store.load(self.small), QSize(900, 620))


if __name__ == '__main__':
    unittest.main()
