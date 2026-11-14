/* Read the same persisted workspace policy in menus and the mode indicator. */
#pragma once
typedef struct { int layout, controls; } WorkspaceModes;
static const char *layout_keys[] = {"off", "tile", "floating", "kde"};
static const char *control_keys[] = {"individual", "on", "off"};

static int workspace_choice(JsonObject *object, const char *key, const char **choices, size_t count) {
    JsonNode *node = json_object_get_member(object, key);
    if (!node || json_node_get_value_type(node) != G_TYPE_STRING) return -1;
    for (size_t i = 0; i < count; i++) if (!strcmp(json_node_get_string(node), choices[i])) return i;
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
    if (valid && json_object_has_member(object, "default_layout")) {
        int fallback = workspace_choice(object, "default_layout", layout_keys, G_N_ELEMENTS(layout_keys));
        valid = fallback >= 0;
        if (valid && workspace > 0) modes->layout = fallback;
    }
    if (valid) {
        char key[24]; g_snprintf(key, sizeof key, "%d", workspace);
        JsonNode *entry = json_object_get_member(json_node_get_object(entries), key);
        if (entry) {
            object = JSON_NODE_HOLDS_OBJECT(entry) ? json_node_get_object(entry) : NULL;
            modes->layout = object ? workspace_choice(object, "layout", layout_keys, G_N_ELEMENTS(layout_keys)) : -1;
            modes->controls = object ? workspace_choice(object, "controls", control_keys, G_N_ELEMENTS(control_keys)) : -1;
            valid = modes->layout >= 0 && modes->controls >= 0;
        }
    }
    g_object_unref(parser); g_free(contents); return valid;
}
