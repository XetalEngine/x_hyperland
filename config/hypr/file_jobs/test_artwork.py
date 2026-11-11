"""Render across animation boundaries, including individual packet wraps."""
import unittest
from pathlib import Path
import sys

# The production window adds the profile's shared theme painters to its path.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'theme'))

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

import artwork


class LoopTests(unittest.TestCase):
    def frame(self, style, phase, count=3, extracting=False, trails=True, light=False):
        image = QImage(448, 80, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor('#ecede8' if light else '#111c20'))
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            getattr(artwork, style)(painter, QRectF(0, 0, 448, 80),
                QColor('#61785b' if light else '#a5c5a1'),
                QColor('#e0e7df' if light else '#162527'), phase,
                count, trails, 60, not extracting, extracting, None)
        finally:
            painter.end()
        return image

    def difference(self, first, second):
        a = first.constBits().asstring(first.sizeInBytes())
        b = second.constBits().asstring(second.sizeInBytes())
        return sum(abs(x-y) for x,y in zip(a,b))/len(a)

    def test_cycle_boundary_has_no_visible_reset(self):
        # tick() supplies a repeating 0..1 phase. A speed multiplier inside a
        # renderer used to jump backwards after travelling only 18–22% of its
        # route. Check the actual rendered images, not the timing expression.
        for style in ('hyperfusionblue', 'midnighttransit', 'blackwood', 'atomicafterglow', 'mycelium', 'platform95', 'midnightrun','infernalencore','polaris','leviathan','ghostbusters','mystery98','prisonbreak'):
            for count in (1, 3, 7):
                for extracting in (False, True):
                    for light in (False, True):
                        with self.subTest(style=style, count=count, extracting=extracting, light=light):
                            a = self.frame(style, 1-1e-6, count, extracting, light=light)
                            b = self.frame(style, 1e-6, count, extracting, light=light)
                            self.assertLess(self.difference(a,b), .02)

    def test_each_packet_wraps_out_of_view_without_a_pop(self):
        for style in ('hyperfusionblue', 'midnighttransit', 'blackwood', 'atomicafterglow', 'mycelium', 'platform95', 'midnightrun','infernalencore','polaris','leviathan','ghostbusters','mystery98','prisonbreak'):
            for extracting in (False, True):
                for trails in (False, True):
                    for count in (1,3,7):
                        for boundary in (i/count for i in range(1,count+1)):
                            with self.subTest(style=style, count=count, extracting=extracting, trails=trails, boundary=boundary):
                                a = self.frame(style, boundary-1e-6, count, extracting=extracting, trails=trails)
                                b = self.frame(style, boundary+1e-6, count, extracting=extracting, trails=trails)
                                self.assertLess(self.difference(a,b), .02)

    def test_scenes_keep_moving_through_the_whole_cycle(self):
        for style in ('hyperfusionblue', 'midnighttransit', 'blackwood', 'atomicafterglow', 'mycelium', 'platform95', 'midnightrun','infernalencore','polaris','leviathan','ghostbusters','mystery98','prisonbreak'):
            for phase in (.05, .3, .6, .9):
                with self.subTest(style=style, phase=phase):
                    self.assertNotEqual(self.frame(style, phase), self.frame(style, phase+.04))


if __name__ == '__main__': unittest.main()
