#!/usr/bin/env python3
"""Unprivileged Setup dialog; closing it always cancels package installation."""
import ctypes as C
import json
import os
import sys

from gtk_ui import GTK
import recovery_choice as choice


def prompt(packages):
    choice.validate(packages)
    if os.geteuid() == 0:
        raise RuntimeError('The recovery choice must run as the desktop user.')
    g = GTK()
    if not g.init_check(None, None):
        return 'cancel'
    dialog = g.dialog_new()
    g.window_set_title(dialog, b'Hyper Fusion / Package recovery')
    g.window_set_default_size(dialog, 720, 440)
    g.window_set_modal(dialog, 1)
    g.window_set_position(dialog, 1)
    cancel = g.dialog_add_button(dialog, b'Cancel installation', -6)
    g.dialog_add_button(dialog, b'Retry downloads', 1)
    g.dialog_add_button(dialog, b'Continue without package rollback', 2)
    g.dialog_set_default_response(dialog, -6)
    content = g.dialog_get_content_area(dialog)
    g.container_set_border_width(content, 20)
    for text in ('Rollback packages could not be downloaded.', choice.WARNING):
        label = g.label_new(text.encode())
        g.label_set_xalign(label, 0); g.label_set_line_wrap(label, 1)
        g.label_set_max_width_chars(label, 76)
        g.box_pack_start(content, label, 0, 0, 8)
    scroll = g.scrolled_window_new(None, None)
    g.scrolled_window_set_policy(scroll, 2, 1)
    g.widget_set_size_request(scroll, -1, 180)
    g.box_pack_start(content, scroll, 1, 1, 8)
    view = g.text_view_new(); g.text_view_set_editable(view, 0)
    g.text_view_set_wrap_mode(view, 2)
    text = '\n\n'.join(p['name']+' '+p['version']+('\n'+p['error'] if p.get('error') else '') for p in packages).encode()
    g.text_buffer_set_text(g.text_view_get_buffer(view), text, len(text))
    g.container_add(scroll, view)
    def stop_if_cancelled(_):
        if choice.cancelled():
            g.dialog_response(dialog, -6)
        return 1
    callback = C.CFUNCTYPE(C.c_int, C.c_void_p)(stop_if_cancelled)
    g.callbacks.append(callback)
    timer = g.glib.g_timeout_add(200, callback, None)
    try:
        g.widget_show_all(dialog); g.widget_grab_focus(cancel)
        result = g.dialog_run(dialog)
    finally:
        g.glib.g_source_remove(timer)
        g.widget_destroy(dialog)
    return {1:'retry', 2:choice.CONTINUE}.get(result, 'cancel')


if __name__ == '__main__':
    try:
        print(prompt(json.load(sys.stdin)), flush=True)
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt):
        print('cancel', flush=True)
