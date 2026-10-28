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
    GError *error = NULL;
    GHashTable *hidden = read_hidden(state, &error);
    g_assert_no_error(error); g_assert_cmpuint(g_hash_table_size(hidden), ==, 0); g_hash_table_unref(hidden);
    change("cpu", FALSE, FALSE); change("custom/wifi", FALSE, FALSE);
    change("future/module", FALSE, FALSE); change("cpu", TRUE, FALSE);
    hidden = read_hidden(state, &error); g_assert_no_error(error);
    g_assert_false(g_hash_table_contains(hidden, "cpu"));
    g_assert_true(g_hash_table_contains(hidden, "custom/wifi"));
    g_assert_true(g_hash_table_contains(hidden, "future/module")); g_hash_table_unref(hidden);
    struct stat st; g_assert_cmpint(g_stat(state, &st), ==, 0); g_assert_cmpint(st.st_mode & 0777, ==, 0600);

    char *lock_path = g_strconcat(state, ".lock", NULL);
    int lock = g_open(lock_path, O_RDWR, 0600); g_assert_cmpint(lock, >=, 0);
    g_assert_cmpint(flock(lock, LOCK_EX | LOCK_NB), ==, 0);
    Change c = {.path = state, .id = "memory", .show = FALSE};
    g_assert_false(write_change(&c, &error)); g_assert_error(error, G_IO_ERROR, G_IO_ERROR_BUSY);
    g_clear_error(&error); close(lock); g_free(lock_path);

    const char *invalid[] = {"{", "[]", "{\"version\":2,\"hidden\":[]}",
        "{\"version\":1,\"hidden\":[false]}", "{\"version\":1,\"hidden\":[\"\"]}"};
    for (guint i = 0; i < G_N_ELEMENTS(invalid); i++) {
        g_assert_true(g_file_set_contents(state, invalid[i], -1, NULL));
        g_assert_false(write_change(&c, &error)); g_assert_error(error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);
        g_clear_error(&error);
        char *contents = NULL; g_file_get_contents(state, &contents, NULL, NULL);
        g_assert_cmpstr(contents, ==, invalid[i]); g_free(contents);
    }
    change(NULL, TRUE, TRUE);
    hidden = read_hidden(state, &error); g_assert_no_error(error);
    g_assert_cmpuint(g_hash_table_size(hidden), ==, 0); g_hash_table_unref(hidden);
    g_print("PASS: saved choices merge, unknown items survive, private atomic file, lock conflict, invalid-file protection and reset.\n");
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

int main(int argc, char **argv) {
    gboolean state_only = argc > 1 && !strcmp(argv[1], "--state-only");
    if (!state_only) gtk_init(&argc, &argv);
    directory = g_dir_make_tmp("xetal-bar-options-test-XXXXXX", NULL); g_assert_nonnull(directory);
    state = g_build_filename(directory, "options.json", NULL);
    state_tests(); if (!state_only) gui_tests();
    char *lock = g_strconcat(state, ".lock", NULL); g_unlink(lock); g_free(lock);
    g_unlink(state); g_rmdir(directory); g_free(state); g_free(directory); return 0;
}
