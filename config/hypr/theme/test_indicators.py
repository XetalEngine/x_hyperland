"""Check actual painted marks, including the hotkey table's item indicators."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QStyle, QStyleOptionButton, QTableWidget, QTableWidgetItem
import runtime

QT = QApplication.instance() or QApplication([])


def red_pixels(image, area):
    count = 0
    for y in range(area.top(), area.bottom()+1):
        for x in range(area.left(), area.right()+1):
            color = image.pixelColor(x, y)
            count += color.red() > 210 and color.green() < 120 and color.blue() < 140
    return count


class IndicatorTests(unittest.TestCase):
    def test_checked_boxes_and_table_items_have_bright_red_marks(self):
        old_style, old_palette = QT.styleSheet(), QT.palette()
        try:
            for mode in runtime.MODES:
                with self.subTest(mode=mode):
                    QT.setPalette(runtime.palette(mode, 'breakpoint'))
                    QT.setStyleSheet(runtime.stylesheet('', mode, 'breakpoint'))
                    check = QCheckBox('Enabled'); check.resize(140, 35); check.show(); QT.processEvents()
                    option = QStyleOptionButton(); check.initStyleOption(option)
                    inside = check.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, check).adjusted(2, 2, -2, -2)
                    unchecked = red_pixels(check.grab().toImage(), inside)
                    check.setChecked(True); QT.processEvents()
                    checked = red_pixels(check.grab().toImage(), inside)
                    self.assertGreaterEqual(checked-unchecked, 15)
                    check.close(); check.deleteLater()
                    table = QTableWidget(1, 1); table.resize(180, 100)
                    item = QTableWidgetItem('Enabled'); item.setCheckState(Qt.CheckState.Unchecked); table.setItem(0, 0, item)
                    table.show(); QT.processEvents()
                    area = table.viewport().rect()
                    before = red_pixels(table.viewport().grab().toImage(), area)
                    item.setCheckState(Qt.CheckState.Checked); QT.processEvents()
                    after = red_pixels(table.viewport().grab().toImage(), area)
                    self.assertGreaterEqual(after-before, 15)
                    table.close(); table.deleteLater()
        finally:
            QT.setStyleSheet(old_style); QT.setPalette(old_palette)


if __name__ == '__main__': unittest.main()
