import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QSettings, Qt
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from programmer_calculator.theme import STYLESHEET
from programmer_calculator.window import CalculatorWindow, ui_font_family
from programmer_calculator import window as calculator_window


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setFont(QFont(ui_font_family(), 10))
        cls.app.setStyleSheet(STYLESHEET)

    def setUp(self):
        preferences_dir = TemporaryDirectory()
        self.addCleanup(preferences_dir.cleanup)
        self.preferences_path = str(Path(preferences_dir.name) / "preferences.ini")
        self.window = CalculatorWindow(settings=QSettings(self.preferences_path, QSettings.Format.IniFormat))
        self.window.show()
        self.window.activateWindow()
        self.window.setFocus()
        QTest.qWait(30)
        self.app.processEvents()
        self.assertTrue(self.window.isActiveWindow())

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def type(self, text):
        QTest.keyClicks(self.window, text)

    def test_default_preferences_stay_inside_the_calculator_profile(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'calculator/state/preferences.ini'
            with patch.object(calculator_window, 'SETTINGS_PATH', path):
                window = CalculatorWindow()
                try:
                    window.base_rows[16].radio.setChecked(True)
                    window.auto_calculate.setChecked(True)
                    self.assertEqual(Path(window.settings.fileName()), path)
                    self.assertTrue(path.is_file())
                    saved = QSettings(str(path), QSettings.Format.IniFormat)
                    self.assertEqual(saved.value('base', type=int), 16)
                    self.assertTrue(saved.value('autoCalculate', type=bool))
                finally:
                    window.close(); window.deleteLater()

    def keypad(self, key, text=""):
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.KeypadModifier, text)
        QApplication.sendEvent(self.window, event)

    def restored_preferences_in_new_process(self):
        # A separate interpreter must read the saved file, not Qt's in-process cache.
        script = """
import json
import sys
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from programmer_calculator.window import CalculatorWindow
app = QApplication([])
window = CalculatorWindow(settings=QSettings(sys.argv[1], QSettings.Format.IniFormat))
print(json.dumps({
    "base": window.engine.base,
    "dec": window.base_rows[10].radio.isChecked(),
    "hex": window.base_rows[16].radio.isChecked(),
    "auto": window.auto_calculate.isChecked(),
    "hex_digits_enabled": window.buttons["A"].isEnabled(),
}))
window.close()
"""
        result = subprocess.run(
            [sys.executable, "-c", script, self.preferences_path],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True, text=True, check=True, timeout=15,
        )
        return json.loads(result.stdout)

    def test_radio_preferences_restore_in_a_new_process(self):
        for base, auto in ((16, True), (10, True), (16, False), (10, False)):
            with self.subTest(base=base, auto=auto):
                QTest.keyClick(self.window, Qt.Key.Key_H if base == 16 else Qt.Key.Key_D,
                               Qt.KeyboardModifier.ControlModifier)
                if self.window.auto_calculate.isChecked() != auto:
                    QTest.mouseClick(self.window.auto_calculate, Qt.MouseButton.LeftButton)
                self.assertEqual(self.restored_preferences_in_new_process(), {
                    "base": base, "dec": base == 10, "hex": base == 16,
                    "auto": auto, "hex_digits_enabled": base == 16,
                })

    def test_invalid_saved_preferences_use_safe_defaults(self):
        settings = self.window.settings
        settings.setValue("base", "invalid")
        settings.setValue("autoCalculate", "invalid")
        settings.sync()
        self.assertEqual(self.restored_preferences_in_new_process(), {
            "base": 10, "dec": True, "hex": False,
            "auto": False, "hex_digits_enabled": False,
        })

    def test_mode_restored_from_history_is_remembered(self):
        QTest.keyClick(self.window, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.type("A+1=")
        QTest.keyClick(self.window, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        self.window._restore_history(self.window.engine.history[0])
        self.window.close()
        self.assertEqual(self.restored_preferences_in_new_process()["base"], 16)

    def test_standard_keyboard_and_enter(self):
        self.type("123+456")
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertEqual(self.window.engine.value, 579)
        self.assertEqual(self.window.number.text(), "579")

    def test_auto_calculate_radio_toggles_without_changing_base_or_input(self):
        self.type("1+1+1+")
        self.assertEqual(self.window.number.text(), "1")
        QTest.mouseClick(self.window.auto_calculate, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.auto_calculate.isChecked())
        self.assertEqual(self.window.number.text(), "3")
        QTest.keyClick(self.window, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.auto_calculate.isChecked())
        self.assertTrue(self.window.base_rows[16].radio.isChecked())
        QTest.mouseClick(self.window.auto_calculate, Qt.MouseButton.LeftButton)
        self.assertFalse(self.window.auto_calculate.isChecked())
        self.assertEqual(self.window.number.text(), "1")
        self.assertTrue(self.window.base_rows[16].radio.isChecked())

    def test_auto_calculate_multidigit_entry_editing_and_precedence(self):
        self.window.auto_calculate.setChecked(True)
        self.type("2+3*4")
        self.assertEqual(self.window.number.text(), "14")
        self.assertEqual(self.window.expression.full_text, "2 + 3 × 4")
        self.type("5")
        self.assertEqual(self.window.number.text(), "137")
        QTest.keyClick(self.window, Qt.Key.Key_Backspace)
        self.assertEqual(self.window.number.text(), "14")
        QTest.keyClick(self.window, Qt.Key.Key_Delete)
        self.assertEqual(self.window.number.text(), "2")
        self.type("6")
        self.assertEqual(self.window.number.text(), "20")

    def test_auto_calculate_numpad_and_clicks_without_enter(self):
        self.window.auto_calculate.setChecked(True)
        self.keypad(Qt.Key.Key_7, "7")
        QTest.mouseClick(self.window.buttons["*"], Qt.MouseButton.LeftButton)
        self.keypad(Qt.Key.Key_6, "6")
        self.assertEqual(self.window.number.text(), "42")
        self.assertEqual(self.window.engine.history, [])

    def test_auto_calculate_enter_commits_once_and_repeat_equals_works(self):
        self.window.auto_calculate.setChecked(True)
        self.type("2+3")
        self.assertEqual(self.window.number.text(), "5")
        self.assertEqual(len(self.window.engine.history), 0)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertEqual(self.window.number.text(), "5")
        self.assertEqual(len(self.window.engine.history), 1)
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertEqual(self.window.number.text(), "8")
        self.assertEqual(len(self.window.engine.history), 2)

    def test_auto_calculate_enter_preserves_preview_after_trailing_operator(self):
        self.window.auto_calculate.setChecked(True)
        self.type("1+1+1+")
        self.assertEqual(self.window.number.text(), "3")
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertEqual(self.window.number.text(), "3")
        self.assertEqual(self.window.engine.history[0].result, 3)

    def test_auto_calculate_live_error_is_editable_and_not_copyable(self):
        self.window.auto_calculate.setChecked(True)
        self.type("8/0")
        self.assertEqual(self.window.number.text(), "Cannot divide by zero")
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertFalse(self.window.error)
        self.type("2")
        self.assertEqual(self.window.number.text(), "4")
        self.assertTrue(self.window.copy_button.isEnabled())

    def test_auto_calculate_hex_conversion_clipboard_and_paste(self):
        self.window.auto_calculate.setChecked(True)
        QTest.keyClick(self.window, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        self.type("A+F")
        self.assertEqual(self.window.number.text(), "19")
        self.assertEqual(self.window.base_rows[10].value.full_text, "25")
        self.assertEqual(self.window.base_rows[16].value.full_text, "19")
        QTest.keyClick(self.window, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "19")
        self.app.clipboard().setText("0x20")
        QTest.keyClick(self.window, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.number.text(), "2A")
        self.assertEqual(self.window.expression.full_text, "A + 20")

    def test_auto_calculate_wraps_and_bit_editing_uses_the_live_result(self):
        self.window.auto_calculate.setChecked(True)
        self.window.word_size.setCurrentIndex(self.window.word_size.findData(8))
        self.type("127+1")
        self.assertEqual(self.window.number.text(), "-128")
        self.assertEqual(self.window.base_rows[16].value.full_text, "80")
        self.window.bits_toggle.setChecked(True)
        self.assertEqual(self.window.bit_buttons[7].text(), "1")
        self.assertEqual(self.window.bit_buttons[0].text(), "0")
        QTest.mouseClick(self.window.bit_buttons[0], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.number.text(), "-127")
        self.assertEqual(self.window.bit_buttons[0].text(), "1")
        self.assertEqual(self.window.expression.full_text, "")

    def test_numpad_arithmetic_and_enter(self):
        self.keypad(Qt.Key.Key_7, "7")
        self.keypad(Qt.Key.Key_Asterisk, "*")
        self.keypad(Qt.Key.Key_6, "6")
        self.keypad(Qt.Key.Key_Enter)
        self.assertEqual(self.window.engine.value, 42)

    def test_numpad_without_num_lock(self):
        self.keypad(Qt.Key.Key_End)
        self.keypad(Qt.Key.Key_Down)
        self.keypad(Qt.Key.Key_PageDown)
        self.assertEqual(self.window.engine.value, 123)
        self.keypad(Qt.Key.Key_Delete)
        self.assertEqual(self.window.engine.value, 123)

    def test_radio_switch_and_hex_keyboard(self):
        self.type("AF")
        self.assertEqual(self.window.engine.value, 0)
        self.assertFalse(self.window.buttons["A"].isEnabled())
        QTest.mouseClick(self.window.base_rows[16].radio, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.engine.base, 16)
        self.assertTrue(self.window.buttons["A"].isEnabled())
        self.type("FF")
        QTest.keyClick(self.window, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.engine.base, 10)
        self.assertEqual(self.window.number.text(), "255")
        self.assertTrue(self.window.base_rows[10].radio.isChecked())
        self.assertFalse(self.window.base_rows[16].radio.isChecked())

    def test_keyboard_with_a_button_focused(self):
        self.window.buttons["5"].setFocus()
        QTest.keyClicks(self.window.buttons["5"], "8+9")
        QTest.keyClick(self.window.buttons["5"], Qt.Key.Key_Return)
        self.assertEqual(self.window.engine.value, 17)

    def test_input_ignored_while_another_window_is_active(self):
        other = QWidget()
        other.show()
        other.activateWindow()
        QTest.qWait(30)
        self.assertFalse(self.window.isActiveWindow())
        self.type("123")
        self.assertEqual(self.window.engine.value, 0)
        self.assertEqual(self.window.status.text(), "Focus to use keyboard")
        other.close()
        other.deleteLater()

    def test_error_and_recovery(self):
        self.type("7/0=")
        self.assertEqual(self.window.number.text(), "Cannot divide by zero")
        self.type("8*3=")
        self.assertEqual(self.window.engine.value, 24)
        self.assertEqual(self.window.error, "")

    def test_clear_and_backspace_shortcuts(self):
        self.type("123")
        QTest.keyClick(self.window, Qt.Key.Key_Backspace)
        self.assertEqual(self.window.engine.value, 12)
        self.type("+45")
        QTest.keyClick(self.window, Qt.Key.Key_Delete)
        self.type("6=")
        self.assertEqual(self.window.engine.value, 18)
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertEqual(self.window.engine.value, 0)

    def test_clear_entry_corrects_division_error(self):
        self.type("9/0=")
        QTest.keyClick(self.window, Qt.Key.Key_Delete)
        self.type("3=")
        self.assertEqual(self.window.engine.value, 3)
        self.assertFalse(self.window.error)

    def test_clicks_and_keyboard_can_be_mixed(self):
        QTest.mouseClick(self.window.buttons["7"], Qt.MouseButton.LeftButton)
        QTest.mouseClick(self.window.buttons["*"], Qt.MouseButton.LeftButton)
        self.type("6")
        QTest.mouseClick(self.window.buttons["="], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.engine.value, 42)

    def test_word_size_and_bit_view(self):
        self.type("255")
        self.window.word_size.setCurrentIndex(self.window.word_size.findData(8))
        self.assertEqual(self.window.engine.value, -1)
        self.window.bits_toggle.setChecked(True)
        self.assertTrue(self.window.bits_panel.isVisible())
        self.assertFalse(self.window.bit_buttons[8].isEnabled())
        QTest.mouseClick(self.window.bit_buttons[7], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.engine.value, 127)

    def test_clipboard_and_invalid_paste(self):
        self.type("255")
        QTest.keyClick(self.window, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.window, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), "FF")
        self.app.clipboard().setText("0xABC")
        QTest.keyClick(self.window, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.engine.value, 2748)
        self.app.clipboard().setText("some code()")
        self.window.paste_value()
        self.assertEqual(self.window.engine.value, 2748)

    def test_history_and_restore(self):
        self.type("12*3=")
        self.window.history_button.setChecked(True)
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(len(self.window.engine.history), 1)
        self.window._restore_history(self.window.engine.history[0])
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.assertEqual(self.window.engine.value, 36)
        self.type("+4=")
        self.assertEqual(self.window.engine.value, 40)

    def test_small_window_fits_buttons(self):
        self.window.resize(420, 720)
        self.app.processEvents()
        for action, button in self.window.buttons.items():
            with self.subTest(action=action):
                self.assertGreaterEqual(button.width(), 36)
                self.assertGreaterEqual(button.height(), 36)
                self.assertTrue(button.isVisible())


if __name__ == "__main__":
    unittest.main()
