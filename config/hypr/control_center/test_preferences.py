"""Compositor value decoding and Input Apply, without touching a live profile."""
import json
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication
import desktop_settings as settings
import preferences_page as preferences

QT = QApplication.instance() or QApplication([])


def synchronous(work, done, failed):
    try: result = work()
    except Exception as error: failed(str(error))
    else: done(result)


class PreferenceReadbackTests(unittest.TestCase):
    def test_boolean_gap_and_legacy_responses_preserve_values(self):
        responses = {
            'enabled': {'bool': True}, 'disabled': {'bool': False},
            'old-enabled': {'int': 1}, 'old-disabled': {'int': 0},
            'gaps': {'css': '3 6 9 12'}, 'old-gaps': {'custom': '4 4 4 4'},
            'speed': {'float': -.25}, 'layout': {'str': 'us,ca'}, 'empty': {'str': '[[EMPTY]]'},
        }
        with patch.object(settings, 'ctl', side_effect=lambda *args: json.dumps(responses[args[-1]])):
            self.assertEqual(settings.read_options(responses), {
                'enabled': True, 'disabled': False, 'old-enabled': 1, 'old-disabled': 0,
                'gaps': '3 6 9 12', 'old-gaps': '4 4 4 4', 'speed': -.25, 'layout': 'us,ca', 'empty': '',
            })
        with patch.object(settings, 'ctl', return_value='{"error":"no such option"}'):
            with self.assertRaisesRegex(ValueError, 'input:unknown.*no such option'):
                settings.read_options(['input:unknown'])

    def test_input_toggles_read_apply_and_reload_on_both_compositor_formats(self):
        for modern in (False, True):
            with self.subTest(modern=modern):
                responses = {}
                for _, key, _, kind, data in preferences.INPUT:
                    if kind == 'bool': value, field = (True, 'bool') if modern else (1, 'int')
                    elif kind == 'int': value, field = data[0], 'int'
                    elif kind == 'float': value, field = .25, 'float'
                    elif kind == 'choice':
                        value = data[0][1]; field = 'int' if isinstance(value, int) else 'str'
                    else: value, field = ('us' if key == 'input:kb_layout' else ''), 'str'
                    responses[key] = {field: value}
                store = Mock(); store.load.return_value = ('# Preserve unrelated preferences\n', 'token')
                key = 'input:natural_scroll'
                def save(content, token):
                    self.assertIn('# Preserve unrelated preferences', content)
                    self.assertIn(key+' = false', content)
                    self.assertNotIn('input:sensitivity', content)
                    responses[key] = {'bool': False} if modern else {'int': 0}
                store.save.side_effect = save
                with patch.object(settings, 'Store', return_value=store), \
                     patch.object(settings, 'ctl', side_effect=lambda *args: json.dumps(responses[args[-1]])):
                    page = preferences.PreferencesPage('input', synchronous)
                    try:
                        page.refresh()
                        self.assertTrue(page.fields[key].isChecked())
                        page.fields[key].setChecked(False); page.save()
                        store.save.assert_called_once()
                        self.assertFalse(page.fields[key].isChecked())
                        self.assertFalse(page.dirty)
                        self.assertTrue(page.status.text().startswith('Applied and saved'))
                        page.refresh(True)
                        self.assertFalse(page.fields[key].isChecked())
                    finally: page.close(); page.deleteLater()


if __name__ == '__main__': unittest.main()
