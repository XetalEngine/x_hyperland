/* Real GTK module lifecycle tests; --state-only requires no display server. */
#include "options.c"
#include <sys/stat.h>

static char *directory, *state;

static void change(const char *id, gboolean show, gboolean reset_all) {
    Change c = {.path = state, .id = (char *)id, .show = show, .reset = reset_all};
    GError *error = NULL;
    g_assert_true(write_change(&c, &error)); g_assert_no_error(error);
}

static void state_tests(void) {
    GError *error = NULL; gboolean bottom;
    GHashTable *hidden = read_options(state, &bottom, &error);
    g_assert_no_error(error); g_assert_cmpuint(g_hash_table_size(hidden), ==, 0); g_hash_table_unref(hidden);
    change("cpu", FALSE, FALSE); change("custom/wifi", FALSE, FALSE);
    change("future/module", FALSE, FALSE); change("cpu", TRUE, FALSE);
    hidden = read_options(state, &bottom, &error); g_assert_no_error(error);
    g_assert_false(g_hash_table_contains(hidden, "cpu"));
    g_assert_true(g_hash_table_contains(hidden, "custom/wifi"));
    g_assert_true(g_hash_table_contains(hidden, "future/module")); g_hash_table_unref(hidden);
    g_assert_false(bottom);
    Change edge = {.path = state, .edge = "bottom"};
    g_assert_true(write_change(&edge, &error)); g_assert_no_error(error);
    change("memory", FALSE, FALSE);
    hidden = read_options(state, &bottom, &error);
    g_assert_true(bottom); g_assert_true(g_hash_table_contains(hidden, "future/module"));
    g_assert_true(g_hash_table_contains(hidden, "memory")); g_hash_table_unref(hidden);
    change(NULL, TRUE, TRUE);
    hidden = read_options(state, &bottom, &error);
    g_assert_true(bottom); g_assert_cmpuint(g_hash_table_size(hidden), ==, 0); g_hash_table_unref(hidden);
    edge.edge = "top"; g_assert_true(write_change(&edge, &error));
    hidden = read_options(state, &bottom, &error); g_assert_false(bottom); g_hash_table_unref(hidden);
    struct stat st; g_assert_cmpint(g_stat(state, &st), ==, 0); g_assert_cmpint(st.st_mode & 0777, ==, 0600);

    char *lock_path = g_strconcat(state, ".lock", NULL);
    int lock = g_open(lock_path, O_RDWR, 0600); g_assert_cmpint(lock, >=, 0);
    g_assert_cmpint(flock(lock, LOCK_EX | LOCK_NB), ==, 0);
    Change c = {.path = state, .id = "memory", .show = FALSE};
    g_assert_false(write_change(&c, &error)); g_assert_error(error, G_IO_ERROR, G_IO_ERROR_BUSY);
    g_clear_error(&error); close(lock); g_free(lock_path);

    const char *invalid[] = {"{", "[]", "{\"version\":2,\"hidden\":[]}", "{\"version\":1,\"hidden\":[],\"position\":\"left\"}",
        "{\"version\":1,\"hidden\":[false]}", "{\"version\":1,\"hidden\":[\"\"]}"};
    for (guint i = 0; i < G_N_ELEMENTS(invalid); i++) {
        g_assert_true(g_file_set_contents(state, invalid[i], -1, NULL));
        g_assert_false(write_change(&c, &error)); g_assert_error(error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);
        g_clear_error(&error);
        char *contents = NULL; g_file_get_contents(state, &contents, NULL, NULL);
        g_assert_cmpstr(contents, ==, invalid[i]); g_free(contents);
    }
    change(NULL, TRUE, TRUE);
    hidden = read_options(state, &bottom, &error); g_assert_no_error(error);
    g_assert_cmpuint(g_hash_table_size(hidden), ==, 0); g_hash_table_unref(hidden);
    g_print("PASS: saved choices merge, unknown items survive, private atomic file, lock conflict, invalid-file protection and reset.\n");
    char *workspace_path = g_build_filename(directory, "workspaces.json", NULL);
    WorkspaceModes modes;
    g_assert_true(workspace_modes(workspace_path, 203, &modes));
    g_assert_cmpint(modes.layout, ==, 0); g_assert_cmpint(modes.controls, ==, 0);
    g_file_set_contents(workspace_path, "{\"version\":1,\"workspaces\":{\"203\":{\"layout\":\"tile\",\"controls\":\"off\"}}}", -1, NULL);
    g_assert_true(workspace_modes(workspace_path, 203, &modes));
    g_assert_cmpint(modes.layout, ==, 1); g_assert_cmpint(modes.controls, ==, 2);
    g_assert_true(workspace_modes(workspace_path, 204, &modes));
    g_assert_cmpint(modes.layout, ==, 0); g_assert_cmpint(modes.controls, ==, 0);
    g_file_set_contents(workspace_path, "{\"version\":1,\"default_layout\":\"kde\",\"workspaces\":{\"203\":{\"layout\":\"tile\",\"controls\":\"off\"}}}", -1, NULL);
    g_assert_true(workspace_modes(workspace_path, 203, &modes));
    g_assert_cmpint(modes.layout, ==, 1); g_assert_cmpint(modes.controls, ==, 2);
    g_assert_true(workspace_modes(workspace_path, 1004, &modes));
    g_assert_cmpint(modes.layout, ==, 3); g_assert_cmpint(modes.controls, ==, 0);
    g_assert_true(workspace_modes(workspace_path, -99, &modes));
    g_assert_cmpint(modes.layout, ==, 0);
    g_file_set_contents(workspace_path, "{\"version\":1,\"default_layout\":true,\"workspaces\":{}}", -1, NULL);
    g_assert_false(workspace_modes(workspace_path, 1004, &modes));
    g_file_set_contents(workspace_path, "{\"version\":1,\"workspaces\":{\"203\":{\"layout\":\"invalid\",\"controls\":\"on\"}}}", -1, NULL);
    g_assert_false(workspace_modes(workspace_path, 203, &modes));
    g_unlink(workspace_path); g_free(workspace_path);
    g_print("PASS: workspace menu reads the addressed workspace, defaults and invalid state.\n");
}

typedef struct { GtkWidget *window, *region, *host, *cpu, *memory, *media; Options *options; } Bar;
static GtkContainer *get_root(wbcffi_module *module) { return GTK_CONTAINER(module); }
static Options *start(Bar *bar) {
    char *quoted = g_strdup_printf("\"%s\"", state);
    wbcffi_config_entry entry = {"state_path", quoted};
    wbcffi_init_info info = {.obj = (wbcffi_module *)bar->host, .get_root_widget = get_root};
    Options *o = wbcffi_init(&info, &entry, 1); g_free(quoted);
    refresh(o); return o;
}
static Bar bar_new(void) {
    Bar bar = {0};
    bar.window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_layer_init_for_window(GTK_WINDOW(bar.window));
    gtk_layer_set_anchor(GTK_WINDOW(bar.window), GTK_LAYER_SHELL_EDGE_TOP, TRUE);
    gtk_window_set_title(GTK_WINDOW(bar.window), "Xetal bar options test");
    bar.region = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 3);
    gtk_style_context_add_class(gtk_widget_get_style_context(bar.region), "modules-right");
    gtk_container_add(GTK_CONTAINER(bar.window), bar.region);
    bar.host = gtk_event_box_new(); gtk_box_pack_start(GTK_BOX(bar.region), bar.host, FALSE, FALSE, 0);
    bar.cpu = gtk_label_new("CPU 75%"); gtk_widget_set_name(bar.cpu, "cpu");
    bar.memory = gtk_label_new("RAM 32G"); gtk_widget_set_name(bar.memory, "memory");
    bar.media = gtk_label_new("Artist / title"); gtk_widget_set_name(bar.media, "mpris");
    gtk_box_pack_start(GTK_BOX(bar.region), bar.cpu, FALSE, TRUE, 5);
    gtk_box_pack_end(GTK_BOX(bar.region), bar.memory, FALSE, FALSE, 2);
    gtk_box_pack_end(GTK_BOX(bar.region), bar.media, FALSE, TRUE, 4);
    gtk_widget_show_all(bar.region);
    bar.options = start(&bar); return bar;
}
static Slot *slot(Options *o, const char *id) {
    for (GSList *it = o->slots; it; it = it->next) {
        Slot *s = it->data; if (!strcmp(s->item->id, id)) return s;
    }
    g_assert_not_reached();
}
static void pump(guint milliseconds) {
    gint64 deadline = g_get_monotonic_time() + milliseconds * 1000;
    do { while (g_main_context_iteration(NULL, FALSE)) {} g_usleep(1000); }
    while (g_get_monotonic_time() < deadline);
}
static GtkWidget *option(GtkWidget *menu, const char *id) {
    GList *children = gtk_container_get_children(GTK_CONTAINER(menu)); GtkWidget *found = NULL;
    for (GList *it = children; it; it = it->next) {
        if (!g_strcmp0(g_object_get_data(G_OBJECT(it->data), "module-id"), id)) found = it->data;
    }
    g_list_free(children); g_assert_nonnull(found); return found;
}
static void gui_tests(void) {
    Bar a = bar_new(), b = bar_new();
    g_assert_cmpuint(g_slist_length(a.options->slots), ==, 3);
    g_assert_cmpint(position(a.region, slot(a.options, "cpu")->wrapper), ==, 1);
    g_assert_cmpint(position(a.region, slot(a.options, "memory")->wrapper), ==, 2);
    g_assert_cmpint(position(a.region, slot(a.options, "mpris")->wrapper), ==, 3);
    for (int i = 0; i < 10; i++) refresh(a.options);
    g_assert_cmpuint(g_slist_length(a.options->slots), ==, 3);
    int full_width; gtk_widget_get_preferred_width(a.region, &full_width, NULL);
    GtkWidget *menu = g_object_ref_sink(submenu(a.options));
    g_assert_false(a.options->saving);
    GList *entries = gtk_container_get_children(GTK_CONTAINER(menu));
    for (GList *it = entries; it; it = it->next) {
        if (!g_strcmp0(g_object_get_data(G_OBJECT(it->data), "bar-position"), "bottom"))
            gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(it->data), TRUE);
    }
    g_list_free(entries);
    for (int i = 0; i < 100 && a.options->saving; i++) pump(10);
    pump(350);
    g_assert_true(gtk_layer_get_anchor(GTK_WINDOW(a.window), GTK_LAYER_SHELL_EDGE_BOTTOM));
    g_assert_true(gtk_layer_get_anchor(GTK_WINDOW(b.window), GTK_LAYER_SHELL_EDGE_BOTTOM));
    g_assert_false(gtk_layer_get_anchor(GTK_WINDOW(a.window), GTK_LAYER_SHELL_EDGE_TOP));
    gtk_check_menu_item_set_active(GTK_CHECK_MENU_ITEM(option(menu, "cpu")), FALSE);
    for (int i = 0; i < 100 && a.options->saving; i++) pump(10);
    g_assert_false(a.options->saving); pump(350);
    g_assert_false(gtk_widget_get_visible(slot(a.options, "cpu")->wrapper));
    g_assert_false(gtk_widget_get_visible(slot(b.options, "cpu")->wrapper));
    g_assert_true(gtk_widget_get_visible(a.cpu));
    int hidden_width; gtk_widget_get_preferred_width(a.region, &hidden_width, NULL);
    g_assert_cmpint(hidden_width, <, full_width);
    gtk_widget_show_all(a.region);
    g_assert_false(gtk_widget_get_visible(slot(a.options, "cpu")->wrapper));

    /* The ready-only choice persists across bars without hiding other updates. */
    GtkWidget *ready = option(menu, "custom/updates#ready");
    g_assert_cmpstr(gtk_menu_item_get_label(GTK_MENU_ITEM(ready)), ==, "Hide Update Ready");
    gtk_menu_item_activate(GTK_MENU_ITEM(ready));
    for (int i = 0; i < 100 && a.options->saving; i++) pump(10);
    pump(350);
    g_assert_true(g_hash_table_contains(a.options->hidden, "custom/updates#ready"));
    g_assert_true(g_hash_table_contains(b.options->hidden, "custom/updates#ready"));
    g_assert_false(g_hash_table_contains(a.options->hidden, "custom/updates"));
    g_assert_true(g_hash_table_contains(a.options->hidden, "cpu"));
    GtkWidget *other_menu = g_object_ref_sink(submenu(b.options));
    g_assert_cmpstr(gtk_menu_item_get_label(GTK_MENU_ITEM(option(other_menu, "custom/updates#ready"))), ==, "Show Update Ready");
    g_assert_false(b.options->saving);
    gtk_widget_destroy(other_menu); g_object_unref(other_menu);
    gtk_widget_destroy(menu); g_object_unref(menu);

    /* Showing a naturally unavailable module must not create a blank placeholder. */
    gtk_widget_hide(a.media); change("mpris", FALSE, FALSE); reload_options(a.options);
    change("mpris", TRUE, FALSE); reload_options(a.options);
    g_assert_true(gtk_widget_get_visible(slot(a.options, "mpris")->wrapper));
    g_assert_false(gtk_widget_get_visible(a.media));
    for (guint i = 0; i < G_N_ELEMENTS(items); i++) change(items[i].id, FALSE, FALSE);
    reload_options(a.options);
    g_assert_nonnull(g_object_get_data(G_OBJECT(a.window), "xetal-bar-options"));
    g_assert_nonnull(a.options->gesture);
    reset(NULL, a.options);
    for (int i = 0; i < 100 && a.options->saving; i++) pump(10);
    g_assert_cmpuint(g_hash_table_size(a.options->hidden), ==, 0);
    g_assert_true(a.options->bottom);
    menu = g_object_ref_sink(submenu(a.options));
    ready = option(menu, "custom/updates#ready");
    g_assert_cmpstr(gtk_menu_item_get_label(GTK_MENU_ITEM(ready)), ==, "Hide Update Ready");
    gtk_menu_item_activate(GTK_MENU_ITEM(ready));
    for (int i = 0; i < 100 && a.options->saving; i++) pump(10);
    gtk_widget_destroy(menu); g_object_unref(menu);
    menu = g_object_ref_sink(submenu(a.options));
    ready = option(menu, "custom/updates#ready");
    g_assert_cmpstr(gtk_menu_item_get_label(GTK_MENU_ITEM(ready)), ==, "Show Update Ready");
    gtk_menu_item_activate(GTK_MENU_ITEM(ready));
    for (int i = 0; i < 100 && a.options->saving; i++) pump(10);
    g_assert_false(g_hash_table_contains(a.options->hidden, "custom/updates#ready"));
    gtk_widget_destroy(menu); g_object_unref(menu);
    menu = g_object_ref_sink(submenu(a.options));
    g_assert_cmpstr(gtk_menu_item_get_label(GTK_MENU_ITEM(option(menu, "custom/updates#ready"))), ==, "Hide Update Ready");
    gtk_widget_destroy(menu); g_object_unref(menu);

    /* An external pin menu can outlive the module. Reload restores original packing. */
    menu = g_object_ref_sink(gtk_menu_new());
    xetal_append_bar_options(menu, a.host, FALSE);
    wbcffi_deinit(a.options);
    g_assert_true(gtk_widget_get_parent(a.cpu) == a.region);
    g_assert_true(gtk_widget_get_parent(a.memory) == a.region);
    gboolean expand, fill; guint padding; GtkPackType type;
    gtk_box_query_child_packing(GTK_BOX(a.region), a.memory, &expand, &fill, &padding, &type);
    g_assert_cmpint(type, ==, GTK_PACK_END); g_assert_false(fill); g_assert_cmpuint(padding, ==, 2);
    g_assert_cmpint(position(a.region, a.cpu), ==, 1);
    g_assert_cmpint(position(a.region, a.memory), ==, 2);
    gtk_widget_destroy(menu); g_object_unref(menu);
    for (int i = 0; i < 12; i++) {
        a.options = start(&a); g_assert_cmpuint(g_slist_length(a.options->slots), ==, 3);
        wbcffi_deinit(a.options);
    }
    gtk_widget_destroy(a.window);
    /* Waybar can destroy its window before destroying the CFFI module. */
    gtk_widget_destroy(b.window); wbcffi_deinit(b.options);
    pump(250);
    g_print("PASS: GTK checkboxes, async persistence across bars, collapsed gaps, natural visibility, recovery, packing, teardown and reload.\n");
}

static void workspace_gui_tests(void) {
    Bar bar = bar_new();
    GtkWidget *first = gtk_button_new_with_label("3"), *second = gtk_button_new_with_label("4");
    g_object_set_data(G_OBJECT(first), "xetal-workspace-id", GINT_TO_POINTER(203));
    g_object_set_data(G_OBJECT(second), "xetal-workspace-id", GINT_TO_POINTER(204));
    gtk_box_pack_start(GTK_BOX(bar.region), first, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(bar.region), second, FALSE, FALSE, 0);
    gtk_widget_show_all(bar.window); pump(250);
    int x, y; gtk_widget_translate_coordinates(second, bar.window, 0, 0, &x, &y);
    g_assert_true(workspace_at(bar.window, bar.window, x+4, y+4) == second);
    gtk_widget_translate_coordinates(first, bar.window, 0, 0, &x, &y);
    g_assert_true(workspace_at(bar.window, bar.window, x+4, y+4) == first);
    GtkWidget *menu = g_object_ref_sink(workspace_choices(bar.options, 203, FALSE, 1));
    GList *entries = gtk_container_get_children(GTK_CONTAINER(menu));
    g_assert_cmpint(g_list_length(entries), ==, 4);
    GtkWidget *kde = g_list_nth_data(entries, 3);
    g_assert_cmpstr(g_object_get_data(G_OBJECT(kde), "workspace-choice"), ==, "kde");
    GtkWidget *tile = g_list_nth_data(entries, 1), *floating = g_list_nth_data(entries, 2);
    g_assert_true(gtk_check_menu_item_get_active(GTK_CHECK_MENU_ITEM(tile)));
    g_assert_false(bar.options->saving);
    g_assert_cmpint(GPOINTER_TO_INT(g_object_get_data(G_OBJECT(floating), "workspace")), ==, 203);
    g_assert_cmpstr(g_object_get_data(G_OBJECT(floating), "workspace-choice"), ==, "floating");
    g_list_free(entries); gtk_widget_destroy(menu); g_object_unref(menu);
    menu = g_object_ref_sink(workspace_choices(bar.options, 204, TRUE, 2));
    entries = gtk_container_get_children(GTK_CONTAINER(menu));
    g_assert_true(gtk_check_menu_item_get_active(GTK_CHECK_MENU_ITEM(g_list_nth_data(entries, 2))));
    g_assert_false(bar.options->saving);
    g_assert_cmpint(g_list_length(entries), ==, 5);
    GtkWidget *settings = g_list_nth_data(entries, 4);
    g_assert_cmpstr(gtk_menu_item_get_label(GTK_MENU_ITEM(settings)), ==, "Settings…");
    g_assert_cmpint(GPOINTER_TO_INT(g_object_get_data(G_OBJECT(settings), "workspace")), ==, 204);
    g_assert_true(gtk_widget_get_sensitive(settings)); // Available even with controls Off.
    g_list_free(entries); gtk_widget_destroy(menu); g_object_unref(menu);
    wbcffi_deinit(bar.options); gtk_widget_destroy(bar.window); pump(50);
    g_print("PASS: workspace hit testing retains real Cube IDs; layout/button radio groups open without writes.\n");
}

int main(int argc, char **argv) {
    gboolean state_only = argc > 1 && !strcmp(argv[1], "--state-only");
    if (!state_only) gtk_init(&argc, &argv);
    directory = g_dir_make_tmp("xetal-bar-options-test-XXXXXX", NULL); g_assert_nonnull(directory);
    state = g_build_filename(directory, "options.json", NULL);
    state_tests(); if (!state_only) { gui_tests(); workspace_gui_tests(); }
    char *lock = g_strconcat(state, ".lock", NULL); g_unlink(lock); g_free(lock);
    g_unlink(state); g_rmdir(directory); g_free(state); g_free(directory); return 0;
}
