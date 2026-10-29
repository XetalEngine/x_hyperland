"""Check actual painted marks, including the hotkey table's item indicators."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QStyle, QStyleOptionButton, QTableWidget, QTableWidgetItem
import runtime

QT = QApplication.instance() or QApplication([])


def accent_pixels(image, area, design):
    count = 0
    for y in range(area.top(), area.bottom()+1):
        for x in range(area.left(), area.right()+1):
            color = image.pixelColor(x, y)
            count += (color.blue() > 210 and color.red() < 130 and 90 < color.green() < 210) if design=='binaryknife' else (color.red() > 210 and color.green() < 120 and color.blue() < 140)
    return count


class IndicatorTests(unittest.TestCase):
    def test_checked_boxes_and_table_items_have_visible_accent_marks(self):
        old_style, old_palette = QT.styleSheet(), QT.palette()
        try:
            for mode,design in ((mode,design) for mode in runtime.MODES for design in ('breakpoint','binaryknife')):
                with self.subTest(mode=mode,design=design):
                    QT.setPalette(runtime.palette(mode, design))
                    QT.setStyleSheet(runtime.stylesheet('', mode, design))
                    check = QCheckBox('Enabled'); check.resize(140, 35); check.show(); QT.processEvents()
                    option = QStyleOptionButton(); check.initStyleOption(option)
                    inside = check.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, check).adjusted(2, 2, -2, -2)
                    unchecked = accent_pixels(check.grab().toImage(), inside, design)
                    check.setChecked(True); QT.processEvents()
                    checked = accent_pixels(check.grab().toImage(), inside, design)
                    self.assertGreaterEqual(checked-unchecked, 15)
                    check.close(); check.deleteLater()
                    table = QTableWidget(1, 1); table.resize(180, 100)
                    item = QTableWidgetItem('Enabled'); item.setCheckState(Qt.CheckState.Unchecked); table.setItem(0, 0, item)
                    table.show(); QT.processEvents()
                    area = table.viewport().rect()
                    before = accent_pixels(table.viewport().grab().toImage(), area, design)
                    item.setCheckState(Qt.CheckState.Checked); QT.processEvents()
                    after = accent_pixels(table.viewport().grab().toImage(), area, design)
                    self.assertGreaterEqual(after-before, 15)
                    table.close(); table.deleteLater()
        finally:
            QT.setStyleSheet(old_style); QT.setPalette(old_palette)


if __name__ == '__main__': unittest.main()
