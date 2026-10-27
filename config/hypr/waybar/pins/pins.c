/* Session-local, native Waybar app pins. GTK owns pointer/keyboard DnD;
 * the Python launcher owns shortcuts and atomically saves the shared order. */
#include "waybar_cffi_module.h"
#include <json-glib/json-glib.h>
#include <string.h>

const size_t wbcffi_version = 2;

typedef struct {
    int refs;
    gboolean alive, loading, pending;
    guint refresh_id, dragging;
    GtkWidget *box, *menu;
    GtkIconTheme *icons;
    GFileMonitor *monitor;
    GAppInfoMonitor *apps;
    gulong apps_handler;
    char *helper, *snapshot;
} Pins;

typedef struct {
    Pins *owner;
    GtkWidget *button;
    char *id, *name;
    gboolean dragged;
} Pin;

typedef struct { Pins *owner; char *action, *id; } Action;
typedef struct { Pins *owner; gboolean listing; } Request;

static void schedule(Pins *p);
static void render(Pins *p, const char *text);

static Pins *retain(Pins *p) { p->refs++; return p; }
static void release(Pins *p) {
    if (--p->refs) return;
    g_free(p->helper); g_free(p->snapshot); g_free(p);
}

static void completed(GObject *source, GAsyncResult *result, gpointer data) {
    Request *request = data;
    Pins *p = request->owner;
    gchar *out = NULL, *err = NULL;
    GError *error = NULL;
    gboolean ok = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, &out, &err, &error)
                  && g_subprocess_get_successful(G_SUBPROCESS(source));
    if (p->alive) {
        if (request->listing) {
            p->loading = FALSE;
            if (ok && out && g_strcmp0(out, p->snapshot)) {
                if (p->dragging || p->menu) p->pending = TRUE;
                else render(p, out);
            }
        } else p->pending = TRUE;
        if (!ok) g_warning("Xetal bar pins: %s", error ? error->message : (err ? err : "request failed"));
        if (p->pending) schedule(p);
    }
    g_clear_error(&error); g_free(out); g_free(err);
    g_object_unref(source); release(p); g_free(request);
}

static void invoke(Pins *p, const char *action, const char *id, const char *target, const char *side) {
    const char *argv[] = {"python3", p->helper, action, id, target, side, NULL};
    GError *error = NULL;
    GSubprocess *child = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_PIPE, &error);
    if (!child) {
        if (!strcmp(action, "list")) p->loading = FALSE;
        g_warning("Xetal bar pins: %s", error->message); g_clear_error(&error); return;
    }
    Request *request = g_new0(Request, 1);
    request->owner = retain(p); request->listing = !strcmp(action, "list");
    g_subprocess_communicate_utf8_async(child, NULL, NULL, completed, request);
}

static gboolean refresh(gpointer data) {
    Pins *p = data;
    p->refresh_id = 0;
    if (!p->alive) return G_SOURCE_REMOVE;
    if (p->loading || p->dragging || p->menu) { p->pending = TRUE; return G_SOURCE_REMOVE; }
    p->pending = FALSE; p->loading = TRUE;
    invoke(p, "list", NULL, NULL, NULL);
    return G_SOURCE_REMOVE;
}

static void schedule(Pins *p) {
    if (p->alive && !p->refresh_id) p->refresh_id = g_timeout_add(100, refresh, p);
}

static void changed(GFileMonitor *monitor, GFile *file, GFile *other, GFileMonitorEvent event, gpointer data) {
    char *name = g_file_get_basename(file);
    char *destination = other ? g_file_get_basename(other) : NULL;
    if (!g_strcmp0(name, "bar-pins.json") || !g_strcmp0(name, "shortcuts.json")
            || !g_strcmp0(destination, "bar-pins.json") || !g_strcmp0(destination, "shortcuts.json")) schedule(data);
    g_free(name); g_free(destination);
}

static void apps_changed(GAppInfoMonitor *monitor, gpointer data) { schedule(data); }

static void free_pin(gpointer data) {
    Pin *pin = data;
    g_free(pin->id); g_free(pin->name); g_free(pin);
}

static void clicked(GtkButton *button, gpointer data) {
    Pin *pin = data;
    if (!pin->dragged) invoke(pin->owner, "launch", pin->id, NULL, NULL);
}

static void clear_drop(GtkWidget *widget) {
    GtkStyleContext *style = gtk_widget_get_style_context(widget);
    gtk_style_context_remove_class(style, "drop-before");
    gtk_style_context_remove_class(style, "drop-after");
}

static void drag_begin(GtkWidget *widget, GdkDragContext *context, gpointer data) {
    Pin *pin = data;
    pin->dragged = TRUE; pin->owner->dragging++;
    gtk_style_context_add_class(gtk_widget_get_style_context(widget), "dragging");
}

static void drag_end(GtkWidget *widget, GdkDragContext *context, gpointer data) {
    Pin *pin = data;
    if (pin->owner->dragging) pin->owner->dragging--;
    gtk_style_context_remove_class(gtk_widget_get_style_context(widget), "dragging");
    clear_drop(widget); schedule(pin->owner);
}

static void drag_get(GtkWidget *widget, GdkDragContext *context, GtkSelectionData *selection,
                     guint info, guint time, gpointer data) {
    Pin *pin = data;
    gtk_selection_data_set(selection, gtk_selection_data_get_target(selection), 8,
                           (const guchar *)pin->id, (gint)strlen(pin->id));
}

static gboolean drag_motion(GtkWidget *widget, GdkDragContext *context, gint x, gint y,
                            guint time, gpointer data) {
    GdkAtom target = gtk_drag_dest_find_target(widget, context, NULL);
    if (target == GDK_NONE) { gdk_drag_status(context, 0, time); return FALSE; }
    clear_drop(widget);
    gtk_style_context_add_class(gtk_widget_get_style_context(widget),
                                x < gtk_widget_get_allocated_width(widget) / 2 ? "drop-before" : "drop-after");
    gdk_drag_status(context, GDK_ACTION_MOVE, time);
    return TRUE;
}

static void drag_leave(GtkWidget *widget, GdkDragContext *context, guint time, gpointer data) { clear_drop(widget); }

static void drag_received(GtkWidget *widget, GdkDragContext *context, gint x, gint y,
                          GtkSelectionData *selection, guint info, guint time, gpointer data) {
    Pin *pin = data;
    gint length = gtk_selection_data_get_length(selection);
    gboolean valid = length > 0 && length < 4096 && gtk_selection_data_get_format(selection) == 8;
    if (valid) {
        char *id = g_strndup((const char *)gtk_selection_data_get_data(selection), length);
        invoke(pin->owner, "move", id, pin->id,
               x < gtk_widget_get_allocated_width(widget) / 2 ? "before" : "after");
        g_free(id);
    }
    clear_drop(widget);
    gtk_drag_finish(context, valid, FALSE, time);
}

static void free_action(gpointer data, GClosure *closure) {
    Action *action = data;
    release(action->owner); g_free(action->action); g_free(action->id); g_free(action);
}

static void menu_action(GtkMenuItem *item, gpointer data) {
    Action *action = data;
    if (action->owner->alive) invoke(action->owner, action->action, action->id, NULL, NULL);
}

static void add_action(GtkWidget *menu, Pin *pin, const char *label, const char *verb, gboolean enabled) {
    GtkWidget *item = gtk_menu_item_new_with_label(label);
    gtk_widget_set_sensitive(item, enabled);
    Action *action = g_new0(Action, 1);
    action->owner = retain(pin->owner); action->id = g_strdup(pin->id); action->action = g_strdup(verb);
    g_signal_connect_data(item, "activate", G_CALLBACK(menu_action), action, free_action, 0);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
}

static void menu_closed(GtkWidget *menu, gpointer data) {
    Pins *p = data;
    p->menu = NULL;
    gtk_widget_destroy(menu);
    schedule(p);
}

static gboolean button_press(GtkWidget *widget, GdkEventButton *event, gpointer data) {
    Pin *pin = data;
    if (event->button == 1) { pin->dragged = FALSE; return FALSE; }
    if (event->button != 3) return FALSE;
    Pins *p = pin->owner;
    if (p->menu) return TRUE;
    GtkWidget *menu = gtk_menu_new();
    p->menu = menu;
    GtkWidget *title = gtk_menu_item_new_with_label(pin->name);
    gtk_widget_set_sensitive(title, FALSE); gtk_menu_shell_append(GTK_MENU_SHELL(menu), title);
    gboolean available = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(widget), "available"));
    add_action(menu, pin, "Open", "launch", available);
    add_action(menu, pin, "Open in terminal", "terminal", available);
    add_action(menu, pin, "Edit shortcut…", "edit", available);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
    add_action(menu, pin, "Move left", "left", TRUE);
    add_action(menu, pin, "Move right", "right", TRUE);
    add_action(menu, pin, "Unpin from bar", "unpin", TRUE);
    g_signal_connect(menu, "selection-done", G_CALLBACK(menu_closed), p);
    gtk_widget_show_all(menu);
    gtk_menu_popup_at_pointer(GTK_MENU(menu), (GdkEvent *)event);
    return TRUE;
}

static GdkPixbuf *load_icon(Pins *p, const char *name) {
    GdkPixbuf *pixbuf = NULL;
    if (g_path_is_absolute(name)) pixbuf = gdk_pixbuf_new_from_file_at_scale(name, 22, 22, TRUE, NULL);
    else {
        GtkIconInfo *info = gtk_icon_theme_lookup_icon(p->icons, name, 22, GTK_ICON_LOOKUP_FORCE_SIZE);
        if (info) { pixbuf = gtk_icon_info_load_icon(info, NULL); g_object_unref(info); }
    }
    if (!pixbuf) pixbuf = gtk_icon_theme_load_icon(p->icons, "application-x-executable", 22, GTK_ICON_LOOKUP_FORCE_SIZE, NULL);
    return pixbuf;
}

static void render(Pins *p, const char *text) {
    JsonParser *parser = json_parser_new();
    if (!json_parser_load_from_data(parser, text, -1, NULL)
            || !JSON_NODE_HOLDS_ARRAY(json_parser_get_root(parser))) {
        g_warning("Xetal bar pins: invalid launcher response"); g_object_unref(parser); return;
    }
    GList *children = gtk_container_get_children(GTK_CONTAINER(p->box));
    for (GList *it = children; it; it = it->next) gtk_widget_destroy(it->data);
    g_list_free(children);
    JsonArray *items = json_node_get_array(json_parser_get_root(parser));
    static GtkTargetEntry targets[] = {{"application/x-xetal-bar-pin", GTK_TARGET_SAME_APP, 0}};
    for (guint i = 0; i < json_array_get_length(items); i++) {
        JsonObject *item = json_array_get_object_element(items, i);
        Pin *pin = g_new0(Pin, 1);
        pin->owner = p;
        pin->id = g_strdup(json_object_get_string_member(item, "id"));
        pin->name = g_strdup(json_object_get_string_member(item, "name"));
        GtkWidget *button = gtk_button_new(); pin->button = button;
        gtk_style_context_add_class(gtk_widget_get_style_context(button), "pin");
        gtk_widget_set_name(button, pin->id);
        gboolean available = json_object_get_boolean_member(item, "available");
        g_object_set_data(G_OBJECT(button), "available", GINT_TO_POINTER(available));
        char *tip = g_strdup_printf("%s%s\nClick to open · Drag to reorder · Right-click for options", pin->name,
                                    available ? "" : " (unavailable)");
        gtk_widget_set_tooltip_text(button, tip); g_free(tip);
        GdkPixbuf *pixbuf = load_icon(p, json_object_get_string_member(item, "icon"));
        GtkWidget *image = gtk_image_new_from_pixbuf(pixbuf);
        gtk_container_add(GTK_CONTAINER(button), image);
        gtk_box_pack_start(GTK_BOX(p->box), button, FALSE, FALSE, 0);
        g_object_set_data_full(G_OBJECT(button), "pin", pin, free_pin);
        gtk_drag_source_set(button, GDK_BUTTON1_MASK, targets, 1, GDK_ACTION_MOVE);
        gtk_drag_dest_set(button, GTK_DEST_DEFAULT_DROP, targets, 1, GDK_ACTION_MOVE);
        if (pixbuf) { gtk_drag_source_set_icon_pixbuf(button, pixbuf); g_object_unref(pixbuf); }
        g_signal_connect(button, "clicked", G_CALLBACK(clicked), pin);
        g_signal_connect(button, "button-press-event", G_CALLBACK(button_press), pin);
        g_signal_connect(button, "drag-begin", G_CALLBACK(drag_begin), pin);
        g_signal_connect(button, "drag-end", G_CALLBACK(drag_end), pin);
        g_signal_connect(button, "drag-data-get", G_CALLBACK(drag_get), pin);
        g_signal_connect(button, "drag-motion", G_CALLBACK(drag_motion), pin);
        g_signal_connect(button, "drag-leave", G_CALLBACK(drag_leave), pin);
        g_signal_connect(button, "drag-data-received", G_CALLBACK(drag_received), pin);
    }
    gtk_widget_show_all(p->box);
    GtkStyleContext *style = gtk_widget_get_style_context(p->box);
    if (json_array_get_length(items)) gtk_style_context_remove_class(style, "empty");
    else gtk_style_context_add_class(style, "empty");
    g_free(p->snapshot); p->snapshot = g_strdup(text);
    g_object_unref(parser);
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries, size_t length) {
    Pins *p = g_new0(Pins, 1);
    p->refs = 1; p->alive = TRUE;
    p->helper = g_build_filename(g_get_home_dir(), ".config/hypr/launcher/bar.py", NULL);
    /* Optional helper is useful for an isolated widget test; production uses the default. */
    for (size_t i = 0; i < length; i++) if (!strcmp(entries[i].key, "helper")) {
        JsonParser *parser = json_parser_new();
        if (json_parser_load_from_data(parser, entries[i].value, -1, NULL)) {
            const char *value = json_node_get_string(json_parser_get_root(parser));
            if (value) { g_free(p->helper); p->helper = g_strdup(value); }
        }
        g_object_unref(parser);
    }
    p->box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    gtk_widget_set_name(p->box, "xetal-pins");
    gtk_container_add(info->get_root_widget(info->obj), p->box);
    p->icons = gtk_icon_theme_new(); gtk_icon_theme_set_custom_theme(p->icons, "Papirus-Dark");
    char *directory = g_path_get_dirname(p->helper);
    GFile *file = g_file_new_for_path(directory);
    p->monitor = g_file_monitor_directory(file, G_FILE_MONITOR_WATCH_MOVES, NULL, NULL);
    if (p->monitor) g_signal_connect(p->monitor, "changed", G_CALLBACK(changed), p);
    g_object_unref(file); g_free(directory);
    p->apps = g_app_info_monitor_get();
    p->apps_handler = g_signal_connect(p->apps, "changed", G_CALLBACK(apps_changed), p);
    schedule(p);
    return p;
}

void wbcffi_deinit(void *instance) {
    Pins *p = instance;
    if (!p) return;
    p->alive = FALSE;
    if (p->refresh_id) g_source_remove(p->refresh_id);
    if (p->monitor) { g_file_monitor_cancel(p->monitor); g_object_unref(p->monitor); }
    g_signal_handler_disconnect(p->apps, p->apps_handler); g_object_unref(p->apps);
    if (p->menu) { g_signal_handlers_disconnect_by_data(p->menu, p); gtk_widget_destroy(p->menu); }
    gtk_widget_destroy(p->box); g_object_unref(p->icons);
    release(p);
}

void wbcffi_update(void *instance) { schedule(instance); }
void wbcffi_refresh(void *instance, int signal) { schedule(instance); }
