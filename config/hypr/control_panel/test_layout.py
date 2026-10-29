"""Exercise real scrollbar hit targets with the panel's shared theme styles."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QStyle, QStyleOptionSlider, QScrollBar
import bridge

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'theme'))
import runtime


class ScrollbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def test_horizontal_thumb_can_be_grabbed_and_moves_the_table(self):
        palettes = json.loads((bridge.ROOT/'theme/palettes.json').read_text())
        for design in ('raw', 'modern', 'breakpoint'):
            with self.subTest(design=design):
                palette = palettes['dark'] if design == 'raw' else palettes[design]['dark']
                with patch.object(runtime, 'design', return_value=design), patch.object(runtime, 'colors', return_value=palette):
                    self.app.setStyleSheet(bridge.theme()['stylesheet'])
                table = QTableWidget(5, 8)
                table.setHorizontalScrollBar(QScrollBar(Qt.Orientation.Horizontal, table))
                table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
                for column in range(8):
                    table.setColumnWidth(column, 180)
                    table.setItem(0, column, QTableWidgetItem(str(column)))
                table.resize(700, 300)
                table.show()
                QTest.qWait(25)
                bar = table.horizontalScrollBar()
                self.assertTrue(bar.isVisible())
                self.assertGreater(bar.maximum(), 0)
                option = QStyleOptionSlider()
                bar.initStyleOption(option)
                handle = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, option,
                                                   QStyle.SubControl.SC_ScrollBarSlider, bar)
                self.assertTrue(bar.rect().contains(handle), 'Thumb must fit inside the scrollbar')
                self.assertGreaterEqual(handle.height(), 7)
                QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=handle.center())
                QTest.mouseMove(bar, handle.center()+QPoint(150, 0), delay=25)
                QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=handle.center()+QPoint(150, 0))
                self.assertGreater(bar.value(), 0)
                self.assertEqual(table.horizontalHeader().offset(), bar.value())
                table.close()
                table.deleteLater()


if __name__ == '__main__': unittest.main()
