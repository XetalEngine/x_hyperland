/* Capture only tray left clicks before the application's hide/show toggle.
 * Use public GTK/dbusmenu properties, without depending on Waybar's C++ ABI.
 * Right/middle clicks and scroll remain native. Unknown items are replayed. */
#pragma once
#include <gtk/gtk.h>
#include <gtk-layer-shell.h>
#include <json-glib/json-glib.h>

typedef struct {
    int refs;
    gboolean alive, replaying;
    GtkWidget *top;
    GtkGesture *gesture;
    char *helper;
    GSList *requests, *hooks;
} FusionTray;

typedef struct { GtkWidget *item; gulong signal; } FusionTrayHook;

typedef struct {
    FusionTray *owner;
    GtkWidget *item;
    GdkEvent *event;
    GSubprocess *process;
    guint timeout;
} FusionTrayRequest;

static gboolean fusion_tray_start(FusionTray *tray, GtkWidget *item, const GdkEvent *event);

static gboolean fusion_tray_item_press(GtkWidget *item, GdkEventButton *event, gpointer data) {
    FusionTray *tray = data;
    if (!tray->alive || tray->replaying || event->button != 1) return FALSE;
    /* GTK emits an extra 2BUTTON/3BUTTON notification after the real press.
     * Capture gestures do not consume those notifications; gtkmm's after-
     * handler would otherwise send a second activation and hide the window. */
    if (event->type == GDK_2BUTTON_PRESS || event->type == GDK_3BUTTON_PRESS) return TRUE;
    return event->type == GDK_BUTTON_PRESS && fusion_tray_start(tray, item, (GdkEvent *)event);
}

static void fusion_tray_watch(FusionTray *tray, GtkWidget *item) {
    for (GSList *it = tray->hooks, *next; it; it = next) {
        next = it->next; FusionTrayHook *hook = it->data;
        if (hook->item == item) return;
        if (!hook->item) { tray->hooks = g_slist_delete_link(tray->hooks, it); g_free(hook); }
    }
    FusionTrayHook *hook = g_new0(FusionTrayHook, 1); hook->item = item;
    g_object_add_weak_pointer(G_OBJECT(item), (gpointer *)&hook->item);
    hook->signal = g_signal_connect(item, "button-press-event", G_CALLBACK(fusion_tray_item_press), tray);
    tray->hooks = g_slist_prepend(tray->hooks, hook);
}

static void fusion_tray_release(FusionTray *tray) {
    if (--tray->refs) return;
    g_object_unref(tray->top); g_free(tray->helper); g_free(tray);
}

static GtkWidget *fusion_tray_item_at(GtkWidget *widget, GtkWidget *top, double x, double y) {
    if (!gtk_widget_get_mapped(widget) || !GTK_IS_CONTAINER(widget)) return NULL;
    gboolean tray = !g_strcmp0(gtk_widget_get_name(widget), "tray");
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget));
    GtkWidget *found = NULL;
    for (GList *it = children; it && !found; it = it->next) {
        GtkWidget *child = it->data; int left, upper;
        if (tray && GTK_IS_EVENT_BOX(child) && gtk_widget_get_mapped(child) &&
                gtk_widget_translate_coordinates(child, top, 0, 0, &left, &upper) &&
                x >= left && y >= upper && x < left+gtk_widget_get_allocated_width(child) &&
                y < upper+gtk_widget_get_allocated_height(child)) found = child;
        else if (!tray) found = fusion_tray_item_at(child, top, x, y);
    }
    g_list_free(children); return found;
}

static char *fusion_tray_hint(GtkWidget *item, GtkWidget *top, const GdkEventButton *event) {
    char *bus = NULL, *menu = NULL, *tooltip = gtk_widget_get_tooltip_text(item);
    for (GList *it = gtk_menu_get_for_attach_widget(item); it && !bus; it = it->next) {
        GObject *object = G_OBJECT(it->data);
        if (g_object_class_find_property(G_OBJECT_GET_CLASS(object), "dbus-name") &&
                g_object_class_find_property(G_OBJECT_GET_CLASS(object), "dbus-object"))
            g_object_get(object, "dbus-name", &bus, "dbus-object", &menu, NULL);
    }
    if ((!bus || !*bus) && (!tooltip || !*tooltip)) {
        g_free(bus); g_free(menu); g_free(tooltip); return NULL;
    }
    int x = event->x_root, y = event->y_root;
    if (GTK_IS_WINDOW(top) && gtk_layer_is_layer_window(GTK_WINDOW(top))) {
        GdkMonitor *monitor = gtk_layer_get_monitor(GTK_WINDOW(top));
        if (monitor) { GdkRectangle geometry; gdk_monitor_get_geometry(monitor, &geometry); x += geometry.x; y += geometry.y; }
    }
    JsonBuilder *builder = json_builder_new(); json_builder_begin_object(builder);
    json_builder_set_member_name(builder, "bus"); json_builder_add_string_value(builder, bus ? bus : "");
    json_builder_set_member_name(builder, "menu"); json_builder_add_string_value(builder, menu ? menu : "");
    json_builder_set_member_name(builder, "tooltip"); json_builder_add_string_value(builder, tooltip ? tooltip : "");
    json_builder_set_member_name(builder, "x"); json_builder_add_int_value(builder, x);
    json_builder_set_member_name(builder, "y"); json_builder_add_int_value(builder, y);
    json_builder_end_object(builder);
    JsonNode *root = json_builder_get_root(builder); char *text = json_to_string(root, FALSE);
    json_node_free(root); g_object_unref(builder); g_free(bus); g_free(menu); g_free(tooltip);
    return text;
}

static gboolean fusion_tray_timeout(gpointer data) {
    FusionTrayRequest *request = data; request->timeout = 0;
    g_subprocess_force_exit(request->process); return G_SOURCE_REMOVE;
}

static void fusion_tray_completed(GObject *source, GAsyncResult *result, gpointer data) {
    FusionTrayRequest *request = data; FusionTray *tray = request->owner;
    GError *error = NULL;
    gboolean handled = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, NULL, NULL, &error)
                       && g_subprocess_get_successful(request->process);
    if (request->timeout) g_source_remove(request->timeout);
    tray->requests = g_slist_remove(tray->requests, request);
    if (tray->alive && !handled && gtk_widget_get_mapped(request->item) &&
            gtk_widget_get_toplevel(request->item) == tray->top) {
        /* Emit directly at the original item. A full event reinjection would
         * pass through the capture gesture a second time. */
        gboolean native_handled = FALSE; tray->replaying = TRUE;
        g_signal_emit_by_name(request->item, "button-press-event", request->event, &native_handled);
        tray->replaying = FALSE;
    }
    g_clear_error(&error); gdk_event_free(request->event); g_object_unref(request->item);
    g_object_unref(request->process); fusion_tray_release(tray); g_free(request);
}

static gboolean fusion_tray_start(FusionTray *tray, GtkWidget *item, const GdkEvent *event) {
    for (GSList *it = tray->requests; it; it = it->next)
        if (((FusionTrayRequest *)it->data)->item == item) return TRUE;
    char *hint = fusion_tray_hint(item, tray->top, (const GdkEventButton *)event);
    if (!hint) return FALSE;
    GError *error = NULL;
    GSubprocess *process = g_subprocess_new(G_SUBPROCESS_FLAGS_STDIN_PIPE | G_SUBPROCESS_FLAGS_STDOUT_SILENCE,
                                          &error, "python3", tray->helper, NULL);
    if (!process) { g_clear_error(&error); g_free(hint); return FALSE; }
    fusion_tray_watch(tray, item);
    FusionTrayRequest *request = g_new0(FusionTrayRequest, 1);
    request->owner = tray; tray->refs++; request->item = g_object_ref(item);
    request->event = gdk_event_copy(event); request->process = process;
    tray->requests = g_slist_prepend(tray->requests, request);
    request->timeout = g_timeout_add_seconds(8, fusion_tray_timeout, request);
    g_subprocess_communicate_utf8_async(process, hint, NULL, fusion_tray_completed, request);
    g_free(hint); return TRUE;
}

static void fusion_tray_pressed(GtkGestureMultiPress *gesture, gint count, gdouble x, gdouble y, gpointer data) {
    FusionTray *tray = data;
    if (!tray->alive || tray->replaying) return;
    const GdkEvent *event = gtk_gesture_get_last_event(GTK_GESTURE(gesture), NULL);
    if (!event || (event->type != GDK_BUTTON_PRESS && event->type != GDK_2BUTTON_PRESS &&
                   event->type != GDK_3BUTTON_PRESS) || event->button.button != 1) return;
    GtkWidget *item = fusion_tray_item_at(tray->top, tray->top, x, y);
    if (item && fusion_tray_start(tray, item, event))
        gtk_gesture_set_state(GTK_GESTURE(gesture), GTK_EVENT_SEQUENCE_CLAIMED);
}

static FusionTray *fusion_tray_new(GtkWidget *top, const char *helper) {
    FusionTray *tray = g_new0(FusionTray, 1); tray->refs = 1; tray->alive = TRUE;
    tray->top = g_object_ref(top); tray->helper = g_strdup(helper);
    tray->gesture = gtk_gesture_multi_press_new(top);
    gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(tray->gesture), 1);
    gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(tray->gesture), GTK_PHASE_CAPTURE);
    g_signal_connect(tray->gesture, "pressed", G_CALLBACK(fusion_tray_pressed), tray);
    return tray;
}

static void fusion_tray_stop(FusionTray *tray) {
    if (!tray) return;
    tray->alive = FALSE;
    gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(tray->gesture), GTK_PHASE_NONE);
    g_object_unref(tray->gesture);
    for (GSList *it = tray->hooks; it; it = it->next) {
        FusionTrayHook *hook = it->data;
        if (hook->item) {
            if (g_signal_handler_is_connected(hook->item, hook->signal))
                g_signal_handler_disconnect(hook->item, hook->signal);
            g_object_remove_weak_pointer(G_OBJECT(hook->item), (gpointer *)&hook->item);
        }
        g_free(hook);
    }
    g_slist_free(tray->hooks); tray->hooks = NULL;
    for (GSList *it = tray->requests; it; it = it->next)
        g_subprocess_force_exit(((FusionTrayRequest *)it->data)->process);
    fusion_tray_release(tray);
}
