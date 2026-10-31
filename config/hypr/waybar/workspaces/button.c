/* Keep Waybar's workspace taskbar, adding close controls around its content.
 * The overlay survives Waybar 0.15 rebuilding the taskbar's inner box.
 * All changes belong to this bar instance and are undone during its teardown. */
#include "../pins/waybar_cffi_module.h"
#include <gtk-layer-shell.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
const size_t wbcffi_version = 2;

typedef struct {
    GtkWidget *button, *overlay, *content, *close, *label;
    gint margin;
    long number;
    int face;
    char *original_label;
    gulong destroy_handler, label_handler;
} Decoration;

typedef struct {
    GtkWidget *button;
    GSList *decorations;
    guint timer;
} Workspaces;

static void invoke(GtkWidget *widget, long number) {
    GtkWidget *top = gtk_widget_get_toplevel(widget);
    GdkMonitor *monitor = gtk_layer_is_layer_window(GTK_WINDOW(top)) ? gtk_layer_get_monitor(GTK_WINDOW(top)) : NULL;
    if (!monitor) monitor = gdk_display_get_monitor_at_window(gtk_widget_get_display(top), gtk_widget_get_window(top));
    if (!monitor) return;
    GdkRectangle area; gdk_monitor_get_geometry(monitor, &area);
    char *x = g_strdup_printf("%d", area.x + area.width/2);
    char *y = g_strdup_printf("%d", area.y + area.height/2);
    char *id = g_strdup_printf("%ld", number);
    char *helper = g_build_filename(g_get_home_dir(), ".config/hypr/scripts",
                                  number ? "remove-workspace.py" : "new-workspace.py", NULL);
    const char *argv[] = {"python3", helper, number ? id : x, number ? x : y, number ? y : NULL, NULL};
    GError *error = NULL;
    GSubprocess *child = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_STDOUT_SILENCE | G_SUBPROCESS_FLAGS_STDERR_SILENCE, &error);
    if (child) g_object_unref(child);
    if (error) { g_warning("Xetal workspaces: %s", error->message); g_error_free(error); }
    g_free(helper); g_free(id); g_free(x); g_free(y);
}

static gboolean cube_faces(GHashTable *faces, GHashTable *names) {
    const char *runtime = g_getenv("XDG_RUNTIME_DIR"), *signature = g_getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if (!runtime || !signature || strchr(signature, '/')) return FALSE;
    char *path = g_build_filename(runtime, "hypr", signature, "xetal-cube-faces", NULL), *data = NULL;
    g_file_get_contents(path, &data, NULL, NULL); g_free(path);
    gboolean enabled = data && g_str_has_prefix(data, "enabled\n");
    if (enabled && faces) {
        char **lines = g_strsplit(data, "\n", -1);
        for (int i=1; lines[i]; ++i) {
            long id=0; int face=0;
            if (sscanf(lines[i], "%ld %d", &id, &face) == 2 && id != 0 && face >= 1 && face <= 4)
                g_hash_table_insert(faces, GSIZE_TO_POINTER(id), GINT_TO_POINTER(face));
            char *tab = strchr(lines[i], '\t');
            if (names && tab && id != 0 && face >= 1 && face <= 4)
                g_hash_table_insert(names, g_strdup(tab+1), GSIZE_TO_POINTER(id));
        }
        g_strfreev(lines);
    }
    g_free(data); return enabled;
}

static void clicked(GtkButton *button, gpointer unused) { if (!cube_faces(NULL, NULL)) invoke(GTK_WIDGET(button), 0); }

static void remove_clicked(GtkButton *button, gpointer data) {
    Decoration *d = data;
    if (!cube_faces(NULL, NULL) && d->button && d->number > 0 && gtk_style_context_has_class(gtk_widget_get_style_context(d->button), "empty"))
        invoke(d->button, d->number);
}

static GtkWidget *find_widget(GtkWidget *widget, const char *name, gboolean by_class) {
    if (by_class ? gtk_style_context_has_class(gtk_widget_get_style_context(widget), name)
                 : !g_strcmp0(gtk_widget_get_name(widget), name)) return widget;
    if (!GTK_IS_CONTAINER(widget)) return NULL;
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget));
    GtkWidget *found = NULL;
    for (GList *it = children; it && !found; it = it->next)
        found = find_widget(it->data, name, by_class);
    g_list_free(children);
    return found;
}

static long workspace_number(GtkWidget *button) {
    if (!GTK_IS_BUTTON(button) || gtk_style_context_has_class(gtk_widget_get_style_context(button), "special")) return 0;
    GtkWidget *label = find_widget(button, "workspace-label", TRUE);
    if (!GTK_IS_LABEL(label)) return 0;
    char *name = g_strdup(gtk_label_get_text(GTK_LABEL(label))), *end = NULL;
    g_strstrip(name);
    long number = strtol(name, &end, 10);
    gboolean valid = end != name && !*end && number > 0 && number <= G_MAXINT;
    g_free(name);
    return valid ? number : 0;
}

static void label_changed(GObject *label, GParamSpec *property, gpointer data) {
    Decoration *d = data;
    if (!d->face) return;
    /* Waybar rewrites this label during workspace and window updates. Correct
     * it in the same GTK notification, before layout/paint, not on our timer. */
    char *text = g_strdup_printf("%d ", d->face);
    if (g_strcmp0(text, gtk_label_get_text(GTK_LABEL(label))))
        gtk_label_set_text(GTK_LABEL(label), text);
    g_free(text);
}

static void watch_label(Decoration *d, GtkWidget *label) {
    if (d->label == label) return;
    if (d->label) {
        g_signal_handler_disconnect(d->label, d->label_handler);
        g_object_remove_weak_pointer(G_OBJECT(d->label), (gpointer *)&d->label);
    }
    d->label = label;
    d->label_handler = 0;
    if (label) {
        g_object_add_weak_pointer(G_OBJECT(label), (gpointer *)&d->label);
        d->label_handler = g_signal_connect(label, "notify::label", G_CALLBACK(label_changed), d);
    }
}

static void workspace_destroyed(GtkWidget *widget, gpointer data) {
    Decoration *d = data;
    watch_label(d, NULL);
    d->button = d->overlay = d->content = d->close = NULL;
}

static Decoration *decorate(Workspaces *owner, GtkWidget *button) {
    GtkWidget *content = gtk_bin_get_child(GTK_BIN(button));
    if (!GTK_IS_BOX(content)) return NULL; /* Unknown future Waybar layout: leave it alone. */
    Decoration *d = g_new0(Decoration, 1);
    d->button = button; d->content = content;
    GtkWidget *label = find_widget(button, "workspace-label", TRUE);
    d->original_label = GTK_IS_LABEL(label) ? g_strdup(gtk_label_get_text(GTK_LABEL(label))) : g_strdup("");
    d->margin = gtk_widget_get_margin_end(content);
    d->overlay = gtk_overlay_new();
    g_object_ref(content);
    gtk_container_remove(GTK_CONTAINER(button), content);
    gtk_container_add(GTK_CONTAINER(d->overlay), content);
    g_object_unref(content);
    gtk_container_add(GTK_CONTAINER(button), d->overlay);
    d->close = gtk_button_new_with_label("×");
    gtk_style_context_add_class(gtk_widget_get_style_context(d->close), "workspace-remove");
    gtk_widget_set_halign(d->close, GTK_ALIGN_END);
    gtk_widget_set_valign(d->close, GTK_ALIGN_CENTER);
    gtk_widget_set_no_show_all(d->close, TRUE);
    gtk_button_set_relief(GTK_BUTTON(d->close), GTK_RELIEF_NONE);
    gtk_overlay_add_overlay(GTK_OVERLAY(d->overlay), d->close);
    g_signal_connect(d->close, "clicked", G_CALLBACK(remove_clicked), d);
    d->destroy_handler = g_signal_connect(button, "destroy", G_CALLBACK(workspace_destroyed), d);
    g_object_set_data(G_OBJECT(button), "xetal-workspace-decoration", d);
    owner->decorations = g_slist_prepend(owner->decorations, d);
    gtk_widget_show(d->overlay);
    return d;
}

static gboolean refresh(gpointer data) {
    Workspaces *owner = data;
    GHashTable *faces = g_hash_table_new(g_direct_hash, g_direct_equal);
    GHashTable *names = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
    gboolean cube = cube_faces(faces, names);
    gtk_widget_set_sensitive(owner->button, !cube);
    gtk_widget_set_tooltip_text(owner->button, cube ? "Cube uses four workspaces on each monitor" : "New empty workspace on this display");
    for (GSList *it = owner->decorations, *next; it; it = next) {
        next = it->next;
        Decoration *d = it->data;
        if (!d->button) { owner->decorations = g_slist_delete_link(owner->decorations, it); g_free(d->original_label); g_free(d); }
    }
    GtkWidget *top = gtk_widget_get_toplevel(owner->button);
    GtkWidget *box = find_widget(top, "workspaces", FALSE);
    if (!GTK_IS_BOX(box)) { g_hash_table_unref(faces); g_hash_table_unref(names); return G_SOURCE_CONTINUE; }
    GList *children = gtk_container_get_children(GTK_CONTAINER(box));
    int count = 0;
    for (GList *it = children; it; it = it->next)
        if (workspace_number(it->data) && gtk_widget_get_visible(it->data)) count++;
    for (GList *it = children; it; it = it->next) {
        GtkWidget *button = it->data;
        if (!GTK_IS_BUTTON(button)) continue;
        long number = workspace_number(button);
        if (!number && cube && !gtk_style_context_has_class(gtk_widget_get_style_context(button), "special")) {
            GtkWidget *label = find_widget(button, "workspace-label", TRUE);
            if (GTK_IS_LABEL(label)) {
                char *text = g_strdup(gtk_label_get_text(GTK_LABEL(label))); g_strstrip(text);
                number = (long)GPOINTER_TO_SIZE(g_hash_table_lookup(names, text)); g_free(text);
            }
        }
        Decoration *d = g_object_get_data(G_OBJECT(button), "xetal-workspace-decoration");
        if (!d && number) d = decorate(owner, button);
        if (!d) continue;
        if (!d->number) d->number = number;
        number = d->number;
        int face = GPOINTER_TO_INT(g_hash_table_lookup(faces, GSIZE_TO_POINTER(number)));
        d->face = cube ? face : 0;
        gtk_widget_set_visible(button, !cube || face > 0);
        GtkWidget *label = find_widget(button, "workspace-label", TRUE);
        watch_label(d, GTK_IS_LABEL(label) ? label : NULL);
        if (GTK_IS_LABEL(label)) {
            char *text = !cube && number < 0 ? g_strdup(d->original_label) : g_strdup_printf("%ld ", cube && face ? (long)face : number);
            if (g_strcmp0(text, gtk_label_get_text(GTK_LABEL(label)))) gtk_label_set_text(GTK_LABEL(label), text);
            g_free(text);
        }
        gboolean removable = !cube && number > 0 && count > 1 && gtk_style_context_has_class(gtk_widget_get_style_context(button), "empty");
        gtk_widget_set_margin_end(d->content, d->margin + (removable ? 16 : 0));
        gtk_widget_set_visible(d->close, removable);
        if (removable) {
            char *tip = g_strdup_printf("Remove empty workspace %ld", number);
            gtk_widget_set_tooltip_text(d->close, tip);
            atk_object_set_name(gtk_widget_get_accessible(d->close), tip);
            g_free(tip);
        }
    }
    g_list_free(children);
    g_hash_table_unref(faces); g_hash_table_unref(names);
    return G_SOURCE_CONTINUE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries, size_t length) {
    Workspaces *owner = g_new0(Workspaces, 1);
    GtkWidget *button = gtk_button_new_with_label("+");
    owner->button = button;
    gtk_widget_set_name(button, "new-workspace");
    gtk_widget_set_tooltip_text(button, "New empty workspace on this display\nStays here after you switch away");
    gtk_container_add(info->get_root_widget(info->obj), button);
    g_signal_connect(button, "clicked", G_CALLBACK(clicked), NULL);
    gtk_widget_show_all(button);
    owner->timer = g_timeout_add(200, refresh, owner);
    return owner;
}
void wbcffi_deinit(void *instance) {
    Workspaces *owner = instance;
    if (owner->timer) g_source_remove(owner->timer);
    for (GSList *it = owner->decorations; it; it = it->next) {
        Decoration *d = it->data;
        watch_label(d, NULL);
        if (d->button) {
            GtkWidget *label = find_widget(d->button, "workspace-label", TRUE);
            if (GTK_IS_LABEL(label) && d->number) {
                char *text = d->number < 0 ? g_strdup(d->original_label) : g_strdup_printf("%ld ", d->number);
                gtk_label_set_text(GTK_LABEL(label), text); g_free(text);
            }
            g_signal_handler_disconnect(d->button, d->destroy_handler);
            g_object_set_data(G_OBJECT(d->button), "xetal-workspace-decoration", NULL);
            gtk_widget_set_margin_end(d->content, d->margin);
            g_object_ref(d->content);
            gtk_container_remove(GTK_CONTAINER(d->overlay), d->content);
            gtk_container_remove(GTK_CONTAINER(d->button), d->overlay);
            gtk_container_add(GTK_CONTAINER(d->button), d->content);
            g_object_unref(d->content);
        }
        g_free(d->original_label); g_free(d);
    }
    g_slist_free(owner->decorations);
    gtk_widget_destroy(owner->button);
    g_free(owner);
}
void wbcffi_update(void *instance) {}
void wbcffi_refresh(void *instance, int signal) {}
