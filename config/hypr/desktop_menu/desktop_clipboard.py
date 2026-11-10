"""GTK file clipboard with KDE and GNOME copy/cut interoperability.

GTK 3 omits set_with_data from introspection. Keep that small C API boundary
here; ownership, requests and Wayland serial handling still belong to GTK.
"""
import ctypes as C
from urllib.parse import urlsplit, unquote
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk

URI = 'text/uri-list'
CUT = 'application/x-kde-cutselection'
GNOME = 'x-special/gnome-copied-files'
FORMATS = (URI, CUT, GNOME, 'text/plain;charset=utf-8')


def file_uri(value):
    try:
        url = urlsplit(value)
        return (url.scheme in ('file', 'admin', 'trash', 'nfs', 'smb', 'sftp', 'fish', 'ftp', 'ftps',
                               'webdav', 'webdavs', 'dav', 'davs', 'mtp', 'afc')
                and '\0' not in unquote(url.path)
                and (url.scheme != 'trash' or url.path not in ('', '/'))
                and (url.scheme != 'file' or url.path.startswith('/')))
    except ValueError:
        return False


def contents(data):
    # Unsupported targets return length -1. Do not ask GI to marshal that
    # negative length as an unsigned byte array.
    return bytes(data.get_data()) if 0 < data.get_length() <= 2*1024*1024 else b''


class Target(C.Structure):
    _fields_ = [('target', C.c_char_p), ('flags', C.c_uint), ('info', C.c_uint)]


GET = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p, C.c_uint, C.c_void_p)
CLEAR = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p)
gtk = C.CDLL('libgtk-3.so.0')
gdk = C.CDLL('libgdk-3.so.0')
gdk.gdk_atom_intern_static_string.argtypes = [C.c_char_p]
gdk.gdk_atom_intern_static_string.restype = C.c_void_p
gtk.gtk_clipboard_get.argtypes = [C.c_void_p]
gtk.gtk_clipboard_get.restype = C.c_void_p
gtk.gtk_clipboard_set_with_data.argtypes = [C.c_void_p, C.POINTER(Target), C.c_uint, GET, CLEAR, C.c_void_p]
gtk.gtk_clipboard_set_with_data.restype = C.c_int
gtk.gtk_selection_data_get_target.argtypes = [C.c_void_p]
gtk.gtk_selection_data_get_target.restype = C.c_void_p
gtk.gtk_selection_data_set.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_char_p, C.c_int]
gtk.gtk_selection_data_set.restype = None


class Clipboard:
    def __init__(self, changed):
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.changed = changed
        self.urls, self.cut, self.owned = [], False, False
        self.generation = 0
        self.payloads = []
        self.native = gtk.gtk_clipboard_get(gdk.gdk_atom_intern_static_string(b'CLIPBOARD'))
        self.get_callback, self.clear_callback = GET(self.provide), CLEAR(self.cleared)
        self.signal = self.clipboard.connect('owner-change', self.owner_changed)

    def owner_changed(self, *_):
        self.generation += 1
        self.changed()

    def provide(self, _clipboard, selection, index, _data):
        data = self.payloads[index] if index < len(self.payloads) else b''
        gtk.gtk_selection_data_set(selection, gtk.gtk_selection_data_get_target(selection), 8, data, len(data))

    def cleared(self, *_):
        self.owned = False
        self.urls, self.cut, self.payloads = [], False, []
        self.changed()

    def write(self, urls, cut=False):
        if not urls: return False
        # GTK can synchronously clear the previous owner while replacing data.
        targets = (Target*len(FORMATS))(*(Target(name.encode(), 0, i) for i, name in enumerate(FORMATS)))
        accepted = gtk.gtk_clipboard_set_with_data(self.native, targets, len(targets),
                                                  self.get_callback, self.clear_callback, None)
        if not accepted: return False
        self.urls, self.cut, self.owned = list(urls), cut, True
        self.payloads = [('\r\n'.join(urls)+'\r\n').encode(), b'1' if cut else b'0',
                         (('cut' if cut else 'copy')+'\n'+'\n'.join(urls)).encode(), '\n'.join(urls).encode()]
        self.generation += 1
        self.changed()
        return True

    def read(self, callback):
        generation = self.generation
        def finish(urls, cut):
            if generation == self.generation:
                values = list(urls or [])
                callback(values if all(file_uri(url) for url in values) else [], cut, generation)
        def kde(_clipboard, data, urls):
            finish(urls, contents(data).strip() == b'1')
        def uris(_clipboard, urls, _data):
            if urls: self.clipboard.request_contents(Gdk.Atom.intern(CUT, False), kde, urls)
            else: finish([], False)
        def gnome(_clipboard, data, _extra):
            raw = contents(data)
            if len(raw) <= 2*1024*1024:
                lines = raw.decode('utf-8', errors='replace').splitlines()
                if lines and lines[0] in ('copy', 'cut'):
                    finish(lines[1:], lines[0] == 'cut'); return
            self.clipboard.request_uris(uris, None)
        self.clipboard.request_contents(Gdk.Atom.intern(GNOME, False), gnome, None)

    def bind_paste(self, item):
        """Keep a visible Paste action in sync without blocking the GTK loop."""
        alive = True
        def refresh(*_):
            item.set_sensitive(False)
            def received(urls, _cut, _generation):
                if alive: item.set_sensitive(bool(urls))
            self.read(received)
        signal = self.clipboard.connect('owner-change', refresh)
        def destroyed(*_):
            nonlocal alive
            alive = False
            self.clipboard.disconnect(signal)
        item.connect('destroy', destroyed)
        refresh()

    def complete_move(self, urls, generation):
        # Never erase something copied while a transfer or conflict was open.
        if generation != self.generation: return
        def checked(current, cut, current_generation):
            if cut and current == urls and generation == current_generation:
                # clear() releases only a selection owned by this GTK process.
                # Claim empty text after a successful cut from another app too.
                self.clipboard.set_text('', -1)
        self.read(checked)

    def dispose(self):
        if self.owned: self.clipboard.clear()
        self.clipboard.disconnect(self.signal)
