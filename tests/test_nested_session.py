import ast
from pathlib import Path
import re
import unittest
from nested_session import nested_environment


class NestedIsolation(unittest.TestCase):
    def test_seat_is_disabled_and_login_identity_is_not_inherited(self):
        before={'LIBSEAT_BACKEND':'logind','XDG_SESSION_ID':'3','XDG_SEAT':'seat0','XDG_VTNR':'1',
                'WAYLAND_DISPLAY':'/private/parent-wayland','XDG_RUNTIME_DIR':'/private/test',
                'HYPRLAND_NO_SD_VARS':'0','PATH':'/usr/bin'}
        after=nested_environment(before)
        self.assertEqual(after['LIBSEAT_BACKEND'],'none')
        self.assertTrue(all(k not in after for k in ('XDG_SESSION_ID','XDG_SEAT','XDG_VTNR')))
        self.assertEqual(after['WAYLAND_DISPLAY'],before['WAYLAND_DISPLAY'])
        self.assertEqual(after['XDG_RUNTIME_DIR'],before['XDG_RUNTIME_DIR'])
        self.assertEqual(after['HYPRLAND_NO_SD_VARS'],'1')
        self.assertEqual(before['LIBSEAT_BACKEND'],'logind')

    def test_native_desktop_checks_use_the_seat_isolation_boundary(self):
        # Catch future native harnesses that rely only on AQ_BACKENDS again.
        for path in Path(__file__).parent.glob('check-*.py'):
            source=path.read_text()
            if not re.search(r"AQ_BACKENDS|(?:\[|\()\s*['\"](?:/usr/bin/)?Hyprland['\"]",source):continue
            tree=ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node,ast.Assign):continue
                if not any(isinstance(target,ast.Name) and target.id=='env' for target in node.targets):continue
                with self.subTest(script=path.name,line=node.lineno):
                    self.assertIsInstance(node.value,ast.Call)
                    self.assertIsInstance(node.value.func,ast.Name)
                    self.assertEqual(node.value.func.id,'nested_environment')


if __name__=='__main__':unittest.main()
