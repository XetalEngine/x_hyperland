/* The same Places source as Qt, with a native GTK sidebar and async device setup. */
#pragma once
#include <json-glib/json-glib.h>

typedef struct {
    GtkWidget *tree;
    GtkFileChooser *chooser;
    GSubprocess *listing, *opening;
    gchar *previous;
    guint timer;
    gboolean alive;
} Places;

enum { PLACE_NAME, PLACE_ICON, PLACE_DATA, PLACE_ENABLED, PLACE_TIP, PLACE_COLUMNS };
static const gchar *place_string(JsonObject *object, const gchar *key) {
    return json_object_has_member(object, key) ? json_object_get_string_member(object, key) : "";
}
static gchar *places_helper(void) {
    gchar *directory = g_path_get_dirname(g_getenv("XETAL_THEME_CONFIG"));
    gchar *path = g_build_filename(directory, "places.py", NULL); g_free(directory); return path;
}
static void places_load(Places *p);
static void places_free(Places *p) {
    g_clear_object(&p->listing); g_clear_object(&p->opening); g_free(p->previous); g_free(p);
}
static void places_destroy(GtkWidget *widget, Places *p) {
    (void)widget; p->alive = FALSE;
    if (p->timer) { g_source_remove(p->timer); p->timer = 0; }
    if (p->listing) g_subprocess_force_exit(p->listing);
    if (p->opening) g_subprocess_force_exit(p->opening);
}
static void places_done(GObject *source, GAsyncResult *result, gpointer data) {
    GtkWidget *tree = data; Places *p = g_object_get_data(G_OBJECT(tree), "xetal-places");
    gboolean opening = p->opening == G_SUBPROCESS(source);
    gchar *output = NULL, *errors = NULL; GError *error = NULL;
    gboolean success = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, &output, &errors, &error);
    if (opening) g_clear_object(&p->opening); else g_clear_object(&p->listing);
    if (!p->alive) goto finish;
    if (opening) gtk_widget_set_sensitive(tree, TRUE);
    JsonParser *parser = json_parser_new();
    if (!success || !output || !json_parser_load_from_data(parser, output, -1, NULL)) {
        g_object_unref(parser); goto finish;
    }
    JsonNode *root = json_parser_get_root(parser);
    if (opening && JSON_NODE_HOLDS_OBJECT(root)) {
        JsonObject *object = json_node_get_object(root);
        const gchar *message = place_string(object, "error");
        const gchar *dolphin = place_string(object, "dolphin");
        const gchar *url = place_string(object, "url");
        if (*message) {
            GtkWidget *dialog = gtk_message_dialog_new(GTK_WINDOW(gtk_widget_get_toplevel(tree)),
                GTK_DIALOG_DESTROY_WITH_PARENT, GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "%s", message);
            g_signal_connect_swapped(dialog, "response", G_CALLBACK(gtk_widget_destroy), dialog); gtk_widget_show(dialog);
        } else if (*dolphin) {
            gchar *helper = places_helper(), *directory = g_path_get_dirname(helper);
            gchar *script = g_build_filename(directory, "..", "scripts", "dolphin.sh", NULL);
            GSubprocess *process = g_subprocess_new(G_SUBPROCESS_FLAGS_NONE, NULL, script, dolphin, NULL);
            g_clear_object(&process); g_free(helper); g_free(directory); g_free(script);
        } else if (*url) gtk_file_chooser_set_current_folder_uri(p->chooser, url);
        places_load(p);
    } else if (!opening && JSON_NODE_HOLDS_ARRAY(root) && g_strcmp0(output, p->previous)) {
        g_free(p->previous); p->previous = g_strdup(output);
        GtkListStore *store = gtk_list_store_new(PLACE_COLUMNS, G_TYPE_STRING, G_TYPE_STRING, G_TYPE_STRING, G_TYPE_BOOLEAN, G_TYPE_STRING);
        JsonArray *array = json_node_get_array(root);
        GPtrArray *groups = g_ptr_array_new_with_free_func(g_free);
        for (guint i = 0; i < json_array_get_length(array); ++i) {
            JsonObject *object = json_array_get_object_element(array, i);
            const gchar *group = place_string(object, "group"); gboolean seen = FALSE;
            for (guint j = 0; j < groups->len; ++j) if (!g_strcmp0(group, groups->pdata[j])) seen = TRUE;
            if (!seen) g_ptr_array_add(groups, g_strdup(group));
        }
        for (guint j = 0; j < groups->len; ++j) {
            const gchar *group = groups->pdata[j]; GtkTreeIter iter;
            gtk_list_store_append(store, &iter);
            gtk_list_store_set(store, &iter, PLACE_NAME, group, PLACE_ENABLED, FALSE, -1);
            for (guint i = 0; i < json_array_get_length(array); ++i) {
                JsonObject *object = json_array_get_object_element(array, i);
                if (g_strcmp0(group, place_string(object, "group"))) continue;
                gchar *entry = json_to_string(json_array_get_element(array, i), FALSE);
                const gchar *url = place_string(object, "url");
                gtk_list_store_append(store, &iter);
                gtk_list_store_set(store, &iter, PLACE_NAME, place_string(object, "name"), PLACE_ICON, place_string(object, "icon"),
                    PLACE_DATA, entry, PLACE_ENABLED, TRUE, PLACE_TIP, *url ? url : place_string(object, "device"), -1);
                g_free(entry);
            }
        }
        gtk_tree_view_set_model(GTK_TREE_VIEW(tree), GTK_TREE_MODEL(store)); g_object_unref(store); g_ptr_array_unref(groups);
    }
    g_object_unref(parser);
finish:
    g_clear_error(&error); g_free(output); g_free(errors); g_object_unref(tree);
}
static void places_load(Places *p) {
    if (!p->alive || p->listing || !gtk_widget_get_mapped(p->tree)) return;
    gchar *helper = places_helper();
    p->listing = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_PIPE, NULL, "python3", helper, NULL);
    g_free(helper);
    if (p->listing) g_subprocess_communicate_utf8_async(p->listing, NULL, NULL, places_done, g_object_ref(p->tree));
}
static gboolean places_tick(gpointer data) { places_load(data); return G_SOURCE_CONTINUE; }
static void places_activated(GtkTreeView *tree, GtkTreePath *path, GtkTreeViewColumn *column, Places *p) {
    (void)column; if (p->opening || !p->alive) return;
    GtkTreeModel *model = gtk_tree_view_get_model(tree); GtkTreeIter iter;
    if (!model || !gtk_tree_model_get_iter(model, &iter, path)) return;
    gchar *entry = NULL; gtk_tree_model_get(model, &iter, PLACE_DATA, &entry, -1);
    if (!entry) return;
    JsonParser *parser = json_parser_new();
    if (json_parser_load_from_data(parser, entry, -1, NULL)) {
        JsonObject *object = json_node_get_object(json_parser_get_root(parser));
        const gchar *url = place_string(object, "url"), *device = place_string(object, "device");
        if (g_str_has_prefix(url, "file:")) gtk_file_chooser_set_current_folder_uri(p->chooser, url);
        else {
            gchar *helper = places_helper();
            p->opening = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_PIPE, NULL,
                "python3", helper, *device ? "--device" : "--open", *device ? device : url, NULL);
            g_free(helper);
            if (p->opening) {
                gtk_widget_set_sensitive(p->tree, FALSE);
                g_subprocess_communicate_utf8_async(p->opening, NULL, NULL, places_done, g_object_ref(p->tree));
            }
        }
    }
    g_object_unref(parser); g_free(entry);
}
static gboolean places_clicked(GtkWidget *tree, GdkEventButton *event, Places *p) {
    GtkTreePath *path = NULL;
    if (event->button == 1 && gtk_tree_view_get_path_at_pos(GTK_TREE_VIEW(tree), event->x, event->y, &path, NULL, NULL, NULL)) {
        places_activated(GTK_TREE_VIEW(tree), path, NULL, p); gtk_tree_path_free(path);
    }
    return FALSE;
}
static GtkWidget *places_find(GtkWidget *widget) {
    if (GTK_IS_PLACES_SIDEBAR(widget)) return widget;
    if (!GTK_IS_CONTAINER(widget)) return NULL;
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget)); GtkWidget *found = NULL;
    for (GList *item = children; item && !found; item = item->next) found = places_find(item->data);
    g_list_free(children); return found;
}
static void places_mapped(GtkWidget *tree, Places *p) { (void)tree; places_load(p); }
static void places_attach(GtkWidget *widget) {
    if (g_object_get_data(G_OBJECT(widget), "xetal-file-places")) return;
    GtkWidget *old = places_find(widget);
    if (!old || g_object_get_data(G_OBJECT(old), "xetal-places-replaced")) return;
    GtkWidget *parent = gtk_widget_get_parent(old);
    if (GTK_IS_PANED(parent)) {
        gboolean first = gtk_paned_get_child1(GTK_PANED(parent)) == old;
        g_object_ref(old); gtk_container_remove(GTK_CONTAINER(parent), old);
        GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
        if (first) gtk_paned_pack1(GTK_PANED(parent), box, FALSE, FALSE);
        else gtk_paned_pack2(GTK_PANED(parent), box, FALSE, FALSE);
        gtk_box_pack_start(GTK_BOX(box), old, FALSE, TRUE, 0); g_object_unref(old);
        gtk_widget_show(box); parent = box;
    }
    if (!GTK_IS_BOX(parent)) return;
    g_object_set_data(G_OBJECT(old), "xetal-places-replaced", GINT_TO_POINTER(1));
    g_object_set_data(G_OBJECT(widget), "xetal-file-places", GINT_TO_POINTER(1));
    gtk_widget_set_no_show_all(old, TRUE); gtk_widget_hide(old);
    Places *p = g_new0(Places, 1); p->alive = TRUE; p->chooser = GTK_FILE_CHOOSER(widget);
    p->tree = gtk_tree_view_new(); gtk_widget_set_name(p->tree, "xetalPlacesSidebar");
    g_object_set_data_full(G_OBJECT(p->tree), "xetal-places", p, (GDestroyNotify)places_free);
    gtk_tree_view_set_headers_visible(GTK_TREE_VIEW(p->tree), FALSE);
    gtk_tree_view_set_tooltip_column(GTK_TREE_VIEW(p->tree), PLACE_TIP);
    GtkTreeViewColumn *column = gtk_tree_view_column_new();
    GtkCellRenderer *icon = gtk_cell_renderer_pixbuf_new(), *text = gtk_cell_renderer_text_new();
    g_object_set(icon, "stock-size", GTK_ICON_SIZE_LARGE_TOOLBAR, "xpad", 8, NULL);
    g_object_set(text, "ypad", 7, "ellipsize", PANGO_ELLIPSIZE_END, NULL);
    gtk_tree_view_column_pack_start(column, icon, FALSE); gtk_tree_view_column_add_attribute(column, icon, "icon-name", PLACE_ICON);
    gtk_tree_view_column_pack_start(column, text, TRUE); gtk_tree_view_column_add_attribute(column, text, "text", PLACE_NAME);
    gtk_tree_view_column_add_attribute(column, text, "sensitive", PLACE_ENABLED);
    gtk_tree_view_append_column(GTK_TREE_VIEW(p->tree), column);
    GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL); gtk_widget_set_size_request(scroll, 230, -1);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_container_add(GTK_CONTAINER(scroll), p->tree); gtk_box_pack_start(GTK_BOX(parent), scroll, FALSE, TRUE, 0);
    gtk_box_reorder_child(GTK_BOX(parent), scroll, 0);
    g_signal_connect(p->tree, "destroy", G_CALLBACK(places_destroy), p);
    g_signal_connect(p->tree, "map", G_CALLBACK(places_mapped), p);
    g_signal_connect(p->tree, "row-activated", G_CALLBACK(places_activated), p);
    g_signal_connect(p->tree, "button-release-event", G_CALLBACK(places_clicked), p);
    p->timer = g_timeout_add_seconds(4, places_tick, p);
    gtk_widget_show_all(scroll);
}
