"""Run with the private GTK3_MODULES preview module and a disposable display."""
import os
from pathlib import Path
import tempfile
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf


def wait_for(condition):
    for _ in range(300):
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        if condition(): return
        time.sleep(.01)
    raise AssertionError('GTK preview did not update')


def children(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children(): yield from children(child)


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); picture = root/'picture.png'; text = root/'preset.json'
    pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 800, 400)
    pix.fill(0xff1122ff); pix.savev(str(picture), 'png', [], [])
    text.write_text('{"enabled":true}')
    for action in (Gtk.FileChooserAction.OPEN, Gtk.FileChooserAction.SAVE, Gtk.FileChooserAction.SELECT_FOLDER):
        dialog = Gtk.FileChooserDialog(title='GTK file picker', action=action)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose', Gtk.ResponseType.ACCEPT)
        dialog.set_current_folder(directory); dialog.show_all()
        wait_for(lambda: dialog.get_preview_widget() is not None)
        wait_for(lambda: any(w.get_name() == 'xetalPlacesSidebar' for w in children(dialog)))
        sidebar = next(w for w in children(dialog) if w.get_name() == 'xetalPlacesSidebar')
        wait_for(lambda: sidebar.get_model() is not None and any(row[0] == 'My Dolphin Places' for row in sidebar.get_model()))
        row = next(row for row in sidebar.get_model() if row[0] == 'My Dolphin Places')
        sidebar.row_activated(row.path, sidebar.get_column(0))
        wait_for(lambda: dialog.get_current_folder() == str(Path(os.environ['XETAL_PLACES_FILE']).parent))
        dialog.set_current_folder(directory)
        pane = dialog.get_preview_widget()
        assert pane.get_name() == 'xetalFilePreviewPane'
        assert dialog.get_action() == action
        if action == Gtk.FileChooserAction.OPEN:
            dialog.set_filename(str(picture))
            image = next(w for w in children(pane) if isinstance(w, Gtk.Image))
            wait_for(lambda: image.get_pixbuf() is not None)
            thumbnail = image.get_pixbuf(); assert thumbnail.get_width() == thumbnail.get_height()*2
            assert dialog.get_filename() == str(picture)
            dialog.set_filename(str(text))
            excerpt = next(w for w in children(pane) if isinstance(w, Gtk.TextView))
            def contents():
                b = excerpt.get_buffer(); return b.get_text(b.get_start_iter(), b.get_end_iter(), True)
            wait_for(lambda: contents() == '{"enabled":true}')
            assert not excerpt.get_editable()
            dialog.set_filename(str(picture))
        dialog.hide(); dialog.show_all()
        assert dialog.get_preview_widget() == pane
        dialog.destroy()
    # Existing application previews remain intact.
    dialog = Gtk.FileChooserDialog(title='Own preview', action=Gtk.FileChooserAction.OPEN)
    own = Gtk.Label(label='Application preview'); dialog.set_preview_widget(own); dialog.show_all()
    wait_for(lambda: dialog.get_mapped()); assert dialog.get_preview_widget() == own
    dialog.destroy()
    for _ in range(40):
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.01)
print('GTK 3: previews, image/text selection, modes, close/reopen and existing previews passed')
