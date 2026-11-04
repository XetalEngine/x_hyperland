/* Exercise the real GTK overlay and pointer routing in a disposable X server.
 * Replace only process spawning, so no desktop workspaces are changed. */
#include <gtk/gtk.h>
#include <stdio.h>
static char *directory;
static void record(const char *action) {
    char *file = g_build_filename(directory, "actions", NULL);
    FILE *stream = fopen(file, "a");
    fprintf(stream, "%s\n", action); fclose(stream); g_free(file);
}
static GSubprocess *capture_spawn(const gchar *const *argv, GSubprocessFlags flags, GError **error) {
    char *base = g_path_get_basename(argv[1]);
    char *line = g_strdup_printf("%s %s", base, argv[2]);
    record(line); g_free(base); g_free(line); return NULL;
}
#define g_subprocess_newv capture_spawn
#include "button.c"
#undef g_subprocess_newv

static GtkWidget *window, *host, *workspace_box, *empty, *occupied, *minimized;
static Workspaces *instance;
static GtkContainer *get_root(wbcffi_module *unused) { return GTK_CONTAINER(host); }
static gboolean activated(GtkWidget *widget, GdkEventButton *event, gpointer data) {
    if (event->type == GDK_BUTTON_PRESS) { record(data); return TRUE; }
    return FALSE;
}
static GtkWidget *workspace(const char *name, gboolean is_empty, const char *action) {
    GtkWidget *button=gtk_button_new(), *box=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0), *label=gtk_label_new(name);
    gtk_style_context_add_class(gtk_widget_get_style_context(label),"workspace-label");
    if (is_empty) gtk_style_context_add_class(gtk_widget_get_style_context(button),"empty");
    gtk_container_add(GTK_CONTAINER(button),box); gtk_box_pack_start(GTK_BOX(box),label,FALSE,FALSE,0);
    gtk_box_pack_start(GTK_BOX(workspace_box),button,FALSE,FALSE,0);
    g_signal_connect(button,"button-press-event",G_CALLBACK(activated),(gpointer)action);
    gtk_widget_show_all(button);return button;
}
static gboolean keyboard(GtkWidget *widget, GdkEventKey *event, gpointer data) {
    if (event->keyval==GDK_KEY_o) gtk_style_context_remove_class(gtk_widget_get_style_context(empty),"empty");
    if (event->keyval==GDK_KEY_e) gtk_style_context_add_class(gtk_widget_get_style_context(empty),"empty");
    if (event->keyval==GDK_KEY_r) { gtk_widget_destroy(empty);empty=NULL; }
    if (event->keyval==GDK_KEY_n) empty=workspace("5 ",TRUE,"activate 5");
    if (event->keyval==GDK_KEY_l) { gtk_widget_destroy(occupied);occupied=NULL; }
    if (event->keyval==GDK_KEY_p) {
        GdkPixbuf *image=gdk_pixbuf_get_from_window(gtk_widget_get_window(window),0,0,
            gtk_widget_get_allocated_width(window),gtk_widget_get_allocated_height(window));
        char *file=g_build_filename(directory,"feedback.png",NULL);
        char *temporary=g_strconcat(file,".tmp",NULL);
        g_assert_true(gdk_pixbuf_save(image,temporary,"png",NULL,NULL));
        g_assert_cmpint(rename(temporary,file),==,0);
        g_object_unref(image);g_free(temporary);g_free(file);
    }
    if (event->keyval==GDK_KEY_u) {
        GtkWidget *a=find_widget(occupied,"workspace-label",TRUE), *b=find_widget(empty,"workspace-label",TRUE);
        /* Waybar sets markup on every workspace/window update. Read back in
         * this same event: a later timeout must not hide a visible flicker. */
        for (int i=0; i<25; ++i) {
            GtkWidget *m=find_widget(minimized,"workspace-label",TRUE);
            gtk_label_set_markup(GTK_LABEL(m),"xetal-minimized-ws-5 ");
            g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(m)),==,instance->cube?"M2 ":"M5 ");
            gtk_label_set_markup(GTK_LABEL(a),"<b>2</b> ");
            gtk_label_set_markup(GTK_LABEL(b),"5 ");
            char *text=g_strdup_printf("labels %s|%s",gtk_label_get_text(GTK_LABEL(a)),gtk_label_get_text(GTK_LABEL(b)));
            record(text);g_free(text);
        }
    }
    if (event->keyval==GDK_KEY_b) {
        wbcffi_deinit(instance);
        g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(find_widget(minimized,"workspace-label",TRUE))),==,"xetal-minimized-ws-5 ");
        g_assert(GTK_IS_BOX(gtk_bin_get_child(GTK_BIN(empty))));
        wbcffi_init_info info={.get_root_widget=get_root};instance=wbcffi_init(&info,NULL,0);
    }
    return TRUE;
}
static gboolean state(gpointer unused) {
    char *file=g_build_filename(directory,"geometry",NULL);
    gint x=-1,y=-1,bx=-1,by=-1;gboolean visible=FALSE;
    Decoration *d=empty ? g_object_get_data(G_OBJECT(empty),"xetal-workspace-decoration") : NULL;
    if (d) {
        g_assert_cmpint(GPOINTER_TO_INT(g_object_get_data(G_OBJECT(empty),"xetal-workspace-id")),==,5);
        visible=gtk_widget_get_visible(d->close);
        gtk_widget_translate_coordinates(d->close,window,gtk_widget_get_allocated_width(d->close)/2,
                                         gtk_widget_get_allocated_height(d->close)/2,&x,&y);
        gtk_widget_translate_coordinates(empty,window,8,gtk_widget_get_allocated_height(empty)/2,&bx,&by);
    }
    char *text=g_strdup_printf("%d %d %d %d %d",visible,x,y,bx,by);
    g_file_set_contents(file,text,-1,NULL);g_free(text);g_free(file);
    gint ax=0,ay=0,nx=0,ny=0;
    gtk_widget_translate_coordinates(instance->button,window,0,0,&ax,&ay);
    gtk_widget_translate_coordinates(workspace_box,window,0,0,&nx,&ny);
    gboolean blocked=gtk_style_context_has_class(gtk_widget_get_style_context(instance->button),"cube-blocked");
    file=g_build_filename(directory,"add-state",NULL);
    char *tip=gtk_widget_get_tooltip_text(instance->button);
    text=g_strdup_printf("%d %d %d %d %d %d\n%s",ax+gtk_widget_get_allocated_width(instance->button)/2,
        ay+gtk_widget_get_allocated_height(instance->button)/2,ax,blocked,nx,gtk_widget_get_allocated_width(window),
        tip);
    g_file_set_contents(file,text,-1,NULL);g_free(tip);g_free(text);g_free(file);
    if (minimized) {
        Decoration *md=g_object_get_data(G_OBJECT(minimized),"xetal-workspace-decoration");
        if(md){
            g_assert_null(g_object_get_data(G_OBJECT(minimized),"xetal-workspace-id"));
            g_assert_true(gtk_widget_get_visible(minimized));g_assert_false(gtk_widget_get_visible(md->close));
            g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(md->label)),==,instance->cube?"M2 ":"M5 ");
            g_assert_nonnull(find_widget(minimized,"minimized-app-icon",FALSE));
        }
    }
    if (occupied && empty) {
        file=g_build_filename(directory,"cube-state",NULL);
        GtkWidget *a=find_widget(occupied,"workspace-label",TRUE), *b=find_widget(empty,"workspace-label",TRUE);
        text=g_strdup_printf("%s|%s|%d|%d",gtk_label_get_text(GTK_LABEL(a)),gtk_label_get_text(GTK_LABEL(b)),gtk_widget_get_sensitive(instance->button),visible);
        g_file_set_contents(file,text,-1,NULL);g_free(text);g_free(file);
    }
    return G_SOURCE_CONTINUE;
}
int main(int argc,char **argv) {
    gtk_init(&argc,&argv);if(argc!=2)return 2;directory=argv[1];
    window=gtk_window_new(GTK_WINDOW_TOPLEVEL);gtk_window_set_title(GTK_WINDOW(window),"Workspace close test");
    gtk_window_set_default_size(GTK_WINDOW(window),360,45);
    GtkWidget *bar=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,2);gtk_container_add(GTK_CONTAINER(window),bar);
    workspace_box=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0);gtk_widget_set_name(workspace_box,"workspaces");
    gtk_box_pack_start(GTK_BOX(bar),workspace_box,FALSE,FALSE,0);
    occupied=workspace("2 ",FALSE,"activate 2");empty=workspace("5 ",TRUE,"activate 5");
    GtkWidget *special=workspace("xetal-startup ",FALSE,"special");
    gtk_style_context_add_class(gtk_widget_get_style_context(special),"special");
    minimized=workspace("xetal-minimized-ws-5 ",FALSE,"minimized 5");
    gtk_style_context_add_class(gtk_widget_get_style_context(minimized),"special");
    GtkWidget *icon=gtk_image_new_from_icon_name("web-browser",GTK_ICON_SIZE_MENU);gtk_widget_set_name(icon,"minimized-app-icon");
    gtk_box_pack_start(GTK_BOX(gtk_bin_get_child(GTK_BIN(minimized))),icon,FALSE,FALSE,0);
    host=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0);gtk_box_pack_start(GTK_BOX(bar),host,FALSE,FALSE,0);
    GtkCssProvider *css=gtk_css_provider_new();
    char *css_path=g_build_filename(g_get_home_dir(),".config/hypr/waybar/style.css",NULL);
    gtk_css_provider_load_from_path(css,css_path,NULL);g_free(css_path);
    gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    wbcffi_init_info info={.get_root_widget=get_root};instance=wbcffi_init(&info,NULL,0);
    g_signal_connect(window,"key-press-event",G_CALLBACK(keyboard),NULL);
    gtk_widget_show_all(window);g_timeout_add(100,state,NULL);
    gtk_main();return 0;
}
