"""Linux virtual-console mouse input for ncurses builds without GPM integration.

Uses the public libgpm ABI from gpm.h (https://github.com/telmich/gpm).
Terminal emulators continue to use curses' normal mouse protocol.
"""
import ctypes as C
import curses
import fcntl
import os
import re
import select
import struct


class Connect(C.Structure):
    _fields_=[('eventMask',C.c_ushort),('defaultMask',C.c_ushort),
              ('minMod',C.c_ushort),('maxMod',C.c_ushort),('pid',C.c_int),('vc',C.c_int)]


class Event(C.Structure):
    _fields_=[('buttons',C.c_ubyte),('modifiers',C.c_ubyte),('vc',C.c_ushort),
              ('dx',C.c_short),('dy',C.c_short),('x',C.c_short),('y',C.c_short),
              ('type',C.c_int),('clicks',C.c_int),('margin',C.c_int),
              ('wdx',C.c_short),('wdy',C.c_short)]


def translate(event):
    state=0
    if event.wdy>0 or event.buttons&16:state=curses.BUTTON4_PRESSED
    elif event.wdy<0 or event.buttons&32:state=getattr(curses,'BUTTON5_PRESSED',0)
    elif event.buttons&4:
        if event.type&4:state=curses.BUTTON1_PRESSED
        elif event.type&8:state=curses.BUTTON1_RELEASED
    return (0,event.x,event.y,0,state)


class ConsoleMouse:
    def __init__(self):
        self.lib=None;self.fd=-1;self.position=None
        try:
            if os.environ.get('TERM')!='linux' or not re.fullmatch(r'/dev/tty[0-9]+',os.ttyname(0)):return
            lib=C.CDLL('libgpm.so.2')
            lib.Gpm_Open.argtypes=[C.POINTER(Connect),C.c_int];lib.Gpm_Open.restype=C.c_int
            lib.Gpm_GetEvent.argtypes=[C.POINTER(Event)];lib.Gpm_GetEvent.restype=C.c_int
            lib.Gpm_Close.argtypes=[];lib.Gpm_Close.restype=C.c_int
            C.c_int.in_dll(lib,'gpm_zerobased').value=1
            connection=Connect(15,0,0,0xffff,0,0)
            fd=lib.Gpm_Open(C.byref(connection),0)
            if fd>=0:self.lib,self.fd=lib,fd
        except (OSError,ValueError):pass

    def read(self):
        if self.fd<0:return None
        try:
            if not select.select([self.fd],[],[],0)[0]:return None
            event=Event()
            if self.lib.Gpm_GetEvent(C.byref(event))<=0:
                self.close();return None
            self.position=(event.x,event.y)
            return translate(event)
        except OSError:
            self.close();return None

    def draw_pointer(self,rows,cols):
        if self.fd<0 or self.position is None:return
        x,y=self.position
        if not (0<=x<cols and 0<=y<rows):return
        # Equivalent to Gpm_DrawPointer: TIOCLINUX's selection-pointer mode.
        try:fcntl.ioctl(0,0x541c,struct.pack('=BHHHHH',2,x+1,y+1,x+1,y+1,3))
        except OSError:pass

    def close(self):
        if self.fd>=0:self.lib.Gpm_Close()
        self.fd=-1;self.position=None
