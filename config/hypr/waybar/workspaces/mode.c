/* Read-only mode indicator. Use this bar's native active workspace and the
 * persistent IDs supplied by controls.so, including Cube's renamed faces.
 * No hyprctl polling, process spawning or changes to window behavior. */
#include "../pins/waybar_cffi_module.h"
#include <json-glib/json-glib.h>
#include <string.h>
#include "../options/workspace_state.h"

const size_t wbcffi_version = 2;

typedef struct {
    GtkWidget *root, *drawing;
    GFileMonitor *monitor;
    char *path;
    guint timer;
    int workspace, display, layout;
    gboolean dirty, active, known;
} Mode;

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
    const char *names[] = {"Individual (default)", "Force tiling", "Force floating"};
    char *tip = !known ? g_strdup("Workspace mode is unavailable") : display > 0
        ? g_strdup_printf("Workspace %d · %s", display, names[mode->layout])
        : g_strdup(names[mode->layout]);
    gtk_widget_set_tooltip_text(mode->root, tip);
    atk_object_set_name(gtk_widget_get_accessible(mode->root), tip);
    g_free(tip);
    GtkStyleContext *style = gtk_widget_get_style_context(mode->root);
    const char *classes[] = {"individual", "tiling", "floating", "unavailable"};
    for (guint i = 0; i < G_N_ELEMENTS(classes); ++i) gtk_style_context_remove_class(style, classes[i]);
    gtk_style_context_add_class(style, known ? classes[mode->layout] : "unavailable");
    gtk_widget_queue_draw(mode->drawing);
    return G_SOURCE_CONTINUE;
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
    /* Both drawings have an identical 18 × 18 ink boundary in a 22 × 22
     * canvas. GTK scales these vectors for the output; no font glyph fallback. */
    cairo_translate(cr, (gtk_widget_get_allocated_width(widget) - 22) / 2.0,
                        (gtk_widget_get_allocated_height(widget) - 22) / 2.0);
    cairo_set_line_width(cr, 1.5);
    cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND);
    if (mode->layout == 2) {
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
    } else {
        for (int y = 0; y < 2; ++y)
            for (int x = 0; x < 2; ++x) cairo_rectangle(cr, 2.75 + x * 9.5, 2.75 + y * 9.5, 7, 7);
        cairo_stroke(cr);
    }
    return FALSE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries, size_t length) {
    Mode *mode = g_new0(Mode, 1);
    mode->dirty = TRUE;
    mode->path = g_build_filename(g_get_home_dir(), ".config/hypr/workspaces/rules.json", NULL);
    mode->root = gtk_event_box_new();
    gtk_event_box_set_visible_window(GTK_EVENT_BOX(mode->root), FALSE);
    gtk_widget_set_name(mode->root, "workspace-mode");
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
    if (mode->timer) g_source_remove(mode->timer);
    if (mode->monitor) { g_file_monitor_cancel(mode->monitor); g_object_unref(mode->monitor); }
    gtk_widget_destroy(mode->root);
    g_free(mode->path); g_free(mode);
}
void wbcffi_update(void *instance) { refresh(instance); }
void wbcffi_refresh(void *instance, int signal) { ((Mode *)instance)->dirty = TRUE; refresh(instance); }
