"""Apply the viewed image using the desktop's existing display picker and store."""
from pathlib import Path
import sys
import tempfile

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QDialog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wallpaper.browser import ScreenPicker, backend, settings
from wallpaper.carousel import Thumbnails
from wallpaper.jobs import Jobs
from wallpaper.library import Picture, active_screens


class WallpaperAction(QObject):
    message = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.owner = parent
        self.jobs = Jobs(self)
        self.thumbnails = Thumbnails(parent)
        self.thumbnails.hide()
        self.busy = False
        self.temporary = None
        self.dialog = None

    def start(self, source, image, rotation=0):
        if self.busy or self.jobs.stopped or image.isNull(): return
        self.busy = True
        self.message.emit('Reading your displays…')
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='xetal-images-wallpaper-')
        except OSError as error:
            self.failed(str(error)); return
        path = Path(self.temporary.name)/'wallpaper.png'
        # Capture the current frame and orientation, including animated images
        # and EXIF orientation. Only the managed wallpaper copy is written.
        def prepare():
            models = settings.display_models(settings.monitors())
            if not active_screens(models): raise ValueError('No active display was found. Connect a display and try again.')
            current = backend.read_wallpapers()
            snapshot = image.transformed(QTransform().rotate(rotation)) if rotation else image
            if not snapshot.save(str(path), 'PNG'): raise OSError('Could not prepare this image as a wallpaper.')
            return models, current
        picture = Picture(str(path), 'Fusion Viewer', Path(source).name)
        self.jobs.run(prepare, lambda result: self.choose(picture, str(source), result), self.failed)

    def choose(self, picture, source, result):
        models, current = result
        screens = active_screens(models)
        if len(screens) == 1:
            self.apply(picture, source, screens[0], current); return
        self.message.emit('Choose a display for this wallpaper.')
        self.dialog = ScreenPicker(models, current, picture, self.thumbnails, self.owner,
                                   cancel_text='Back to image')
        dialog = self.dialog
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        selected = dialog.selected
        self.dialog = None
        dialog.deleteLater()
        if self.jobs.stopped: return
        if accepted and selected:
            self.apply(picture, source, selected, current)
        else:
            self.finish('')

    def apply(self, picture, source, monitor, current):
        name = monitor['name']
        self.message.emit('Applying wallpaper to '+name+'…')
        choice = {'path': picture.path, 'original': source, 'fit': 'cover'}
        self.jobs.run(lambda: backend.apply_wallpapers({name: choice}, current),
                      lambda _: self.finish('Wallpaper applied to '+name+'.'), self.failed)

    def failed(self, message):
        self.finish('Could not set wallpaper: '+message)

    def finish(self, message):
        if self.temporary:
            self.temporary.cleanup(); self.temporary = None
        self.busy = False
        self.message.emit(message)

    def shutdown(self):
        if self.dialog: self.dialog.reject()
        # Let any already-authorized wallpaper transaction finish before the
        # viewer exits; discard queued UI callbacks and then remove its staging copy.
        self.jobs.shutdown(cancel_queued=True)
        self.thumbnails.jobs.shutdown(cancel_queued=True)
        self.finish('')
