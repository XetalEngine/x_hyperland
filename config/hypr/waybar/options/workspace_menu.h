/* Per-workspace menus. Only the profile controller writes preferences; it
 * validates, locks, merges and rolls back failed compositor updates. */
#pragma once
typedef struct { int layout, controls; } WorkspaceModes;
static const char *layout_keys[] = {"off", "tile", "floating"};
static const char *control_keys[] = {"individual", "on", "off"};

static int workspace_choice(JsonObject *object, const char *key, const char **choices) {
    JsonNode *node = json_object_get_member(object, key);
    if (!node || json_node_get_value_type(node) != G_TYPE_STRING) return -1;
    for (int i = 0; i < 3; i++) if (!strcmp(json_node_get_string(node), choices[i])) return i;
    return -1;
}

static gboolean workspace_modes(const char *path, int workspace, WorkspaceModes *modes) {
    *modes = (WorkspaceModes){0, 0};
    char *contents = NULL; gsize length = 0; GError *error = NULL;
    if (!g_file_get_contents(path, &contents, &length, &error)) {
        gboolean absent = g_error_matches(error, G_FILE_ERROR, G_FILE_ERROR_NOENT);
        g_clear_error(&error); return absent;
    }
    JsonParser *parser = json_parser_new();
    gboolean valid = length <= 1024 * 1024 && json_parser_load_from_data(parser, contents, length, NULL);
    JsonNode *root = valid ? json_parser_get_root(parser) : NULL;
    JsonObject *object = root && JSON_NODE_HOLDS_OBJECT(root) ? json_node_get_object(root) : NULL;
    JsonNode *version = object ? json_object_get_member(object, "version") : NULL;
    JsonNode *entries = object ? json_object_get_member(object, "workspaces") : NULL;
    valid = version && json_node_get_value_type(version) == G_TYPE_INT64 && json_node_get_int(version) == 1
        && entries && JSON_NODE_HOLDS_OBJECT(entries);
    if (valid) {
        char key[24]; g_snprintf(key, sizeof key, "%d", workspace);
        JsonNode *entry = json_object_get_member(json_node_get_object(entries), key);
        if (entry) {
            object = JSON_NODE_HOLDS_OBJECT(entry) ? json_node_get_object(entry) : NULL;
            modes->layout = object ? workspace_choice(object, "layout", layout_keys) : -1;
            modes->controls = object ? workspace_choice(object, "controls", control_keys) : -1;
            valid = modes->layout >= 0 && modes->controls >= 0;
        }
    }
    g_object_unref(parser); g_free(contents); return valid;
}

static GtkWidget *workspace_at(GtkWidget *widget, GtkWidget *top, double x, double y) {
    if (!gtk_widget_get_mapped(widget)) return NULL;
    int left, upper;
    if (g_object_get_data(G_OBJECT(widget), "xetal-workspace-id") &&
        gtk_widget_translate_coordinates(widget, top, 0, 0, &left, &upper) &&
        x >= left && x < left + gtk_widget_get_allocated_width(widget) &&
        y >= upper && y < upper + gtk_widget_get_allocated_height(widget)) return widget;
    if (!GTK_IS_CONTAINER(widget)) return NULL;
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget)); GtkWidget *found = NULL;
    for (GList *it = children; it && !found; it = it->next) found = workspace_at(it->data, top, x, y);
    g_list_free(children); return found;
}

static void workspace_failure(Options *o, const char *message) {
    if (!o->alive) return;
    GtkWidget *dialog = gtk_message_dialog_new(GTK_WINDOW(o->top), GTK_DIALOG_DESTROY_WITH_PARENT,
        GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "Could not change this workspace");
    gtk_message_dialog_format_secondary_text(GTK_MESSAGE_DIALOG(dialog), "%s", message);
    g_signal_connect_swapped(dialog, "response", G_CALLBACK(gtk_widget_destroy), dialog);
    gtk_widget_show(dialog);
}

static void workspace_saved(GObject *source, GAsyncResult *result, gpointer data) {
    Options *o = data; GError *error = NULL; char *output = NULL, *errors = NULL;
    gboolean ok = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, &output, &errors, &error);
    o->saving = FALSE;
    if (!ok || !g_subprocess_get_successful(G_SUBPROCESS(source)))
        workspace_failure(o, error ? error->message : errors && *errors ? errors : output && *output ? output : "The window behavior service did not respond.");
    g_free(output); g_free(errors); g_clear_error(&error); release(o);
}

static void workspace_toggled(GtkCheckMenuItem *item, gpointer data) {
    Options *o = data;
    if (!gtk_check_menu_item_get_active(item) || !o->alive || o->saving) return;
    int workspace = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(item), "workspace"));
    const char *option = g_object_get_data(G_OBJECT(item), "workspace-option");
    const char *choice = g_object_get_data(G_OBJECT(item), "workspace-choice");
    if (workspace < 1 || !option || !choice) return;
    char number[24]; g_snprintf(number, sizeof number, "%d", workspace);
    char *script = g_build_filename(g_get_home_dir(), ".config/hypr/workspaces/controller.py", NULL);
    GError *error = NULL;
    GSubprocess *process = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_PIPE,
        &error, "python3", script, "--workspace", number, option, choice, NULL);
    g_free(script);
    if (!process) { workspace_failure(o, error->message); g_clear_error(&error); return; }
    o->saving = TRUE;
    g_subprocess_communicate_utf8_async(process, NULL, NULL, workspace_saved, retain(o));
    g_object_unref(process);
}

static GtkWidget *workspace_choices(Options *o, int workspace, gboolean controls, int selected) {
    const char *layout_names[] = {"Off", "Force tiled", "Force floating"};
    const char *control_names[] = {"Individual", "On", "Off"};
    const char *layout_tips[] = {"Use normal launch and per-window behavior. Current windows keep their layout.",
        "Keep windows tiled together, including newly opened windows and windows moved here.",
        "Keep windows floating, including newly opened windows and windows moved here."};
    const char *control_tips[] = {"Use each app or window’s own settings.",
        "Always show controls on all windows here. Super reveals the gear; its settings apply across this workspace.",
        "Hide all artificial window controls in this workspace, even while Super is held."};
    GtkWidget *menu = gtk_menu_new(); GSList *group = NULL;
    gtk_style_context_add_class(gtk_widget_get_style_context(menu), "xetal-bar-options");
    g_object_set_data_full(G_OBJECT(menu), "owner", retain(o), release);
    for (int i = 0; i < 3; i++) {
        GtkWidget *item = gtk_radio_menu_item_new_with_label(group, controls ? control_names[i] : layout_names[i]);
        group = gtk_radio_menu_item_get_group(GTK_RADIO_MENU_ITEM(item));
        gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(item), selected == i);
        gtk_widget_set_tooltip_text(item, controls ? control_tips[i] : layout_tips[i]);
        gtk_widget_set_sensitive(item, !o->saving && selected >= 0);
        g_object_set_data(G_OBJECT(item), "workspace", GINT_TO_POINTER(workspace));
        g_object_set_data(G_OBJECT(item), "workspace-option", controls ? "--controls" : "--layout");
        g_object_set_data(G_OBJECT(item), "workspace-choice", (gpointer)(controls ? control_keys[i] : layout_keys[i]));
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
    }
    /* Connecting after initialization prevents writes merely by opening a menu. */
    for (GSList *it = group; it; it = it->next) g_signal_connect(it->data, "toggled", G_CALLBACK(workspace_toggled), o);
    return menu;
}

static void append_workspace_options(Options *o, GtkWidget *menu, GtkWidget *button) {
    int workspace = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(button), "xetal-workspace-id"));
    int display = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(button), "xetal-workspace-display"));
    if (workspace < 1) return;
    char *path = g_build_filename(g_get_home_dir(), ".config/hypr/workspaces/rules.json", NULL);
    WorkspaceModes modes; gboolean valid = workspace_modes(path, workspace, &modes); g_free(path);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
    char *title = g_strdup_printf("Workspace %d", display > 0 ? display : workspace);
    GtkWidget *heading = gtk_menu_item_new_with_label(title); g_free(title);
    gtk_widget_set_sensitive(heading, FALSE); gtk_menu_shell_append(GTK_MENU_SHELL(menu), heading);
    for (int controls = 0; controls < 2; controls++) {
        GtkWidget *item = gtk_menu_item_new_with_label(controls ? "Force modifier buttons" : "Force window layout");
        gtk_menu_item_set_submenu(GTK_MENU_ITEM(item), workspace_choices(o, workspace, controls,
            valid ? controls ? modes.controls : modes.layout : -1));
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
    }
    if (!valid) {
        GtkWidget *item = gtk_menu_item_new_with_label("Saved workspace settings could not be read");
        gtk_widget_set_sensitive(item, FALSE); gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
    }
}
