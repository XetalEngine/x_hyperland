#!/usr/bin/env python3
"""A private authentication window. Passwords go only to the authentication pipe."""
import sys
from gtk_ui import GTK


def main():
    root = sys.argv[1:] == ['--root']
    g = GTK()
    if not g.init_check(None, None): return 1
    dialog = g.dialog_new()
    g.window_set_title(dialog, b'Xetal Setup / Root authentication' if root else b'Xetal Setup / Administrator authentication')
    g.window_set_default_size(dialog, 460, 180)
    g.window_set_modal(dialog, 1)
    g.window_set_position(dialog, 1)
    g.dialog_add_button(dialog, b'Cancel', -6)
    g.dialog_add_button(dialog, b'Authenticate', -5)
    g.dialog_set_default_response(dialog, -5)
    content = g.dialog_get_content_area(dialog)
    g.container_set_border_width(content, 20)
    label = g.label_new(b'Setup needs administrator access to continue.\nEnter the system root password:' if root else
                        b'Administrator access is needed for desktop packages\nand the tested Hyprland version. Enter your password:')
    g.label_set_xalign(label, 0)
    g.box_pack_start(content, label, 0, 0, 8)
    entry = g.entry_new(); g.entry_set_visibility(entry, 0); g.entry_set_activates_default(entry, 1)
    g.box_pack_start(content, entry, 0, 0, 8)
    g.widget_show_all(dialog); g.widget_grab_focus(entry)
    result = g.dialog_run(dialog)
    if result == -5:
        sys.stdout.write(g.entry_get_text(entry).decode()+'\n'); sys.stdout.flush()
    g.entry_set_text(entry, b''); g.widget_destroy(dialog)
    return 0 if result == -5 else 1


if __name__ == '__main__': sys.exit(main())
