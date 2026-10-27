"""Key recording shared by Control desk and the Apps shortcut editor."""
import ctypes
from PyQt6.QtCore import Qt,pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QLineEdit


class CaptureEdit(QLineEdit):
    captured=pyqtSignal(str,str)
    cancelled=pyqtSignal()

    def __init__(self):
        super().__init__();self.recording=False

    def keyPressEvent(self,event):
        if not self.recording:return super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Control,Qt.Key.Key_Shift,Qt.Key.Key_Alt,Qt.Key.Key_Meta,Qt.Key.Key_AltGr):return
        if event.key()==Qt.Key.Key_Escape:self.cancelled.emit();return
        modifiers=[]
        for flag,name in ((Qt.KeyboardModifier.MetaModifier,'SUPER'),(Qt.KeyboardModifier.ControlModifier,'CTRL'),
                          (Qt.KeyboardModifier.AltModifier,'ALT'),(Qt.KeyboardModifier.ShiftModifier,'SHIFT')):
            if event.modifiers()&flag:modifiers.append(name)
        name=''
        if event.nativeVirtualKey():
            try:
                library=ctypes.CDLL('libxkbcommon.so.0');buffer=ctypes.create_string_buffer(128)
                library.xkb_keysym_get_name(ctypes.c_uint32(event.nativeVirtualKey()),buffer,len(buffer));name=buffer.value.decode()
            except Exception:pass
        if not name:
            names={Qt.Key.Key_Return:'Return',Qt.Key.Key_Enter:'KP_Enter',Qt.Key.Key_Space:'space',Qt.Key.Key_Backspace:'BackSpace',Qt.Key.Key_Tab:'Tab'}
            name=names.get(event.key(),QKeySequence(event.key()).toString())
        self.captured.emit(' '.join(modifiers),name)
