/* Real GTK state, file notifications, monitor separation and vector bounds. */
#include <gtk/gtk.h>
#include <glib/gstdio.h>
static const char *fixture_home;
static const char *test_home(void) { return fixture_home; }
#define g_get_home_dir test_home
#include "mode.c"
#undef g_get_home_dir

static GtkContainer *get_root(wbcffi_module *module) { return GTK_CONTAINER(module); }
static void pump(void) {
    gint64 deadline = g_get_monotonic_time() + 350000;
    do { while (g_main_context_iteration(NULL, FALSE)) {} g_usleep(1000); }
    while (g_get_monotonic_time() < deadline);
}
typedef struct { GtkWidget *window, *host, *box, *first, *second; Mode *mode; } Bar;
static GtkWidget *workspace(GtkWidget *box, int id, int face) {
    GtkWidget *button = gtk_button_new_with_label("Face");
    g_object_set_data(G_OBJECT(button), "xetal-workspace-id", GINT_TO_POINTER(id));
    g_object_set_data(G_OBJECT(button), "xetal-workspace-display", GINT_TO_POINTER(face));
    g_object_set_data(G_OBJECT(button), "xetal-workspace-layout-ready", GINT_TO_POINTER(1));
    gtk_style_context_add_class(gtk_widget_get_style_context(button), "hosting-monitor");
    gtk_container_add(GTK_CONTAINER(box), button); return button;
}
static Mode *start(Bar *bar) {
    wbcffi_init_info info = {.obj = (wbcffi_module *)bar->host, .get_root_widget = get_root};
    return wbcffi_init(&info, NULL, 0);
}
static Bar bar_new(int id, int face) {
    Bar bar = {0};
    bar.window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_container_add(GTK_CONTAINER(bar.window), row);
    bar.box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0); gtk_widget_set_name(bar.box, "workspaces");
    gtk_container_add(GTK_CONTAINER(row), bar.box);
    bar.first = workspace(bar.box, id, face); bar.second = workspace(bar.box, 99, 4);
    gtk_style_context_add_class(gtk_widget_get_style_context(bar.first), "visible");
    bar.host = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0); gtk_container_add(GTK_CONTAINER(row), bar.host);
    bar.mode = start(&bar); gtk_widget_show_all(bar.window); return bar;
}
static void expect(Bar *bar, int layout, const char *text) {
    g_assert_true(bar->mode->known); g_assert_cmpint(bar->mode->layout, ==, layout);
    char *tip = gtk_widget_get_tooltip_text(bar->mode->root);
    g_assert_nonnull(strstr(tip, text)); g_free(tip);
}
static void icons(Mode *mode) {
    int bounds[3][4];
    int width = gtk_widget_get_allocated_width(mode->drawing), height = gtk_widget_get_allocated_height(mode->drawing);
    for (int i = 0; i < 3; ++i) {
        mode->layout = i;
        cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
        cairo_t *cr = cairo_create(surface); draw(mode->drawing, cr, mode); cairo_destroy(cr); cairo_surface_flush(surface);
        unsigned char *pixels = cairo_image_surface_get_data(surface);
        int stride = cairo_image_surface_get_stride(surface), *b = bounds[i];
        b[0] = width; b[1] = height; b[2] = b[3] = -1;
        for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
            if (!(((guint32 *)(pixels + y * stride))[x] >> 24)) continue;
            b[0] = MIN(b[0], x); b[1] = MIN(b[1], y); b[2] = MAX(b[2], x); b[3] = MAX(b[3], y);
        }
        g_assert_cmpint(b[2] - b[0] + 1, ==, 18); g_assert_cmpint(b[3] - b[1] + 1, ==, 18);
        for (int j = 0; j < 4; ++j) g_assert_cmpint(b[j], ==, bounds[0][j]);
        char *path = g_strdup_printf("%s/mode-%d.png", fixture_home, i);
        cairo_surface_write_to_png(surface, path); g_free(path); cairo_surface_destroy(surface);
    }
}
int main(int argc, char **argv) {
    gtk_init(&argc, &argv); g_assert_cmpint(argc, ==, 2); fixture_home = argv[1];
    char *directory = g_build_filename(fixture_home, ".config/hypr/workspaces", NULL);
    g_mkdir_with_parents(directory, 0700);
    char *path = g_build_filename(directory, "rules.json", NULL);
    Bar a = bar_new(203, 2), b = bar_new(204, 3); pump();
    expect(&a, 0, "Workspace 2 · Individual"); expect(&b, 0, "Workspace 3 · Individual");
    int width = gtk_widget_get_allocated_width(a.mode->root);
    g_assert_true(g_file_set_contents(path, "{\"version\":1,\"workspaces\":{\"203\":{\"layout\":\"floating\",\"controls\":\"individual\"},\"204\":{\"layout\":\"tile\",\"controls\":\"off\"}}}", -1, NULL));
    pump(); expect(&a, 2, "Force floating"); expect(&b, 1, "Force tiling");
    g_assert_cmpint(gtk_widget_get_allocated_width(a.mode->root), ==, width);
    icons(a.mode);
    gtk_style_context_remove_class(gtk_widget_get_style_context(a.first), "visible");
    gtk_style_context_add_class(gtk_widget_get_style_context(a.second), "visible");
    pump(); expect(&a, 0, "Workspace 4 · Individual"); expect(&b, 1, "Force tiling");
    /* Hiding workspace buttons through Options must not disable the reader. */
    gtk_widget_hide(b.box); pump(); expect(&b, 1, "Force tiling");
    g_file_set_contents(path, "broken", -1, NULL); pump(); g_assert_false(b.mode->known);
    g_unlink(path); pump(); expect(&b, 0, "Individual");
    /* Queued file notifications and timers must not outlive module reload. */
    wbcffi_deinit(a.mode); a.mode = start(&a); pump(); expect(&a, 0, "Individual");
    wbcffi_deinit(a.mode); wbcffi_deinit(b.mode); pump();
    gtk_widget_destroy(a.window); gtk_widget_destroy(b.window);
    g_free(path); g_free(directory);
    g_print("PASS: per-display policies, Cube IDs, mode/workspace changes, atomic file updates/deletion, hidden workspace controls, module reload and equal icon bounds.\n");
    return 0;
}
