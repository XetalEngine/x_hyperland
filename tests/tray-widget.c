/* Async GTK click routing and teardown, in the private Wayland test session. */
#include "../config/hypr/waybar/tray/activation.h"
#include <glib/gstdio.h>

static int native_clicks;
static gboolean native_press(GtkWidget *widget, GdkEventButton *event, gpointer data) {
    native_clicks++; return TRUE;
}
static void settle(void) {
    gint64 until = g_get_monotonic_time()+50000;
    while (g_get_monotonic_time()<until) {
        while (g_main_context_iteration(NULL, FALSE)) {}
        g_usleep(1000);
    }
}
static void finish(FusionTray *tray) {
    gint64 until = g_get_monotonic_time()+3000000;
    while (tray->requests && g_get_monotonic_time()<until) settle();
    g_assert_null(tray->requests);
}
int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    GError *error = NULL; char *directory = g_dir_make_tmp("fusion-tray-widget-XXXXXX", &error);
    g_assert_no_error(error);
    char *helper = g_build_filename(directory, "helper.py", NULL);
    GtkWidget *top = gtk_window_new(GTK_WINDOW_TOPLEVEL), *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    GtkWidget *item = gtk_event_box_new(); gtk_widget_set_name(box, "tray");
    gtk_container_add(GTK_CONTAINER(top), box); gtk_container_add(GTK_CONTAINER(box), item);
    gtk_container_add(GTK_CONTAINER(item), gtk_label_new("Tray fixture"));
    gtk_widget_set_tooltip_text(item, "Fixture"); gtk_widget_show_all(top); settle();
    g_signal_connect_after(item, "button-press-event", G_CALLBACK(native_press), NULL);
    FusionTray *tray = fusion_tray_new(top, helper);
    GdkEvent *event = gdk_event_new(GDK_BUTTON_PRESS);
    event->button.window = g_object_ref(gtk_widget_get_window(item)); event->button.button = 1;
    g_file_set_contents(helper, "import sys,time\nsys.stdin.read()\ntime.sleep(.05)\nsys.exit(0)\n", -1, NULL);
    g_assert_true(fusion_tray_start(tray, item, event));
    g_assert_true(fusion_tray_start(tray, item, event));
    g_assert_cmpuint(g_slist_length(tray->requests), ==, 1);
    finish(tray); g_assert_cmpint(native_clicks, ==, 0);
    for (GdkEventType type = GDK_2BUTTON_PRESS; type <= GDK_3BUTTON_PRESS; type++) {
        event->type = type; gboolean handled = FALSE;
        g_signal_emit_by_name(item, "button-press-event", event, &handled);
        g_assert_true(handled); g_assert_cmpint(native_clicks, ==, 0);
    }
    event->type = GDK_BUTTON_PRESS;
    g_file_set_contents(helper, "import sys\nsys.stdin.read()\nsys.exit(2)\n", -1, NULL);
    g_assert_true(fusion_tray_start(tray, item, event)); finish(tray);
    g_assert_cmpint(native_clicks, ==, 1);
    g_file_set_contents(helper, "import sys,time\nsys.stdin.read()\ntime.sleep(10)\n", -1, NULL);
    g_assert_true(fusion_tray_start(tray, item, event));
    FusionTrayRequest *request = tray->requests->data;
    g_source_remove(request->timeout); request->timeout = 0;
    fusion_tray_timeout(request); finish(tray); g_assert_cmpint(native_clicks, ==, 2);
    g_assert_true(fusion_tray_start(tray, item, event));
    /* Pending callbacks own one last reference; teardown cancels their action. */
    gtk_widget_destroy(top); fusion_tray_stop(tray); settle();
    g_assert_cmpint(native_clicks, ==, 2);
    gdk_event_free(event); g_unlink(helper); g_rmdir(directory); g_free(helper); g_free(directory);
    g_print("PASS: handled clicks, duplicate suppression, native fallback, timeout and teardown\n");
    return 0;
}
