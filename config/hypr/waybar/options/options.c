/* Native, session-owned bar context menu and reversible visibility wrappers.
 * Module roots keep their own visibility/state; hiding a wrapper never changes
 * audio, networking, notifications, the tray or a module's natural visibility.
 * GTK capture-phase gestures: https://docs.gtk.org/gtk3/class.Gesture.html */
#define _POSIX_C_SOURCE 200809L
#include "../pins/waybar_cffi_module.h"
#include "menu.h"
#include <json-glib/json-glib.h>
#include <gtk-layer-shell.h>
#include <glib/gstdio.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/file.h>
#include <unistd.h>

const size_t wbcffi_version = 2;

typedef struct { const char *id, *name, *widget, *instance, *group; } Item;
static const Item items[] = {
    {"cpu", "CPU usage", "cpu", NULL, "System"},
    {"memory", "RAM usage", "memory", NULL, "System"},
    {"custom/temperature", "Temperature", "custom-temperature", NULL, "System"},
    {"disk", "Disk usage", "disk", NULL, "System"},
    {"custom/internet", "Internet status", "custom-internet", NULL, "Network"},
    {"custom/lan", "Ethernet / LAN", "custom-lan", NULL, "Network"},
    {"custom/wifi", "Wi-Fi", "custom-wifi", NULL, "Network"},
    {"custom/vpn", "VPN", "custom-vpn", NULL, "Network"},
    {"bluetooth", "Bluetooth", "bluetooth", NULL, "Network"},
    {"mpris", "Now playing", "mpris", NULL, "Sound & tools"},
    {"group/audio", "Volume & slider", "audio", NULL, "Sound & tools"},
    {"pulseaudio#microphone", "Microphone", "pulseaudio", "microphone", "Sound & tools"},
    {"idle_inhibitor", "Keep awake", "idle_inhibitor", NULL, "Sound & tools"},
    {"custom/notifications", "Notifications", "custom-notifications", NULL, "Sound & tools"},
    {"tray", "System tray", "tray", NULL, "Sound & tools"},
    {"clock", "Date & time", "clock", NULL, "Sound & tools"},
    {"custom/power", "Power button", "custom-power", NULL, "Sound & tools"},
    {"custom/launcher", "Apps button", "custom-launcher", NULL, "Apps & workspaces"},
    {"hyprland/workspaces", "Workspaces & app icons", "workspaces", NULL, "Apps & workspaces"},
    {"cffi/new-workspace", "New workspace (+)", "new-workspace", NULL, "Apps & workspaces"},
    {"custom/keys", "Keys button", "custom-keys", NULL, "Apps & workspaces"},
    {"custom/updates", "Desktop updates", "custom-updates", NULL, "Apps & workspaces"},
    {"cffi/app-pins", "Pinned apps", "xetal-pins", NULL, "Apps & workspaces"},
};

typedef struct {
    GtkWidget *parent, *module, *wrapper;
    const Item *item;
    gboolean expand, fill;
    guint padding;
    GtkPackType pack;
} Slot;

typedef struct {
    int refs;
    gboolean alive, saving, bottom;
    GtkWidget *root, *top, *menu;
    GtkGesture *gesture;
    GSList *slots;
    guint timer;
    GFileMonitor *monitor;
    GHashTable *hidden;
    char *path;
    XetalBarOptionsMenu bridge;
} Options;

typedef struct { char *path, *id, *edge; gboolean show, reset; } Change;

static Options *retain(Options *o) { o->refs++; return o; }
static void release(gpointer data) {
    Options *o = data;
    if (--o->refs) return;
    g_hash_table_unref(o->hidden); g_free(o->path); g_free(o);
}

static GHashTable *read_options(const char *path, gboolean *bottom, GError **error) {
    *bottom = FALSE;
    GHashTable *hidden = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
    char *data = NULL;
    GError *failure = NULL;
    if (!g_file_get_contents(path, &data, NULL, &failure)) {
        if (g_error_matches(failure, G_FILE_ERROR, G_FILE_ERROR_NOENT)) { g_error_free(failure); return hidden; }
        g_propagate_error(error, failure); g_hash_table_unref(hidden); return NULL;
    }
    JsonParser *parser = json_parser_new();
    gboolean valid = json_parser_load_from_data(parser, data, -1, NULL);
    JsonNode *root = valid ? json_parser_get_root(parser) : NULL;
    JsonObject *object = root && JSON_NODE_HOLDS_OBJECT(root) ? json_node_get_object(root) : NULL;
    JsonNode *version = object ? json_object_get_member(object, "version") : NULL;
    JsonNode *array = object ? json_object_get_member(object, "hidden") : NULL;
    valid = version && json_node_get_value_type(version) == G_TYPE_INT64 && json_node_get_int(version) == 1
            && array && JSON_NODE_HOLDS_ARRAY(array);
    JsonNode *edge = object ? json_object_get_member(object, "position") : NULL;
    if (valid && edge) {
        const char *value = json_node_get_value_type(edge) == G_TYPE_STRING ? json_node_get_string(edge) : "";
        valid = !strcmp(value, "top") || !strcmp(value, "bottom");
        *bottom = !strcmp(value, "bottom");
    }
    if (valid) {
        JsonArray *values = json_node_get_array(array);
        for (guint i = 0; i < json_array_get_length(values); i++) {
            JsonNode *value = json_array_get_element(values, i);
            if (json_node_get_value_type(value) != G_TYPE_STRING) { valid = FALSE; break; }
            const char *id = json_node_get_string(value);
            if (!*id || strlen(id) > 256) { valid = FALSE; break; }
            g_hash_table_add(hidden, g_strdup(id));
        }
    }
    g_object_unref(parser); g_free(data);
    if (valid) return hidden;
    g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                        "The saved bar options are invalid. Use Show all items to reset them.");
    g_hash_table_unref(hidden); return NULL;
}

static gboolean write_change(Change *change, GError **error) {
    char *lock_path = g_strconcat(change->path, ".lock", NULL);
    int lock = g_open(lock_path, O_RDWR | O_CREAT | O_CLOEXEC, 0600); g_free(lock_path);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) {
        g_set_error(error, G_IO_ERROR, G_IO_ERROR_BUSY, "Could not save bar options: %s. Try again.", g_strerror(errno));
        if (lock >= 0) close(lock);
        return FALSE;
    }
    gboolean bottom = FALSE;
    GHashTable *hidden = read_options(change->path, &bottom, error);
    if (change->reset) {
        if (!hidden) {
            g_clear_error(error); bottom = FALSE;
            hidden = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
        } else g_hash_table_remove_all(hidden);
    }
    if (!hidden) { close(lock); return FALSE; }
    if (change->edge) bottom = !strcmp(change->edge, "bottom");
    if (!change->reset && change->id) {
        if (change->show) g_hash_table_remove(hidden, change->id);
        else g_hash_table_add(hidden, g_strdup(change->id));
    }
    JsonBuilder *builder = json_builder_new();
    json_builder_begin_object(builder);
    json_builder_set_member_name(builder, "version"); json_builder_add_int_value(builder, 1);
    json_builder_set_member_name(builder, "position"); json_builder_add_string_value(builder, bottom ? "bottom" : "top");
    json_builder_set_member_name(builder, "hidden"); json_builder_begin_array(builder);
    GList *keys = g_list_sort(g_hash_table_get_keys(hidden), (GCompareFunc)g_strcmp0);
    for (GList *it = keys; it; it = it->next) json_builder_add_string_value(builder, it->data);
    g_list_free(keys); json_builder_end_array(builder); json_builder_end_object(builder);
    JsonNode *root = json_builder_get_root(builder);
    JsonGenerator *generator = json_generator_new(); json_generator_set_root(generator, root);
    json_generator_set_pretty(generator, TRUE);
    char *data = json_generator_to_data(generator, NULL);
    gboolean success = g_file_set_contents_full(change->path, data, -1,
        G_FILE_SET_CONTENTS_CONSISTENT | G_FILE_SET_CONTENTS_DURABLE, 0600, error);
    g_free(data); g_object_unref(generator); json_node_free(root); g_object_unref(builder);
    g_hash_table_unref(hidden); close(lock);
    return success;
}

static void apply_hidden(Options *o) {
    for (GSList *it = o->slots; it; it = it->next) {
        Slot *slot = it->data;
        gtk_widget_set_visible(slot->wrapper, !g_hash_table_contains(o->hidden, slot->item->id));
    }
}

static void apply_position(Options *o) {
    if (!o->top || !gtk_layer_is_layer_window(GTK_WINDOW(o->top))) return;
    GtkWindow *window = GTK_WINDOW(o->top);
    /* Changing the real layer anchors also moves the compositor's reserved
     * workarea. GTK popups flip inward at either edge. No bar restart needed. */
    if (gtk_layer_get_anchor(window, GTK_LAYER_SHELL_EDGE_TOP) != !o->bottom
            || gtk_layer_get_anchor(window, GTK_LAYER_SHELL_EDGE_BOTTOM) != o->bottom) {
        gtk_layer_set_anchor(window, o->bottom ? GTK_LAYER_SHELL_EDGE_TOP : GTK_LAYER_SHELL_EDGE_BOTTOM, FALSE);
        gtk_layer_set_anchor(window, o->bottom ? GTK_LAYER_SHELL_EDGE_BOTTOM : GTK_LAYER_SHELL_EDGE_TOP, TRUE);
        GtkStyleContext *style = gtk_widget_get_style_context(o->top);
        gtk_style_context_remove_class(style, o->bottom ? "top" : "bottom");
        gtk_style_context_add_class(style, o->bottom ? "bottom" : "top");
        gtk_widget_queue_draw(o->top);
    }
}

static void reload_options(Options *o) {
    GError *error = NULL;
    gboolean bottom;
    GHashTable *hidden = read_options(o->path, &bottom, &error);
    if (hidden) {
        g_hash_table_unref(o->hidden); o->hidden = hidden; o->bottom = bottom;
        apply_hidden(o); apply_position(o);
    }
    if (error) { g_warning("Xetal bar options: %s", error->message); g_error_free(error); }
}

static void changed(GFileMonitor *monitor, GFile *file, GFile *other, GFileMonitorEvent event, gpointer data) {
    Options *o = data;
    char *path = g_file_get_path(file), *destination = other ? g_file_get_path(other) : NULL;
    if (o->alive && (!g_strcmp0(path, o->path) || !g_strcmp0(destination, o->path))) reload_options(o);
    g_free(path); g_free(destination);
}

static void change_free(gpointer data) {
    Change *change = data; g_free(change->path); g_free(change->id); g_free(change->edge); g_free(change);
}

static void save_thread(GTask *task, gpointer source, gpointer data, GCancellable *cancel) {
    GError *error = NULL;
    if (write_change(data, &error)) g_task_return_boolean(task, TRUE);
    else g_task_return_error(task, error);
}

static void saved(GObject *source, GAsyncResult *result, gpointer data) {
    Options *o = data; GError *error = NULL;
    g_task_propagate_boolean(G_TASK(result), &error);
    if (o->alive) {
        o->saving = FALSE; reload_options(o);
        if (error) {
            GtkWidget *dialog = gtk_message_dialog_new(GTK_WINDOW(o->top), GTK_DIALOG_DESTROY_WITH_PARENT,
                GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "%s", error->message);
            g_signal_connect_swapped(dialog, "response", G_CALLBACK(gtk_widget_destroy), dialog);
            gtk_widget_show(dialog);
        }
    }
    g_clear_error(&error); release(o);
}

static void save(Options *o, const char *id, gboolean show, gboolean reset, const char *edge) {
    if (!o->alive || o->saving) return;
    o->saving = TRUE;
    Change *change = g_new0(Change, 1);
    change->path = g_strdup(o->path); change->id = g_strdup(id); change->show = show; change->reset = reset;
    change->edge = g_strdup(edge);
    GTask *task = g_task_new(NULL, NULL, saved, retain(o));
    g_task_set_task_data(task, change, change_free); g_task_run_in_thread(task, save_thread); g_object_unref(task);
}

static void toggled(GtkCheckMenuItem *item, gpointer data) {
    save(data, g_object_get_data(G_OBJECT(item), "module-id"), gtk_check_menu_item_get_active(item), FALSE, NULL);
}

static void reset(GtkMenuItem *item, gpointer data) { save(data, NULL, TRUE, TRUE, NULL); }

static void edge_toggled(GtkCheckMenuItem *item, gpointer data) {
    if (gtk_check_menu_item_get_active(item))
        save(data, NULL, FALSE, FALSE, g_object_get_data(G_OBJECT(item), "bar-position"));
}

static GtkWidget *submenu(gpointer data) {
    Options *o = data; reload_options(o);
    GtkWidget *menu = gtk_menu_new();
    gtk_style_context_add_class(gtk_widget_get_style_context(menu), "xetal-bar-options");
    g_object_set_data_full(G_OBJECT(menu), "owner", retain(o), release);
    GtkWidget *heading = gtk_menu_item_new_with_label("Taskbar position");
    gtk_widget_set_sensitive(heading, FALSE);
    gtk_style_context_add_class(gtk_widget_get_style_context(heading), "section");
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), heading);
    GSList *edges = NULL;
    for (int i = 0; i < 2; i++) {
        GtkWidget *item = gtk_radio_menu_item_new_with_label(edges, i ? "Bottom" : "Top");
        edges = gtk_radio_menu_item_get_group(GTK_RADIO_MENU_ITEM(item));
        gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(item), o->bottom == i);
        gtk_widget_set_sensitive(item, !o->saving);
        g_object_set_data(G_OBJECT(item), "bar-position", i ? "bottom" : "top");
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
    }
    /* Connect after both initial states are set, so opening Options never saves. */
    for (GSList *it = edges; it; it = it->next)
        g_signal_connect(it->data, "toggled", G_CALLBACK(edge_toggled), o);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
    const char *group = NULL;
    for (guint i = 0; i < G_N_ELEMENTS(items); i++) {
        if (g_strcmp0(group, items[i].group)) {
            if (group) gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
            group = items[i].group;
            GtkWidget *heading = gtk_menu_item_new_with_label(group);
            gtk_widget_set_sensitive(heading, FALSE);
            gtk_style_context_add_class(gtk_widget_get_style_context(heading), "section");
            gtk_menu_shell_append(GTK_MENU_SHELL(menu), heading);
        }
        GtkWidget *item = gtk_check_menu_item_new_with_label(items[i].name);
        gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(item), !g_hash_table_contains(o->hidden, items[i].id));
        gtk_widget_set_sensitive(item, !o->saving);
        g_object_set_data(G_OBJECT(item), "module-id", (gpointer)items[i].id);
        g_signal_connect(item, "toggled", G_CALLBACK(toggled), o);
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
    }
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
    GtkWidget *all = gtk_menu_item_new_with_label("Show all items");
    gtk_widget_set_sensitive(all, !o->saving);
    g_signal_connect(all, "activate", G_CALLBACK(reset), o);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), all);
    gtk_widget_show_all(menu); return menu;
}

static gboolean matches(GtkWidget *widget, const Item *item) {
    if (!g_strcmp0(gtk_widget_get_name(widget), item->widget)
            && (!item->instance || gtk_style_context_has_class(gtk_widget_get_style_context(widget), item->instance))) return TRUE;
    if (!GTK_IS_CONTAINER(widget)) return FALSE;
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget)); gboolean result = FALSE;
    for (GList *it = children; it && !result; it = it->next) result = matches(it->data, item);
    g_list_free(children); return result;
}

static int position(GtkWidget *parent, GtkWidget *child) {
    /* get_children() reverses pack-end children; reorder_child() needs the
     * actual packing position, not that visual traversal index. */
    int index = -1;
    gtk_container_child_get(GTK_CONTAINER(parent), child, "position", &index, NULL);
    return index;
}

static void pack(GtkWidget *parent, GtkWidget *child, Slot *slot, int index) {
    if (slot->pack == GTK_PACK_END) gtk_box_pack_end(GTK_BOX(parent), child, slot->expand, slot->fill, slot->padding);
    else gtk_box_pack_start(GTK_BOX(parent), child, slot->expand, slot->fill, slot->padding);
    gtk_box_reorder_child(GTK_BOX(parent), child, index);
}

static void wrap(Options *o, GtkWidget *parent, GtkWidget *module, const Item *item) {
    Slot *slot = g_new0(Slot, 1); slot->item = item;
    slot->parent = g_object_ref(parent); slot->module = g_object_ref(module);
    gtk_box_query_child_packing(GTK_BOX(parent), module, &slot->expand, &slot->fill, &slot->padding, &slot->pack);
    int index = position(parent, module);
    slot->wrapper = g_object_ref_sink(gtk_box_new(gtk_orientable_get_orientation(GTK_ORIENTABLE(parent)), 0));
    g_object_set_data(G_OBJECT(slot->wrapper), "xetal-bar-slot", slot);
    gtk_widget_set_no_show_all(slot->wrapper, TRUE);
    gtk_container_remove(GTK_CONTAINER(parent), module);
    gtk_container_add(GTK_CONTAINER(slot->wrapper), module);
    pack(parent, slot->wrapper, slot, index);
    gtk_widget_set_visible(slot->wrapper, !g_hash_table_contains(o->hidden, item->id));
    o->slots = g_slist_prepend(o->slots, slot);
}

static void slot_free(Slot *slot) {
    if (gtk_widget_get_parent(slot->wrapper) == slot->parent
            && gtk_widget_get_parent(slot->module) == slot->wrapper
            && !gtk_widget_in_destruction(slot->parent)) {
        int index = position(slot->parent, slot->wrapper);
        gtk_container_remove(GTK_CONTAINER(slot->wrapper), slot->module);
        gtk_container_remove(GTK_CONTAINER(slot->parent), slot->wrapper);
        pack(slot->parent, slot->module, slot, index);
    }
    gtk_widget_destroy(slot->wrapper);
    g_object_unref(slot->wrapper); g_object_unref(slot->module); g_object_unref(slot->parent); g_free(slot);
}

static void discover(Options *o, GtkWidget *widget) {
    if (!GTK_IS_CONTAINER(widget)) return;
    GtkStyleContext *style = gtk_widget_get_style_context(widget);
    gboolean region = GTK_IS_BOX(widget) && (gtk_style_context_has_class(style, "modules-left")
        || gtk_style_context_has_class(style, "modules-center") || gtk_style_context_has_class(style, "modules-right"));
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget));
    for (GList *it = children; it; it = it->next) {
        GtkWidget *child = it->data;
        if (region) {
            if (g_object_get_data(G_OBJECT(child), "xetal-bar-slot")) continue;
            for (guint i = 0; i < G_N_ELEMENTS(items); i++) {
                if (matches(child, &items[i])) { wrap(o, widget, child, &items[i]); break; }
            }
        } else discover(o, child);
    }
    g_list_free(children);
}

static const char *at_point(Options *o, double x, double y) {
    for (GSList *it = o->slots; it; it = it->next) {
        Slot *slot = it->data; int left, top;
        if (gtk_widget_get_mapped(slot->wrapper) && gtk_widget_translate_coordinates(slot->wrapper, o->top, 0, 0, &left, &top)
                && x >= left && y >= top && x < left + gtk_widget_get_allocated_width(slot->wrapper)
                && y < top + gtk_widget_get_allocated_height(slot->wrapper)) return slot->item->id;
    }
    return "";
}

static void execute(GtkMenuItem *item, gpointer data) {
    const char *command = data; GError *error = NULL;
    g_spawn_command_line_async(command, &error);
    if (error) { g_warning("Xetal bar action: %s", error->message); g_error_free(error); }
}

static void add_action(GtkWidget *menu, const char *title, const char *command) {
    GtkWidget *item = gtk_menu_item_new_with_label(title);
    g_signal_connect(item, "activate", G_CALLBACK(execute), (gpointer)command);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
}

static void closed(GtkWidget *menu, gpointer data) {
    Options *o = data; o->menu = NULL; gtk_widget_destroy(menu);
}

static void pressed(GtkGestureMultiPress *gesture, gint count, gdouble x, gdouble y, gpointer data) {
    Options *o = data;
    if (!o->alive || count != 1 || o->menu) return;
    const char *id = at_point(o, x, y);
    /* Tray menus belong to their applications; pins append our Options submenu. */
    if (!strcmp(id, "tray") || !strcmp(id, "cffi/app-pins")) return;
    gtk_gesture_set_state(GTK_GESTURE(gesture), GTK_EVENT_SEQUENCE_CLAIMED);
    GtkWidget *menu = gtk_menu_new(); o->menu = menu;
    xetal_append_bar_options(menu, o->root, FALSE);
    if (!strcmp(id, "group/audio") || !strcmp(id, "pulseaudio#microphone") || !strcmp(id, "mpris")
            || !strcmp(id, "custom/notifications") || !strcmp(id, "cpu") || !strcmp(id, "custom/launcher") || !strcmp(id, "custom/power")) {
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
        if (!strcmp(id, "group/audio")) add_action(menu, "Mute / unmute output", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle");
        if (!strcmp(id, "pulseaudio#microphone")) add_action(menu, "Mute / unmute microphone", "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle");
        if (!strcmp(id, "mpris")) add_action(menu, "Next track", "playerctl next");
        if (!strcmp(id, "custom/notifications")) add_action(menu, "Toggle Do Not Disturb", "swaync-client -d");
        if (!strcmp(id, "cpu")) {
            char *path = g_build_filename(g_get_home_dir(), ".config/hypr/kitty.conf", NULL);
            char *quoted = g_shell_quote(path), *command = g_strconcat("kitty --config ", quoted, " -e htop", NULL);
            add_action(menu, "Task monitor", command);
            g_object_set_data_full(G_OBJECT(menu), "task-command", command, g_free);
            g_free(quoted); g_free(path);
        }
        if (!strcmp(id, "custom/launcher")) {
            char *script = g_build_filename(g_get_home_dir(), ".config/hypr/scripts/control-center.sh", NULL);
            char *quoted = g_shell_quote(script), *command = g_strconcat(quoted, " --tab system", NULL);
            add_action(menu, "Fusion Settings", command);
            g_object_set_data_full(G_OBJECT(menu), "control-command", command, g_free);
            g_free(quoted); g_free(script);
        }
        if (!strcmp(id, "custom/power")) {
            char *path = g_build_filename(g_get_home_dir(), ".config/hypr/hyprlock.conf", NULL);
            char *quoted = g_shell_quote(path), *command = g_strconcat("hyprlock --config ", quoted, NULL);
            add_action(menu, "Lock screen", command);
            g_object_set_data_full(G_OBJECT(menu), "lock-command", command, g_free);
            g_free(quoted); g_free(path);
        }
    }
    g_signal_connect(menu, "selection-done", G_CALLBACK(closed), o);
    gtk_widget_show_all(menu);
    const GdkEvent *event = gtk_gesture_get_last_event(GTK_GESTURE(gesture), NULL);
    gtk_menu_popup_at_pointer(GTK_MENU(menu), event);
}

static gboolean refresh(gpointer data) {
    Options *o = data;
    GtkWidget *top = gtk_widget_get_toplevel(o->root);
    if (!GTK_IS_WINDOW(top)) return G_SOURCE_CONTINUE;
    if (!o->top) {
        o->top = g_object_ref(top);
        o->bridge = (XetalBarOptionsMenu){submenu, o};
        g_object_set_data(G_OBJECT(top), "xetal-bar-options", &o->bridge);
        gtk_widget_add_events(top, GDK_BUTTON_PRESS_MASK | GDK_BUTTON_RELEASE_MASK);
        o->gesture = gtk_gesture_multi_press_new(top);
        gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(o->gesture), 3);
        gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(o->gesture), GTK_PHASE_CAPTURE);
        g_signal_connect(o->gesture, "pressed", G_CALLBACK(pressed), o);
    }
    for (GSList *it = o->slots, *next; it; it = next) {
        next = it->next; Slot *slot = it->data;
        if (gtk_widget_get_parent(slot->module) != slot->wrapper || gtk_widget_get_parent(slot->wrapper) != slot->parent) {
            o->slots = g_slist_delete_link(o->slots, it); slot_free(slot);
        }
    }
    discover(o, top); apply_position(o); return G_SOURCE_CONTINUE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries, size_t length) {
    Options *o = g_new0(Options, 1); o->refs = 1; o->alive = TRUE;
    o->path = g_build_filename(g_get_home_dir(), ".config/hypr/waybar/options.json", NULL);
    for (size_t i = 0; i < length; i++) if (!strcmp(entries[i].key, "state_path")) {
        JsonParser *parser = json_parser_new();
        if (json_parser_load_from_data(parser, entries[i].value, -1, NULL)
                && json_node_get_value_type(json_parser_get_root(parser)) == G_TYPE_STRING) {
            g_free(o->path); o->path = g_strdup(json_node_get_string(json_parser_get_root(parser)));
        }
        g_object_unref(parser);
    }
    o->hidden = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
    o->root = g_object_ref_sink(gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0));
    gtk_widget_set_name(o->root, "xetal-bar-options-controller");
    gtk_container_add(info->get_root_widget(info->obj), o->root);
    /* No visible button is needed; the window itself owns the right-click target. */
    gtk_widget_set_no_show_all(o->root, TRUE);
    char *directory = g_path_get_dirname(o->path); GFile *file = g_file_new_for_path(directory);
    o->monitor = g_file_monitor_directory(file, G_FILE_MONITOR_WATCH_MOVES, NULL, NULL);
    if (o->monitor) g_signal_connect(o->monitor, "changed", G_CALLBACK(changed), o);
    g_object_unref(file); g_free(directory);
    reload_options(o); o->timer = g_timeout_add(200, refresh, o);
    return o;
}

void wbcffi_deinit(void *instance) {
    Options *o = instance; o->alive = FALSE;
    if (o->timer) g_source_remove(o->timer);
    if (o->monitor) { g_file_monitor_cancel(o->monitor); g_object_unref(o->monitor); }
    if (o->menu) { g_signal_handlers_disconnect_by_data(o->menu, o); gtk_widget_destroy(o->menu); }
    if (o->top) g_object_set_data(G_OBJECT(o->top), "xetal-bar-options", NULL);
    if (o->gesture) {
        gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(o->gesture), GTK_PHASE_NONE);
        g_object_unref(o->gesture);
    }
    g_slist_free_full(o->slots, (GDestroyNotify)slot_free);
    gtk_widget_destroy(o->root); g_object_unref(o->root);
    if (o->top) g_object_unref(o->top);
    release(o);
}
void wbcffi_update(void *instance) {}
void wbcffi_refresh(void *instance, int signal) { reload_options(instance); }
