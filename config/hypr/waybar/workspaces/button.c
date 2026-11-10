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
    gboolean minimized, stash;
    char *original_label, *original_tooltip;
    gulong destroy_handler, label_handler;
} Decoration;

typedef struct {
    GtkWidget *button;
    GSList *decorations;
    guint timer, feedback_tick;
    gint64 feedback_started;
    gboolean cube;
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

static void stop_feedback(Workspaces *owner) {
    if (owner->feedback_tick) gtk_widget_remove_tick_callback(owner->button, owner->feedback_tick);
    owner->feedback_tick = 0;
    gtk_style_context_remove_class(gtk_widget_get_style_context(owner->button), "cube-blocked");
    gtk_widget_set_margin_start(owner->button, 3);
    gtk_widget_set_margin_end(owner->button, 3);
}

static gboolean feedback_frame(GtkWidget *button, GdkFrameClock *clock, gpointer data) {
    Workspaces *owner = data;
    gint64 elapsed = gdk_frame_clock_get_frame_time(clock) - owner->feedback_started;
    if (elapsed >= 550000) {
        owner->feedback_tick = 0;
        stop_feedback(owner);
        return G_SOURCE_REMOVE;
    }
    static const int offsets[] = {0, -3, 3, -3, 3, -2, 2, -1, 1, 0};
    guint step = MAX(elapsed, 0) / 40000;
    int offset = step < G_N_ELEMENTS(offsets) ? offsets[step] : 0;
    /* Constant total margin: shake only this button, never its neighbours. */
    gtk_widget_set_margin_start(button, 3 + offset);
    gtk_widget_set_margin_end(button, 3 - offset);
    return G_SOURCE_CONTINUE;
}

static void update_add_button(Workspaces *owner, gboolean cube) {
    owner->cube = cube;
    const char *tip = cube ? "Not available with 3D Cube on" : "New empty workspace on this display";
    GtkStyleContext *context = gtk_widget_get_style_context(owner->button);
    if (cube) gtk_style_context_add_class(context, "cube-unavailable");
    else { gtk_style_context_remove_class(context, "cube-unavailable"); stop_feedback(owner); }
    gtk_widget_set_tooltip_text(owner->button, tip);
    atk_object_set_description(gtk_widget_get_accessible(owner->button), tip);
}

static void clicked(GtkButton *button, gpointer data) {
    Workspaces *owner = data;
    gboolean cube = cube_faces(NULL, NULL);
    if (cube != owner->cube) update_add_button(owner, cube);
    if (!cube) { invoke(GTK_WIDGET(button), 0); return; }
    owner->feedback_started = g_get_monotonic_time();
    gtk_style_context_add_class(gtk_widget_get_style_context(owner->button), "cube-blocked");
    if (!owner->feedback_tick)
        owner->feedback_tick = gtk_widget_add_tick_callback(owner->button, feedback_frame, owner, NULL);
}

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

/* The stash name carries the original workspace ID, never a window sequence.
 * Cube's face map translates that ID to the same 1–4 shown by the main pills. */
static long minimized_workspace(GtkWidget *button) {
    if (!gtk_style_context_has_class(gtk_widget_get_style_context(button), "special")) return 0;
    GtkWidget *label = find_widget(button, "workspace-label", TRUE);
    if (!GTK_IS_LABEL(label)) return 0;
    const char *prefix = "xetal-minimized-ws-", *text = gtk_label_get_text(GTK_LABEL(label));
    if (!g_str_has_prefix(text, prefix)) return 0;
    char *end = NULL;long number = strtol(text + strlen(prefix), &end, 10);
    if (end == text + strlen(prefix)) return 0;
    while (g_ascii_isspace(*end)) ++end;
    return !*end && number && number >= G_MININT && number <= G_MAXINT ? number : 0;
}

/* Keep the original workspace identity so occupied workspaces and personal
 * shortcuts survive the rename. Only its presentation changes to Stash. */
static gboolean stash_workspace(GtkWidget *button) {
    if (!gtk_style_context_has_class(gtk_widget_get_style_context(button), "special")) return FALSE;
    GtkWidget *label = find_widget(button, "workspace-label", TRUE);
    if (!GTK_IS_LABEL(label)) return FALSE;
    char *name = g_strdup(gtk_label_get_text(GTK_LABEL(label))); g_strstrip(name);
    gboolean stash = !g_strcmp0(name, "magic") || !g_strcmp0(name, "Stash");
    g_free(name); return stash;
}

static const char *stash_help =
    "<b>Stash</b> is a hidden workspace. Your windows keep running.\n"
    "<b>Win + Shift + S:</b> Stash the focused window (hover to focus).\n"
    "<b>Win + S:</b> Show or hide Stash.\n"
    "<b>Win + Shift + number:</b> Move the window back to that workspace.";

static char *display_label(const Decoration *d) {
    if (d->stash) return g_strdup("Stash ");
    if (d->minimized) return g_strdup_printf("M%ld ", d->face ? (long)d->face : d->number);
    if (d->face) return g_strdup_printf("%d ", d->face);
    return d->number < 0 ? g_strdup(d->original_label) : g_strdup_printf("%ld ",d->number);
}

static void label_changed(GObject *label, GParamSpec *property, gpointer data) {
    Decoration *d = data;
    if (!d->face && !d->minimized && !d->stash) return;
    /* Waybar rewrites this label during workspace and window updates. Correct
     * it in the same GTK notification, before layout/paint, not on our timer. */
    char *text = display_label(d);
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
    d->original_tooltip = gtk_widget_get_tooltip_markup(button);
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
    if (cube != owner->cube) update_add_button(owner, cube);
    for (GSList *it = owner->decorations, *next; it; it = next) {
        next = it->next;
        Decoration *d = it->data;
        if (!d->button) { owner->decorations = g_slist_delete_link(owner->decorations, it); g_free(d->original_label); g_free(d->original_tooltip); g_free(d); }
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
        long minimized = minimized_workspace(button);
        gboolean stash = stash_workspace(button);
        if (!d && (number || minimized || stash)) {
            d = decorate(owner, button);
            if (d && minimized) { d->minimized = TRUE; d->number = minimized; }
            if (d) d->stash = stash;
        }
        /* Named workspaces have no numbered layout override. Publish readiness
         * separately so the indicator can distinguish them from initial setup. */
        g_object_set_data(G_OBJECT(button), "xetal-workspace-layout-ready", GINT_TO_POINTER(!number || d != NULL));
        if (!d) continue;
        if (!d->number) d->number = number;
        number = d->number;
        int face = GPOINTER_TO_INT(g_hash_table_lookup(faces, GSIZE_TO_POINTER(number)));
        d->face = cube ? face : 0;
        /* The displayed Cube face can differ from Hyprland's persistent ID.
         * Context menus must save the actual workspace, never the active one. */
        g_object_set_data(G_OBJECT(button), "xetal-workspace-id", d->minimized || number < 1 ? NULL : GINT_TO_POINTER(number));
        g_object_set_data(G_OBJECT(button), "xetal-workspace-display", d->stash ? NULL : GINT_TO_POINTER(d->face ? d->face : number));
        gtk_widget_set_visible(button, d->stash || d->minimized || !cube || face > 0);
        GtkWidget *label = find_widget(button, "workspace-label", TRUE);
        watch_label(d, GTK_IS_LABEL(label) ? label : NULL);
        if (GTK_IS_LABEL(label)) {
            char *text = display_label(d);
            if (g_strcmp0(text, gtk_label_get_text(GTK_LABEL(label)))) gtk_label_set_text(GTK_LABEL(label), text);
            g_free(text);
        }
        gboolean removable = !d->minimized && !cube && number > 0 && count > 1 && gtk_style_context_has_class(gtk_widget_get_style_context(button), "empty");
        gtk_widget_set_margin_end(d->content, d->margin + (removable ? 16 : 0));
        gtk_widget_set_visible(d->close, removable);
        if (d->stash) {
            char *tip = gtk_widget_get_tooltip_markup(button);
            if (g_strcmp0(tip, stash_help)) gtk_widget_set_tooltip_markup(button, stash_help);
            g_free(tip);
        }
        if (d->minimized) {
            char *tip = g_strdup_printf("Minimized from workspace %ld · Click an app icon to restore", d->face ? (long)d->face : number);
            gtk_widget_set_tooltip_text(button, tip);g_free(tip);
        }
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
    atk_object_set_name(gtk_widget_get_accessible(button), "New workspace");
    gtk_widget_set_margin_start(button, 3);
    gtk_widget_set_margin_end(button, 3);
    /* Widget-local feedback survives theme changes without editing shared CSS. */
    GtkCssProvider *feedback = gtk_css_provider_new();
    gtk_css_provider_load_from_data(feedback,
        "#new-workspace.cube-unavailable {opacity:0.65;}"
        "#new-workspace.cube-unavailable:hover {opacity:1;}"
        "#new-workspace.cube-blocked {background-image:none; background-color:#b42338;"
        " color:#ffffff; border-color:#ff6b78; box-shadow:inset 0 0 0 1px #ff6b78;"
        " opacity:1; transition:none;}" , -1, NULL);
    gtk_style_context_add_provider(gtk_widget_get_style_context(button), GTK_STYLE_PROVIDER(feedback),
                                   GTK_STYLE_PROVIDER_PRIORITY_APPLICATION + 1);
    g_object_unref(feedback);
    update_add_button(owner, cube_faces(NULL, NULL));
    gtk_container_add(info->get_root_widget(info->obj), button);
    g_signal_connect(button, "clicked", G_CALLBACK(clicked), owner);
    gtk_widget_show_all(button);
    owner->timer = g_timeout_add(200, refresh, owner);
    return owner;
}
void wbcffi_deinit(void *instance) {
    Workspaces *owner = instance;
    if (owner->timer) g_source_remove(owner->timer);
    stop_feedback(owner);
    for (GSList *it = owner->decorations; it; it = it->next) {
        Decoration *d = it->data;
        watch_label(d, NULL);
        if (d->button) {
            GtkWidget *label = find_widget(d->button, "workspace-label", TRUE);
            if (GTK_IS_LABEL(label) && (d->number || d->stash)) {
                char *text = d->stash || d->minimized || d->number < 0 ? g_strdup(d->original_label) : g_strdup_printf("%ld ", d->number);
                gtk_label_set_text(GTK_LABEL(label), text); g_free(text);
            }
            if (d->stash) gtk_widget_set_tooltip_markup(d->button, d->original_tooltip);
            g_signal_handler_disconnect(d->button, d->destroy_handler);
            g_object_set_data(G_OBJECT(d->button), "xetal-workspace-decoration", NULL);
            g_object_set_data(G_OBJECT(d->button), "xetal-workspace-id", NULL);
            g_object_set_data(G_OBJECT(d->button), "xetal-workspace-display", NULL);
            g_object_set_data(G_OBJECT(d->button), "xetal-workspace-layout-ready", NULL);
            gtk_widget_set_margin_end(d->content, d->margin);
            g_object_ref(d->content);
            gtk_container_remove(GTK_CONTAINER(d->overlay), d->content);
            gtk_container_remove(GTK_CONTAINER(d->button), d->overlay);
            gtk_container_add(GTK_CONTAINER(d->button), d->content);
            g_object_unref(d->content);
        }
        g_free(d->original_label); g_free(d->original_tooltip); g_free(d);
    }
    g_slist_free(owner->decorations);
    gtk_widget_destroy(owner->button);
    g_free(owner);
}
void wbcffi_update(void *instance) {}
void wbcffi_refresh(void *instance, int signal) {}
