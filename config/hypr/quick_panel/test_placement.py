import unittest
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


if __name__ == '__main__': unittest.main()
