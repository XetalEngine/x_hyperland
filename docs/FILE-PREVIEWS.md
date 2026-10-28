# File picker previews

File pickers show a preview pane on the right. Select a file with the mouse or
keyboard to update it. Images retain their aspect ratio; animated images show
one still frame. The pane includes the filename, type, size and modification
time. Qt dialogs also show image dimensions and the creation time when the
filesystem provides it.

Text files show a read-only excerpt (up to 64 KiB); folders show up to 40 entries.
Unsupported files still have a details pane. Large images are limited before
loading, and loading happens in the background. The pane scrolls when necessary
so the Open, Save and Cancel buttons remain accessible. Selecting a file never
executes it. Device files, pipes and sockets are not read for previews.

## Coverage

- Every standard file picker in Xetal's Python tools, including Cube ceiling,
  floor and sky images, wallpapers, shortcut icons/programs/folders, context
  menu presets, hotkey presets and the image viewer.
- Qt 5/6 Widgets applications using the private `xetal` platform theme, including
  ordinary open, save, multiple-selection and folder dialogs. Static
  `QFileDialog` convenience functions are covered too.
- Standard GTK 3 file chooser widgets/dialogs in applications inheriting the
  Hyprland environment. An application's existing preview widget is preserved.

Reopen existing applications after upgrading. Newly launched session tools pick
up the Python changes immediately; native modules are loaded when an application
starts. A new login also supplies the GTK module to applications whose parents
were already running before the upgrade.

Hyprland cannot add widgets inside an arbitrary application's custom file picker.
GTK 4, Qt Quick custom pickers, Flatpak runtimes with separate libraries, and
separately running portal processes are not covered by these toolkit hooks.
Existing portal services are not restarted or replaced. These cases need
integration with their own picker or portal backend; this does not claim to
modify every third-party dialog.

## Isolation and installation

`theme/file_preview.py` supplies the common Python pane and
`theme/file_preview.hpp` extends the native Qt theme. They share a marker to
prevent duplicate panes. `theme/gtk_file_preview.c` uses GTK 3's
[preview widget API](https://docs.gtk.org/gtk3/method.FileChooser.set_preview_widget.html).
Its module is loaded through the Hyprland-only
[`GTK3_MODULES` environment variable](https://docs.gtk.org/gtk3/running.html#environment-variables),
leaving GTK 2 modules and shared GTK settings alone. The Qt implementation uses
[QFileDialog](https://doc.qt.io/qt-6/qfiledialog.html) and leaves selection, filters,
confirmation and cancellation to the original dialog.

The installer builds all three native modules from the included source and
checks for their outputs. Session startup and theme application rebuild them
when sources or installed toolkit versions change. No system module directory,
KDE configuration, shared GTK/Qt setting or portal activation environment is
modified.
