"""Delegate desktop file changes and launches to Fusion Files."""
import hashlib
import os
from gi.repository import Gio, GLib

INTERFACE = 'org.xetal.FusionFiles.Desktop1'
OBJECT = '/org/xetal/FusionFiles/Desktop'


class Files:
    def __init__(self, error, trashed=None, trash_state=None, transferred=None, renamed=None,
                 placement_target=None, placement_finished=None):
        self.error = error
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        digest = hashlib.sha256(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '').encode()).hexdigest()[:24]
        self.name = 'org.xetal.FusionFiles.Desktop.s'+digest
        self.subscriptions = []
        for signal, callback in [('TrashFinished', trashed), ('TrashStateChanged', trash_state),
                                 ('TransferFinished', transferred), ('RenameFinished', renamed),
                                 ('PlacementTarget', placement_target), ('PlacementFinished', placement_finished)]:
            if callback:
                self.subscriptions.append(self.bus.signal_subscribe(self.name, INTERFACE, signal, OBJECT,
                    None, Gio.DBusSignalFlags.NONE,
                    lambda _bus, _sender, _path, _interface, _signal, values, _data, callback=callback:
                        callback(*values.unpack()), None))

    def call(self, method, signature, *arguments, on_reply=None, quiet=False):
        def finished(bus, result, _data):
            accepted = False
            try:
                accepted = bus.call_finish(result).unpack()[0]
                if not accepted and not quiet:
                    self.error('The selected file operation is no longer available. Refresh the desktop and try again.')
            except GLib.Error as error:
                if not quiet: self.error('Could not reach Fusion Files: '+error.message)
            if on_reply: on_reply(accepted)
        self.bus.call(self.name, OBJECT, INTERFACE, method, GLib.Variant(signature, arguments),
                      GLib.VariantType.new('(b)'), Gio.DBusCallFlags.NO_AUTO_START, 5000,
                      None, finished, None)

    def open(self, urls, choose=False):
        self.call('Open', '(asb)', urls, choose)

    def transfer(self, urls, destination, copy):
        self.call('Transfer', '(assb)', urls, destination, copy)

    def refresh_trash(self):
        self.call('RefreshTrash', '()', quiet=True)

    def dispose(self):
        for identifier in self.subscriptions: self.bus.signal_unsubscribe(identifier)
        self.subscriptions.clear()
