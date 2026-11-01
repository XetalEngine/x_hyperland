"""Verify the native-console mouse ABI and route without touching a real VT."""
import ctypes
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_iso_frontend import terminal, FRONTEND
spec=importlib.util.spec_from_file_location('mouse',FRONTEND.with_name('installer_mouse.py'))
mouse=importlib.util.module_from_spec(spec);spec.loader.exec_module(mouse)

class ConsoleMouseTests(unittest.TestCase):
    def test_gpm_structs_match_the_installed_public_header(self):
        if not shutil.which('cc') or not Path('/usr/include/gpm.h').exists():self.skipTest('GPM development header unavailable')
        source='#include <stddef.h>\n#include <stdio.h>\n#include <gpm.h>\nint main(void){printf("%zu %zu %zu %zu",sizeof(Gpm_Connect),sizeof(Gpm_Event),offsetof(Gpm_Event,type),offsetof(Gpm_Event,wdy));}\n'
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'abi'
            subprocess.run(['cc','-x','c','-','-o',str(binary)],input=source,text=True,capture_output=True,check=True)
            got=tuple(map(int,subprocess.check_output([str(binary)],text=True).split()))
        self.assertEqual(got,(ctypes.sizeof(mouse.Connect),ctypes.sizeof(mouse.Event),mouse.Event.type.offset,mouse.Event.wdy.offset))

    def test_press_release_and_scroll_translate_to_curses(self):
        event=mouse.Event();event.x=10;event.y=20;event.buttons=4;event.type=4
        self.assertEqual(mouse.translate(event),(0,10,20,0,mouse.curses.BUTTON1_PRESSED))
        event.type=8;self.assertEqual(mouse.translate(event)[4],mouse.curses.BUTTON1_RELEASED)
        event.buttons=0;event.type=1;self.assertEqual(mouse.translate(event)[4],0)
        event.wdy=1;self.assertEqual(mouse.translate(event)[4],mouse.curses.BUTTON4_PRESSED)

    def test_terminal_emulators_and_pts_never_connect_to_console_mouse(self):
        for term in ('xterm-kitty','linux'):
            with patch.dict(os.environ,TERM=term),patch.object(os,'ttyname',return_value='/dev/pts/5'),patch.object(mouse.C,'CDLL') as library:
                client=mouse.ConsoleMouse();self.assertEqual(client.fd,-1);library.assert_not_called()

    def test_native_console_events_choose_a_drive_and_click_next(self):
        # The real curses loop consumes a GPM-shaped event source. No terminal
        # mouse escape sequences are sent, matching a Linux virtual console.
        script='''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('ui',sys.argv[1]);ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
class Mouse:
 fd=5
 def __init__(self):
  self.events=[(0,9,12,0,ui.curses.BUTTON1_PRESSED),(0,9,12,0,ui.curses.BUTTON1_RELEASED),(0,93,27,0,ui.curses.BUTTON1_PRESSED),(0,93,27,0,ui.curses.BUTTON1_RELEASED)]
 def read(self):return self.events.pop(0) if self.events else None
 def close(self):self.fd=-1
 def draw_pointer(self,*args):pass
ui.installer_mouse.ConsoleMouse=Mouse
raise SystemExit(ui.main(['menu','--title','Choose drive','--text','Choose a target.','--','a','SSD A','b','SSD B']))
'''
        import sys
        with terminal([],term='linux',command=[sys.executable,'-c',script,str(FRONTEND)]) as tty:
            self.assertEqual(tty.finish(),(0,'b\n',''))

if __name__=='__main__':unittest.main()
