import unittest
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch
import placement


class Placement(unittest.TestCase):
    def test_each_map_receives_its_output_geometry_and_bar_edge(self):
        requests = [dict(monitor=0, width=370, height=440, relative_x=1538, relative_y=48),
                    dict(monitor=2, width=420, height=835, relative_x=1268, relative_y=555, edge='bottom')]
        with patch.object(placement.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='ok\n\n\nok\n\n\nok\n\n\nok\n\n', stderr='')) as run:
            for request in requests:
                self.assertEqual(placement.prepare(request), (request['width'], request['height']))
                batch = run.call_args.args[0][2]
                self.assertIn(f":monitor {request['monitor']}", batch)
                self.assertIn(f":move {request['relative_x']} {request['relative_y']}", batch)
                self.assertIn(':animation slide ' + request.get('edge', 'top'), batch)

    def test_failed_rule_setup_does_not_fall_through_to_mapping(self):
        request = dict(monitor=0, width=370, height=440, relative_x=1538, relative_y=48)
        with patch.object(placement.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='rule not found\nok\nok\nok\n', stderr='')):
            with self.assertRaises(RuntimeError): placement.prepare(request)
        with patch.object(placement.subprocess, 'run') as run:
            with self.assertRaises(ValueError): placement.prepare(dict(request, relative_x='0; dispatch exit'))
            run.assert_not_called()

    def test_wide_mixer_is_allowed_without_expanding_other_panels(self):
        request=dict(kind='audio',monitor=0,width=2046,height=470,relative_x=308,relative_y=48)
        with patch.object(placement.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='ok\nok\nok\nok\n',stderr='')):
            self.assertEqual(placement.prepare(request),(2046,470))
            with self.assertRaises(ValueError):placement.prepare(dict(request,kind='clock'))
            with self.assertRaises(ValueError):placement.prepare(dict(request,width=2047))
            with self.assertRaises(ValueError):placement.prepare(request,rule='fusion-clipboard-history')

    def test_live_resize_targets_only_the_mapped_popup_without_focusing(self):
        clients=[dict(pid=12,mapped=True,title='Hyper Fusion quick panel',**{'class':'fusion-quick-panel'},address='0xabc'),
                 dict(pid=99,mapped=True,title='Browser',**{'class':'browser'},address='0xdef')]
        replies=[SimpleNamespace(returncode=0,stdout=json.dumps(clients),stderr=''),
                 SimpleNamespace(returncode=0,stdout='ok\nok\n',stderr='')]
        request=dict(width=408,height=470,x=1500,y=50)
        cancelled=threading.Event()
        with patch.object(placement.subprocess,'run',side_effect=replies) as run:
            self.assertTrue(placement.resize_mapped(request,12,cancelled))
            self.assertEqual(run.call_args.args[0],['hyprctl','--batch',
                'dispatch resizewindowpixel exact 408 470,address:0xabc;dispatch movewindowpixel exact 1500 50,address:0xabc'])
        cancelled.set()
        with patch.object(placement.subprocess,'run',return_value=replies[0]) as run:
            self.assertFalse(placement.resize_mapped(request,12,cancelled));self.assertEqual(run.call_count,1)
        with patch.object(placement.subprocess,'run',return_value=replies[0]) as run:
            self.assertFalse(placement.resize_mapped(request,123,threading.Event()));self.assertEqual(run.call_count,1)


if __name__ == '__main__': unittest.main()
