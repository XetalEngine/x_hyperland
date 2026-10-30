from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import model
from protocol import Request


class Models(unittest.TestCase):
    def test_one_toggle_per_message_even_with_duplicate_ready_notifications(self):
        request=Request();self.assertIsNone(request.feed(b'{"kind":'))
        self.assertEqual(request.feed(b'"clock"}\n'),{'kind':'clock'})
        self.assertIsNone(request.feed(b''));self.assertIsNone(request.feed(b'{"kind":"clock"}\n'))
        with self.assertRaises(ValueError):Request().feed(b'x'*4097)
        with self.assertRaises(ValueError):Request().feed(b'[]\n')
    def test_leap_month_and_year_navigation(self):
        days=model.month_days(2024,2);self.assertEqual(len(days),42);self.assertIn(date(2024,2,29),days)
        self.assertEqual(days[0].weekday(),0)
        self.assertEqual(model.shift_month(2026,12,1),(2027,1));self.assertEqual(model.shift_month(2026,1,-1),(2025,12))
    def test_scaled_rotated_negative_monitor_and_edges(self):
        monitor=dict(id=2,x=-720,y=0,width=1920,height=1080,scale=1.5,transform=1,reserved=[0,38,0,0])
        self.assertEqual(model.monitor_at([monitor],{'x':-100,'y':300}),monitor)
        top=model.placement(monitor,'power');bottom=model.placement(monitor,'clock','bottom')
        self.assertEqual(top['y'],48);self.assertLess(top['x']+top['width'],0)
        self.assertEqual(bottom['y']+bottom['height'],1270)
        small=dict(monitor,width=800,height=600,scale=2,transform=0)
        self.assertLessEqual(model.placement(small,'power')['height'],242)
    def test_real_battery_and_desktop_fallback(self):
        self.assertEqual(model.battery_status(None)['percent'],100)
        value=model.battery_status(SimpleNamespace(percent=37.8,power_plugged=False,secsleft=7200))
        self.assertEqual(value['percent'],38);self.assertIn('2h 00m',value['detail'])
        self.assertEqual(model.battery_status(SimpleNamespace(percent=145,power_plugged=True,secsleft=-1))['percent'],100)
    def test_media_microseconds_and_missing_metadata(self):
        with patch.object(model,'command',return_value='player\x1fTrack\x1fArtist\x1f\x1f120000000\x1f35000000\x1fPlaying'):
            media=model.media_snapshot();self.assertEqual(media['length'],120);self.assertEqual(media['position'],35)
        with patch.object(model,'command',return_value=''):self.assertIsNone(model.media_snapshot())


if __name__=='__main__':unittest.main()
