/* Native GTK harness: drives the actual module inside a disposable Xvfb. */
#include "pins.c"
#include <glib-unix.h>
static GtkWidget *host;
static GtkContainer *get_root(wbcffi_module *module) { return GTK_CONTAINER(host); }
static gboolean stop(gpointer data) { gtk_main_quit(); return G_SOURCE_REMOVE; }
int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    if (argc != 2) return 2;
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "Xetal pin widget test");
    gtk_window_set_default_size(GTK_WINDOW(window), 320, 60);
    host = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_container_add(GTK_CONTAINER(window), host);
    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_data(css, "#xetal-pins .pin { min-width: 36px; padding: 4px; border: 2px solid transparent; }", -1, NULL);
    gtk_style_context_add_provider_for_screen(gdk_screen_get_default(), GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    gchar *quoted = g_strdup_printf("\"%s\"", argv[1]);
    wbcffi_config_entry entry = {"helper", quoted};
    wbcffi_init_info info = {.get_root_widget = get_root};
    Pins *instance = wbcffi_init(&info, &entry, 1);
    g_free(quoted);
    gtk_widget_show_all(window);
    g_unix_signal_add(SIGTERM, stop, NULL);
    gtk_main();
    wbcffi_deinit(instance);
    gtk_widget_destroy(window);
    g_object_unref(css);
    return 0;
}
