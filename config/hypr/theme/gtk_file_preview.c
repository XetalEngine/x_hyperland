/* Private GTK 3 file chooser previews. Loaded only by this Hyprland profile. */
#include <gtk/gtk.h>
#include <gio/gunixinputstream.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#define KEY "xetal-file-preview"
typedef struct {
    GtkWidget *pane, *image, *name, *message, *details, *text;
    gchar *path;
    guint timer;
    guint64 generation;
    gboolean busy, alive;
} Preview;
typedef struct {
    GWeakRef chooser;
    gchar *path, *name, *message, *details, *text;
    GdkPixbuf *image;
    guint64 generation;
} Job;

static void job_free(Job *job) {
    g_weak_ref_clear(&job->chooser); g_free(job->path); g_free(job->name);
    g_free(job->message); g_free(job->details); g_free(job->text);
    g_clear_object(&job->image); g_free(job);
}
static void preview_free(Preview *p) {
    if (p->timer) g_source_remove(p->timer);
    g_free(p->path); g_free(p);
}
static void destroyed(GtkWidget *widget, Preview *p) {
    (void)widget; p->alive = FALSE; ++p->generation;
    if (p->timer) { g_source_remove(p->timer); p->timer = 0; }
}
static void inspect(GTask *task, gpointer source, gpointer data, GCancellable *cancel) {
    (void)source; (void)cancel; Job *job = data;
    job->name = g_filename_display_basename(job->path);
    struct stat info;
    if (stat(job->path, &info)) { job->message = g_strdup("This file could not be read."); goto done; }
    GDateTime *modified = g_date_time_new_from_unix_local(info.st_mtime);
    gchar *stamp = modified ? g_date_time_format(modified, "%b %d, %Y · %H:%M") : g_strdup("Unknown");
    if (modified) g_date_time_unref(modified);
    gchar *size = g_format_size(info.st_size);
    job->details = g_strdup_printf("%s\nModified %s", S_ISDIR(info.st_mode) ? "Folder" : size, stamp);
    g_free(size); g_free(stamp);
    if (S_ISDIR(info.st_mode)) {
        GDir *dir = g_dir_open(job->path, 0, NULL);
        if (!dir) { job->message = g_strdup("This folder could not be read."); goto done; }
        GString *list = g_string_new(""); const gchar *entry = NULL; guint count = 0;
        while (count < 40 && (entry = g_dir_read_name(dir))) {
            gchar *display = g_filename_display_name(entry);
            if (count++) g_string_append_c(list, '\n');
            g_string_append(list, display); g_free(display);
        }
        job->message = g_strdup(count == 40 && g_dir_read_name(dir) ? "First 40 entries" : count ? "Folder contents" : "Empty folder");
        job->text = g_string_free(list, FALSE); g_dir_close(dir); goto done;
    }
    if (!S_ISREG(info.st_mode)) { job->message = g_strdup("No preview for this device or special file"); goto done; }
    int fd = open(job->path, O_RDONLY | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) { job->message = g_strdup("This file could not be read."); goto done; }
    if (fstat(fd, &info) || !S_ISREG(info.st_mode)) { close(fd); goto done; }
    gchar head[65537]; ssize_t length = read(fd, head, sizeof(head)-1);
    if (length < 0) { close(fd); goto done; }
    head[length] = '\0'; lseek(fd, 0, SEEK_SET);
    gchar *type = g_content_type_guess(job->path, (guchar *)head, MIN(length, 4096), NULL);
    if (g_str_has_prefix(type, "image/")) {
        if (info.st_size > 128*1024*1024) job->message = g_strdup("Image too large to preview");
        else {
            GInputStream *stream = g_unix_input_stream_new(fd, FALSE);
            GdkPixbuf *picture = gdk_pixbuf_new_from_stream_at_scale(stream, 240, 200, TRUE, NULL, NULL);
            if (picture) { job->image = gdk_pixbuf_apply_embedded_orientation(picture); g_object_unref(picture); }
            g_object_unref(stream);
        }
    } else {
        gboolean binary = !g_utf8_validate(head, length, NULL);
        for (ssize_t i = 0; i < length; ++i) if ((guchar)head[i] < 32 && head[i] != '\n' && head[i] != '\r' && head[i] != '\t') binary = TRUE;
        if (!binary) {
            job->text = g_strndup(head, length);
            job->message = g_strdup(info.st_size > length ? "First 64 KiB" : length ? "" : "Empty file");
        }
    }
    g_free(type); close(fd);
done:
    if (!job->message) job->message = g_strdup(job->image ? "" : "No preview available for this file type");
    g_task_return_boolean(task, TRUE);
}
static gboolean start(gpointer chooser);
static void completed(GObject *source, GAsyncResult *result, gpointer user) {
    (void)source; (void)user;
    Job *job = g_task_get_task_data(G_TASK(result));
    GObject *chooser = g_weak_ref_get(&job->chooser);
    if (!chooser) return;
    Preview *p = g_object_get_data(chooser, KEY);
    if (p && p->alive) {
        p->busy = FALSE;
        if (p->generation != job->generation) {
            if (!p->timer) p->timer = g_timeout_add(100, start, chooser);
        } else {
            gtk_image_set_from_pixbuf(GTK_IMAGE(p->image), job->image);
            gtk_widget_set_visible(p->image, job->image != NULL);
            gtk_label_set_text(GTK_LABEL(p->name), job->name ? job->name : "");
            gtk_label_set_text(GTK_LABEL(p->message), job->message);
            gtk_label_set_text(GTK_LABEL(p->details), job->details ? job->details : "");
            gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(p->text)), job->text ? job->text : "", -1);
            gtk_widget_set_visible(gtk_widget_get_parent(p->text), job->text && *job->text);
        }
    }
    g_object_unref(chooser);
}
static gboolean start(gpointer chooser) {
    Preview *p = g_object_get_data(chooser, KEY); p->timer = 0;
    if (!p->alive || p->busy || !p->path || !*p->path) return G_SOURCE_REMOVE;
    p->busy = TRUE; Job *job = g_new0(Job, 1);
    g_weak_ref_init(&job->chooser, chooser); job->path = g_strdup(p->path); job->generation = p->generation;
    GTask *task = g_task_new(NULL, NULL, completed, NULL);
    g_task_set_task_data(task, job, (GDestroyNotify)job_free);
    g_task_run_in_thread(task, inspect); g_object_unref(task); return G_SOURCE_REMOVE;
}
static void selected(GtkFileChooser *chooser, gpointer unused) {
    (void)unused; Preview *p = g_object_get_data(G_OBJECT(chooser), KEY);
    if (!p || !p->alive) return;
    ++p->generation; g_free(p->path); p->path = gtk_file_chooser_get_preview_filename(chooser);
    gtk_image_clear(GTK_IMAGE(p->image)); gtk_widget_hide(p->image);
    gtk_widget_hide(gtk_widget_get_parent(p->text));
    gtk_label_set_text(GTK_LABEL(p->name), ""); gtk_label_set_text(GTK_LABEL(p->details), "");
    gtk_label_set_text(GTK_LABEL(p->message), p->path ? "Loading preview…" : "Select a file or folder");
    gtk_file_chooser_set_preview_widget_active(chooser, TRUE);
    if (p->timer) g_source_remove(p->timer);
    p->timer = g_timeout_add(100, start, chooser);
}
static GtkWidget *label(GtkWidget *box, const gchar *text) {
    GtkWidget *widget = gtk_label_new(text); gtk_label_set_line_wrap(GTK_LABEL(widget), TRUE);
    gtk_label_set_max_width_chars(GTK_LABEL(widget), 34); gtk_label_set_xalign(GTK_LABEL(widget), 0);
    gtk_box_pack_start(GTK_BOX(box), widget, FALSE, FALSE, 0); return widget;
}
static gboolean mapped(GSignalInvocationHint *hint, guint n, const GValue *values, gpointer user) {
    (void)hint; (void)n; (void)user; GtkWidget *widget = g_value_get_object(values);
    if (!GTK_IS_FILE_CHOOSER(widget) || g_object_get_data(G_OBJECT(widget), KEY)) return TRUE;
    GtkFileChooser *chooser = GTK_FILE_CHOOSER(widget);
    // Keep application-supplied previews and avoid attaching to both a dialog
    // and its internal chooser, which forward the same preview-widget property.
    if (gtk_file_chooser_get_preview_widget(chooser)) return TRUE;
    Preview *p = g_new0(Preview, 1); p->alive = TRUE;
    p->pane = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10); gtk_widget_set_name(p->pane, "xetalFilePreviewPane");
    gtk_container_set_border_width(GTK_CONTAINER(p->pane), 12); gtk_widget_set_size_request(p->pane, 264, -1);
    gtk_widget_set_valign(p->pane, GTK_ALIGN_START);
    label(p->pane, "PREVIEW"); p->image = gtk_image_new(); gtk_widget_set_size_request(p->image, 240, 160);
    gtk_box_pack_start(GTK_BOX(p->pane), p->image, FALSE, FALSE, 0);
    p->name = label(p->pane, ""); gtk_label_set_selectable(GTK_LABEL(p->name), TRUE);
    p->message = label(p->pane, "Select a file or folder");
    GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL); gtk_widget_set_size_request(scroll, -1, 160);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    p->text = gtk_text_view_new(); gtk_text_view_set_editable(GTK_TEXT_VIEW(p->text), FALSE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(p->text), GTK_WRAP_WORD_CHAR);
    gtk_container_add(GTK_CONTAINER(scroll), p->text); gtk_box_pack_start(GTK_BOX(p->pane), scroll, FALSE, FALSE, 0);
    p->details = label(p->pane, ""); gtk_label_set_selectable(GTK_LABEL(p->details), TRUE);
    g_object_set_data_full(G_OBJECT(widget), KEY, p, (GDestroyNotify)preview_free);
    g_signal_connect(widget, "destroy", G_CALLBACK(destroyed), p);
    gtk_file_chooser_set_preview_widget(chooser, p->pane); gtk_file_chooser_set_use_preview_label(chooser, FALSE);
    gtk_widget_show_all(p->pane); gtk_widget_hide(scroll); gtk_widget_hide(p->image);
    g_signal_connect(widget, "update-preview", G_CALLBACK(selected), NULL); selected(chooser, NULL);
    return TRUE;
}
G_MODULE_EXPORT void gtk_module_init(gint *argc, gchar ***argv) {
    (void)argc; (void)argv;
    if (!g_getenv("HYPRLAND_INSTANCE_SIGNATURE") || !g_getenv("XETAL_THEME_CONFIG")) return;
    gpointer klass = g_type_class_ref(GTK_TYPE_WIDGET);
    g_signal_add_emission_hook(g_signal_lookup("map", GTK_TYPE_WIDGET), 0, mapped, NULL, NULL);
    g_type_class_unref(klass);
}
