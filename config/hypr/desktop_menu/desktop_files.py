"""Delegate desktop file changes and launches to Fusion Files."""
import hashlib
import os
from gi.repository import Gio, GLib

INTERFACE = 'org.xetal.FusionFiles.Desktop1'
OBJECT = '/org/xetal/FusionFiles/Desktop'


class Files:
    def __init__(self, error):
        self.error = error
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        digest = hashlib.sha256(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '').encode()).hexdigest()[:24]
        self.name = 'org.xetal.FusionFiles.Desktop.s'+digest

    def call(self, method, signature, *arguments):
        def finished(bus, result, _data):
            try:
                if not bus.call_finish(result).unpack()[0]:
                    self.error('The selected file operation is no longer available. Refresh the desktop and try again.')
            except GLib.Error as error:
                self.error('Could not reach Fusion Files: '+error.message)
        self.bus.call(self.name, OBJECT, INTERFACE, method, GLib.Variant(signature, arguments),
                      GLib.VariantType.new('(b)'), Gio.DBusCallFlags.NO_AUTO_START, 5000,
                      None, finished, None)

    def open(self, urls, choose=False):
        self.call('Open', '(asb)', urls, choose)

    def transfer(self, urls, destination, copy):
        self.call('Transfer', '(assb)', urls, destination, copy)
