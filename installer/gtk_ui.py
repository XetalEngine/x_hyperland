"""Small GTK 3 ctypes bridge shared with the Echo Linux installer design."""
import ctypes as C

class GTK:
    def __init__(self):
        try:
            self.lib = C.CDLL('libgtk-3.so.0')
            self.obj = C.CDLL('libgobject-2.0.so.0')
            self.glib = C.CDLL('libglib-2.0.so.0')
            self.pixbuf = C.CDLL('libgdk_pixbuf-2.0.so.0')
        except OSError as error:
            raise RuntimeError('Xetal Setup needs GTK 3. Install gtk3, then run Setup again.') from error
        p, i, s, d = C.c_void_p, C.c_int, C.c_char_p, C.c_double
        bindings = {
            'gtk_init_check': (i, p, p), 'gtk_main': (None,), 'gtk_main_quit': (None,),
            'gtk_window_new': (p, i), 'gtk_window_set_title': (None, p, s),
            'gtk_window_set_default_size': (None, p, i, i), 'gtk_window_set_position': (None, p, i),
            'gtk_window_set_icon_from_file': (i, p, s, p),
            'gtk_box_new': (p, i, i), 'gtk_box_pack_start': (None, p, p, i, i, C.c_uint),
            'gtk_container_add': (None, p, p), 'gtk_container_set_border_width': (None, p, C.c_uint),
            'gtk_widget_set_name': (None, p, s), 'gtk_widget_set_size_request': (None, p, i, i),
            'gtk_widget_set_hexpand': (None, p, i), 'gtk_widget_set_vexpand': (None, p, i),
            'gtk_widget_set_halign': (None, p, i), 'gtk_widget_set_valign': (None, p, i),
            'gtk_widget_set_sensitive': (None, p, i), 'gtk_widget_grab_focus': (None, p),
            'gtk_widget_show_all': (None, p), 'gtk_widget_destroy': (None, p),
            'gtk_label_new': (p, s), 'gtk_label_set_text': (None, p, s),
            'gtk_label_set_markup': (None, p, s), 'gtk_label_set_xalign': (None, p, C.c_float),
            'gtk_label_set_line_wrap': (None, p, i), 'gtk_label_set_max_width_chars': (None, p, i),
            'gtk_label_set_selectable': (None, p, i),
            'gtk_button_new_with_label': (p, s), 'gtk_button_set_label': (None, p, s),
            'gtk_entry_new': (p,), 'gtk_entry_set_text': (None, p, s), 'gtk_entry_get_text': (s, p),
            'gtk_entry_set_visibility': (None, p, i), 'gtk_entry_set_activates_default': (None, p, i),
            'gtk_dialog_new': (p,), 'gtk_dialog_add_button': (p, p, s, i),
            'gtk_dialog_get_content_area': (p, p), 'gtk_dialog_run': (i, p),
            'gtk_dialog_set_default_response': (None, p, i),
            'gtk_window_set_modal': (None, p, i),
            'gtk_scrolled_window_new': (p, p, p), 'gtk_scrolled_window_set_policy': (None, p, i, i),
            'gtk_text_view_new': (p,), 'gtk_text_view_get_buffer': (p, p),
            'gtk_text_view_set_editable': (None, p, i), 'gtk_text_view_set_monospace': (None, p, i),
            'gtk_text_view_set_wrap_mode': (None, p, i), 'gtk_text_buffer_set_text': (None, p, s, i),
            'gtk_expander_new': (p, s), 'gtk_expander_set_expanded': (None, p, i),
            'gtk_check_button_new_with_label': (p, s), 'gtk_toggle_button_set_active': (None, p, i),
            'gtk_toggle_button_get_active': (i, p), 'gtk_progress_bar_new': (p,),
            'gtk_progress_bar_set_fraction': (None, p, d),
            'gtk_image_new_from_pixbuf': (p, p), 'gtk_stack_new': (p,),
            'gtk_stack_add_named': (None, p, p, s), 'gtk_stack_set_visible_child_name': (None, p, s),
            'gtk_stack_set_transition_type': (None, p, i),
            'gtk_css_provider_new': (p,), 'gtk_css_provider_load_from_data': (i, p, s, C.c_ssize_t, p),
            'gdk_screen_get_default': (p,), 'gtk_style_context_add_provider_for_screen': (None, p, p, C.c_uint),
            'gtk_file_chooser_native_new': (p, s, p, i, s, s), 'gtk_native_dialog_run': (i, p),
            'gtk_file_chooser_get_filename': (p, p), 'gtk_file_chooser_set_current_folder': (i, p, s),
            'gtk_native_dialog_destroy': (None, p),
        }
        for name, (result, *args) in bindings.items():
            fn = getattr(self.lib, name)
            fn.restype, fn.argtypes = result, args
            setattr(self, name.removeprefix('gtk_'), fn)
        self.obj.g_signal_connect_data.argtypes = (p, s, p, p, p, i)
        self.obj.g_signal_connect_data.restype = C.c_ulong
        self.glib.g_timeout_add.argtypes = (C.c_uint, p, p)
        self.glib.g_timeout_add.restype = C.c_uint
        self.glib.g_free.argtypes = (p,)
        self.pixbuf.gdk_pixbuf_new_from_file_at_scale.argtypes = (s, i, i, i, p)
        self.pixbuf.gdk_pixbuf_new_from_file_at_scale.restype = p
        self.obj.g_object_unref.argtypes = (p,)
        self.obj.g_object_unref.restype = None
        self.callbacks = []

    def connect(self, widget, event, action, close=False):
        if close:
            callback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_void_p)(lambda *args: action())
        else:
            callback = C.CFUNCTYPE(None, C.c_void_p, C.c_void_p)(lambda *args: action())
        self.callbacks.append(callback)
        self.obj.g_signal_connect_data(widget, event.encode(), callback, None, None, 0)
