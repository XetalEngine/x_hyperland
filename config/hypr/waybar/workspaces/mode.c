/* Mode switcher. Use this bar's native active workspace and the
 * persistent IDs supplied by controls.so, including Cube's renamed faces.
 * Changes use the locked, transactional workspace controller only on click. */
#include "../pins/waybar_cffi_module.h"
#include <json-glib/json-glib.h>
#include <pango/pangocairo.h>
#include <string.h>
#include "../options/workspace_state.h"

const size_t wbcffi_version = 2;

typedef struct {
    GtkWidget *root, *drawing;
    GFileMonitor *monitor;
    char *path;
    guint timer;
    int workspace, display, layout;
    gboolean dirty, active, known, saving, alive;
    guint refs;
} Mode;

static void release(Mode *mode) {
    if (--mode->refs) return;
    g_free(mode->path); g_free(mode);
}

static GtkWidget *find_workspaces(GtkWidget *widget) {
    if (!strcmp(gtk_widget_get_name(widget), "workspaces")) return widget;
    if (!GTK_IS_CONTAINER(widget)) return NULL;
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget));
    GtkWidget *found = NULL;
    for (GList *it = children; it && !found; it = it->next) found = find_workspaces(it->data);
    g_list_free(children);
    return found;
}

static gboolean active_workspace(GtkWidget *root, int *workspace, int *display) {
    GtkWidget *box = find_workspaces(gtk_widget_get_toplevel(root));
    if (!GTK_IS_CONTAINER(box)) return FALSE;
    GList *children = gtk_container_get_children(GTK_CONTAINER(box));
    gboolean found = FALSE;
    GtkWidget *selected = NULL;
    for (GList *it = children; it; it = it->next) {
        GtkWidget *button = it->data;
        GtkStyleContext *style = gtk_widget_get_style_context(button);
        /* .active follows global keyboard focus. .visible + .hosting-monitor
         * identifies this display's workspace, including an unfocused output
         * and configurations which show workspace buttons from every output. */
        if (!GTK_IS_BUTTON(button) || !gtk_style_context_has_class(style, "visible")
                || !gtk_style_context_has_class(style, "hosting-monitor")) continue;
        selected = button;
        if (gtk_style_context_has_class(style, "special")) break;
    }
    if (selected) {
        *workspace = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(selected), "xetal-workspace-id"));
        *display = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(selected), "xetal-workspace-display"));
        /* Wait for the decorator to attach the true ID instead of interpreting
         * Cube's displayed face number as a persistent workspace ID. Special
         * workspaces have no forced layout policy. */
        found = g_object_get_data(G_OBJECT(selected), "xetal-workspace-layout-ready") != NULL;
    }
    g_list_free(children);
    return found;
}

static gboolean refresh(gpointer data) {
    Mode *mode = data;
    int workspace = 0, display = 0;
    gboolean known = active_workspace(mode->root, &workspace, &display);
    if (!mode->dirty && workspace == mode->workspace && display == mode->display && known == mode->active)
        return G_SOURCE_CONTINUE;
    mode->active = known;
    WorkspaceModes modes = {0, 0};
    if (known && workspace > 0) known = workspace_modes(mode->path, workspace, &modes);
    mode->workspace = workspace; mode->display = display;
    mode->known = known; mode->layout = known ? modes.layout : 0; mode->dirty = FALSE;
    const char *names[] = {"Individual", "Force tiling", "Force floating", "KDE mode"};
    char *tip = !known ? g_strdup("Workspace mode is unavailable") : display > 0
        ? g_strdup_printf("Workspace %d · %s", display, names[mode->layout])
        : g_strdup(names[mode->layout]);
    if (known && workspace > 0) {
        char *old = tip;
        tip = g_strdup_printf("%s\n%s%s", old, mode->saving ? "Applying…" : "Left-click → ",
            mode->saving ? "" : names[(mode->layout + 1) % G_N_ELEMENTS(names)]);
        g_free(old);
    }
    gtk_widget_set_tooltip_text(mode->root, tip);
    atk_object_set_name(gtk_widget_get_accessible(mode->root), tip);
    g_free(tip);
    GtkStyleContext *style = gtk_widget_get_style_context(mode->root);
    const char *classes[] = {"individual", "tiling", "floating", "kde", "unavailable"};
    for (guint i = 0; i < G_N_ELEMENTS(classes); ++i) gtk_style_context_remove_class(style, classes[i]);
    gtk_style_context_add_class(style, known ? classes[mode->layout] : "unavailable");
    gtk_widget_queue_draw(mode->drawing);
    return G_SOURCE_CONTINUE;
}

static void failure(Mode *mode, const char *message) {
    if (!mode->alive) return;
    GtkWidget *top = gtk_widget_get_toplevel(mode->root);
    GtkWidget *dialog = gtk_message_dialog_new(GTK_IS_WINDOW(top) ? GTK_WINDOW(top) : NULL,
        GTK_DIALOG_DESTROY_WITH_PARENT, GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE,
        "Could not change this workspace");
    gtk_message_dialog_format_secondary_text(GTK_MESSAGE_DIALOG(dialog), "%s", message);
    g_signal_connect_swapped(dialog, "response", G_CALLBACK(gtk_widget_destroy), dialog);
    gtk_widget_show(dialog);
}

static void saved(GObject *source, GAsyncResult *result, gpointer data) {
    Mode *mode = data; GError *error = NULL; char *output = NULL, *errors = NULL;
    gboolean ok = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, &output, &errors, &error);
    mode->saving = FALSE;
    if (!ok || !g_subprocess_get_successful(G_SUBPROCESS(source)))
        failure(mode, error ? error->message : errors && *errors ? errors : "The window behavior service did not respond.");
    if (mode->alive) { mode->dirty = TRUE; refresh(mode); }
    g_free(output); g_free(errors); g_clear_error(&error); release(mode);
}

static void cycle(Mode *mode) {
    if (!mode->alive || mode->saving) return;
    /* Resolve again at click time: focus can move between timer updates. */
    mode->dirty = TRUE; refresh(mode);
    if (!mode->known || mode->workspace < 1) return;
    char number[24]; g_snprintf(number, sizeof number, "%d", mode->workspace);
    char *script = g_build_filename(g_get_home_dir(), ".config/hypr/workspaces/controller.py", NULL);
    GError *error = NULL;
    GSubprocess *process = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_PIPE,
        &error, "python3", script, "--workspace", number, "--cycle-layout", NULL);
    g_free(script);
    if (!process) { failure(mode, error->message); g_clear_error(&error); return; }
    mode->saving = TRUE; mode->refs++; mode->dirty = TRUE; refresh(mode);
    g_subprocess_communicate_utf8_async(process, NULL, NULL, saved, mode);
    g_object_unref(process);
}

static gboolean clicked(GtkWidget *widget, GdkEventButton *event, gpointer data) {
    if (event->button != 1 || event->type != GDK_BUTTON_PRESS) return FALSE;
    gtk_widget_grab_focus(widget); cycle(data); return TRUE;
}

static gboolean key_pressed(GtkWidget *widget, GdkEventKey *event, gpointer data) {
    if (event->keyval != GDK_KEY_Return && event->keyval != GDK_KEY_space) return FALSE;
    cycle(data); return TRUE;
}

static void changed(GFileMonitor *monitor, GFile *file, GFile *other, GFileMonitorEvent event, gpointer data) {
    Mode *mode = data;
    char *path = g_file_get_path(file), *destination = other ? g_file_get_path(other) : NULL;
    if (!g_strcmp0(path, mode->path) || !g_strcmp0(destination, mode->path)) {
        mode->dirty = TRUE;
        refresh(mode);
    }
    g_free(path); g_free(destination);
}

static gboolean draw(GtkWidget *widget, cairo_t *cr, gpointer data) {
    Mode *mode = data;
    GdkRGBA color;
    gtk_style_context_get_color(gtk_widget_get_style_context(mode->root), GTK_STATE_FLAG_NORMAL, &color);
    color.alpha *= mode->known ? 1.0 : 0.45;
    gdk_cairo_set_source_rgba(cr, &color);
    /* Every mode uses the same 22 × 22 canvas, so switching to the KDE
     * label never changes the button's size or moves neighboring modules. */
    cairo_translate(cr, (gtk_widget_get_allocated_width(widget) - 22) / 2.0,
                        (gtk_widget_get_allocated_height(widget) - 22) / 2.0);
    cairo_set_line_width(cr, 1.5);
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);
    if (mode->layout == 3) {
        PangoLayout *label = gtk_widget_create_pango_layout(widget, "KDE");
        PangoFontDescription *font = pango_font_description_copy(
            pango_context_get_font_description(pango_layout_get_context(label)));
        pango_font_description_set_weight(font, PANGO_WEIGHT_BOLD);
        pango_font_description_set_absolute_size(font, 10 * PANGO_SCALE);
        pango_layout_set_font_description(label, font);
        PangoRectangle ink;
        pango_layout_get_pixel_extents(label, &ink, NULL);
        double scale = MIN(1.0, MIN(20.0 / MAX(1, ink.width), 18.0 / MAX(1, ink.height)));
        cairo_save(cr);
        cairo_translate(cr, 11, 11);
        cairo_scale(cr, scale, scale);
        cairo_move_to(cr, -ink.x - ink.width / 2.0, -ink.y - ink.height / 2.0);
        pango_cairo_show_layout(cr, label);
        cairo_restore(cr);
        pango_font_description_free(font);
        g_object_unref(label);
    } else if (mode->layout == 2) {
        for (int i = 0; i < 3; ++i) {
            double x = 2.75 + i * 3;
            cairo_save(cr);
            if (i < 2) {
                cairo_rectangle(cr, 0, 0, 22, 22);
                cairo_rectangle(cr, x + 2.25, x + 2.25, 14, 14);
                cairo_set_fill_rule(cr, CAIRO_FILL_RULE_EVEN_ODD);
                cairo_clip(cr);
            }
            cairo_rectangle(cr, x, x, 10.5, 10.5);
            cairo_stroke(cr);
            cairo_restore(cr);
        }
        cairo_move_to(cr, 8.75, 12); cairo_line_to(cr, 19.25, 12); cairo_stroke(cr);
    } else if (mode->layout == 1) {
        for (int y = 0; y < 2; ++y)
            for (int x = 0; x < 2; ++x) cairo_rectangle(cr, 2.75 + x * 9.5, 2.75 + y * 9.5, 7, 7);
        cairo_stroke(cr);
    } else {
        cairo_rectangle(cr, 2.75, 2.75, 16.5, 16.5);
        cairo_move_to(cr, 2.75, 7.75); cairo_line_to(cr, 19.25, 7.75);
        cairo_stroke(cr);
    }
    return FALSE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries, size_t length) {
    Mode *mode = g_new0(Mode, 1);
    mode->refs = 1; mode->alive = TRUE;
    mode->dirty = TRUE;
    mode->path = g_build_filename(g_get_home_dir(), ".config/hypr/workspaces/rules.json", NULL);
    mode->root = gtk_event_box_new();
    gtk_event_box_set_visible_window(GTK_EVENT_BOX(mode->root), FALSE);
    /* DrawingArea owns a GdkWindow. Keep this input window above it so real
     * pointer presses reach the switcher, not just its painted child. */
    gtk_event_box_set_above_child(GTK_EVENT_BOX(mode->root), TRUE);
    gtk_widget_set_name(mode->root, "workspace-mode");
    gtk_widget_set_can_focus(mode->root, TRUE);
    gtk_widget_add_events(mode->root, GDK_BUTTON_PRESS_MASK | GDK_KEY_PRESS_MASK);
    atk_object_set_role(gtk_widget_get_accessible(mode->root), ATK_ROLE_PUSH_BUTTON);
    g_signal_connect(mode->root, "button-press-event", G_CALLBACK(clicked), mode);
    g_signal_connect(mode->root, "key-press-event", G_CALLBACK(key_pressed), mode);
    /* Local styling works with existing, personally edited bar styles too. */
    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_data(css,
        "#workspace-mode {margin:1px 2px; padding:0 6px; color:inherit;}" , -1, NULL);
    gtk_style_context_add_provider(gtk_widget_get_style_context(mode->root), GTK_STYLE_PROVIDER(css),
                                  GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(css);
    mode->drawing = gtk_drawing_area_new();
    gtk_widget_set_size_request(mode->drawing, 22, 22);
    gtk_widget_set_valign(mode->drawing, GTK_ALIGN_CENTER);
    g_signal_connect(mode->drawing, "draw", G_CALLBACK(draw), mode);
    gtk_container_add(GTK_CONTAINER(mode->root), mode->drawing);
    gtk_container_add(info->get_root_widget(info->obj), mode->root);
    gtk_widget_show_all(mode->root);
    char *directory = g_path_get_dirname(mode->path);
    GFile *file = g_file_new_for_path(directory);
    mode->monitor = g_file_monitor_directory(file, G_FILE_MONITOR_WATCH_MOVES, NULL, NULL);
    if (mode->monitor) g_signal_connect(mode->monitor, "changed", G_CALLBACK(changed), mode);
    g_object_unref(file); g_free(directory);
    refresh(mode);
    mode->timer = g_timeout_add(200, refresh, mode);
    return mode;
}

void wbcffi_deinit(void *instance) {
    Mode *mode = instance;
    mode->alive = FALSE;
    if (mode->timer) g_source_remove(mode->timer);
    if (mode->monitor) {
        g_signal_handlers_disconnect_by_data(mode->monitor, mode);
        g_file_monitor_cancel(mode->monitor); g_object_unref(mode->monitor);
    }
    gtk_widget_destroy(mode->root);
    release(mode);
}
void wbcffi_update(void *instance) { refresh(instance); }
void wbcffi_refresh(void *instance, int signal) { ((Mode *)instance)->dirty = TRUE; refresh(instance); }
