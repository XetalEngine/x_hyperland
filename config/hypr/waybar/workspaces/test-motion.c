/* Real GTK layout/paint checks in Xvfb; never dispatches to a compositor. */
#include "button.c"

static GtkWidget *window, *host, *box;
static Workspaces *owner;
static char *destination, *faces_path;
static int paints;
static GtkContainer *root_widget(wbcffi_module *unused) { return GTK_CONTAINER(host); }

static GtkWidget *pill(int number) {
    char text[24]; g_snprintf(text,sizeof text,"%d ",number);
    GtkWidget *button=gtk_button_new(), *content=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0);
    GtkWidget *label=gtk_label_new(text);
    gtk_style_context_add_class(gtk_widget_get_style_context(label),"workspace-label");
    gtk_style_context_add_class(gtk_widget_get_style_context(button),"empty");
    gtk_box_pack_start(GTK_BOX(content),label,FALSE,FALSE,0);gtk_container_add(GTK_CONTAINER(button),content);
    gtk_box_pack_start(GTK_BOX(box),button,FALSE,FALSE,0);gtk_widget_show_all(button);
    return button;
}

static void faces(const int *ids,int count) {
    GString *text=g_string_new("enabled\n");
    for(int i=0;i<count;i++) g_string_append_printf(text,"%d %d\n",ids[i],i+1);
    g_assert_true(g_file_set_contents(faces_path,text->str,-1,NULL));g_string_free(text,TRUE);
}

static gboolean painted(GtkWidget *widget,cairo_t *cr,gpointer data) {
    paints++;
    GList *children=gtk_container_get_children(GTK_CONTAINER(box));
    for(GList *it=children;it;it=it->next) {
        Decoration *d=g_object_get_data(G_OBJECT(it->data),"xetal-workspace-decoration");
        g_assert_nonnull(d);g_assert_cmpint(d->face,>,0);
        char expected[24];g_snprintf(expected,sizeof expected,"%d ",d->face);
        g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(d->label)),==,expected);
    }
    g_list_free(children);return FALSE;
}

static void screenshot(const char *name) {
    GdkPixbuf *image=gdk_pixbuf_get_from_window(gtk_widget_get_window(window),0,0,
        gtk_widget_get_allocated_width(window),gtk_widget_get_allocated_height(window));
    char *path=g_build_filename(destination,name,NULL);
    g_assert_true(gdk_pixbuf_save(image,path,"png",NULL,NULL));g_free(path);g_object_unref(image);
}

static void pump(int milliseconds) {
    gint64 end=g_get_monotonic_time()+milliseconds*1000;
    do {
        while(g_main_context_iteration(NULL,FALSE));
        g_usleep(1000);
    } while(g_get_monotonic_time()<end);
}

static void transition(gboolean growing,const char *image) {
    double previous=owner->strip->width;
    int changes=0;gboolean captured=FALSE;
    gint64 end=g_get_monotonic_time()+500000;
    while(g_get_monotonic_time()<end) {
        pump(8);double current=owner->strip->width;
        if(current!=previous) {
            g_assert_true(growing ? current>=previous : current<=previous);
            changes++;previous=current;
        }
        if(!captured && changes>=3) { screenshot(image);captured=TRUE; }
    }
    g_assert_cmpint(changes,>=,5);g_assert_cmpuint(owner->strip->tick,==,0);
    g_assert_cmpfloat(owner->strip->width,==,owner->strip->target_width);
}

int main(int argc,char **argv) {
    gtk_init(&argc,&argv);g_assert_cmpint(argc,==,2);destination=argv[1];
    char *runtime=g_build_filename(destination,"runtime",NULL);
    char *directory=g_build_filename(runtime,"hypr","test",NULL);g_mkdir_with_parents(directory,0700);
    faces_path=g_build_filename(directory,"xetal-cube-faces",NULL);
    g_setenv("XDG_RUNTIME_DIR",runtime,TRUE);g_setenv("HYPRLAND_INSTANCE_SIGNATURE","test",TRUE);
    g_object_set(gtk_settings_get_default(),"gtk-enable-animations",TRUE,NULL);
    window=gtk_window_new(GTK_WINDOW_TOPLEVEL);gtk_window_set_default_size(GTK_WINDOW(window),620,42);
    gtk_window_set_title(GTK_WINDOW(window),"Workspace transitions");
    GtkWidget *bar=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0), *module=gtk_event_box_new();
    gtk_container_add(GTK_CONTAINER(window),bar);
    box=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0);gtk_widget_set_name(box,"workspaces");
    gtk_container_add(GTK_CONTAINER(module),box);gtk_box_pack_start(GTK_BOX(bar),module,FALSE,FALSE,0);
    host=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,0);gtk_box_pack_start(GTK_BOX(bar),host,FALSE,FALSE,0);
    GtkWidget *mode=gtk_label_new("KDE");gtk_box_pack_start(GTK_BOX(bar),mode,FALSE,FALSE,0);
    int ids[]={2,7,8,17,24};GtkWidget *buttons[5];faces(ids,4);
    for(int i=0;i<4;i++)buttons[i]=pill(ids[i]);
    GtkCssProvider *css=gtk_css_provider_new();
    char *css_path=g_build_filename(g_get_home_dir(),".config/hypr/waybar/style.css",NULL);
    gtk_css_provider_load_from_path(css,css_path,NULL);g_free(css_path);
    gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(css);
    g_signal_connect(box,"draw",G_CALLBACK(painted),NULL);
    wbcffi_init_info info={.get_root_widget=root_widget};owner=wbcffi_init(&info,NULL,0);
    gtk_widget_show_all(window);pump(350);g_assert_nonnull(owner->strip);screenshot("before.png");
    gtk_widget_hide(box);pump(40);g_assert_false(gtk_widget_get_visible(owner->strip->clip));
    gtk_widget_show(box);pump(40);g_assert_true(gtk_widget_get_visible(owner->strip->clip));
    faces(ids,5);buttons[4]=pill(ids[4]);transition(TRUE,"adding.png");screenshot("added.png");
    /* Hyprland reload recreates the native pills, but these are the same IDs. */
    for(int i=0;i<5;i++)gtk_widget_destroy(buttons[i]);
    for(int i=0;i<5;i++)buttons[i]=pill(ids[i]);
    pump(80);g_assert_cmpuint(owner->strip->tick,==,0);
    int remaining[]={2,7,17,24};faces(remaining,4);gtk_widget_destroy(buttons[2]);
    transition(FALSE,"removing.png");screenshot("removed.png");
    /* Interrupt an entrance with removal and reload the module mid-animation. */
    faces(ids,5);GtkWidget *rapid=pill(8);pump(45);
    faces(remaining,4);gtk_widget_destroy(rapid);pump(45);
    wbcffi_deinit(owner);owner=wbcffi_init(&info,NULL,0);pump(350);
    g_assert_cmpuint(owner->strip->tick,==,0);
    g_object_set(gtk_settings_get_default(),"gtk-enable-animations",FALSE,NULL);
    faces(ids,5);pill(8);pump(80);g_assert_cmpuint(owner->strip->tick,==,0);
    g_assert_cmpint(paints,>,15);
    wbcffi_deinit(owner);gtk_widget_destroy(window);pump(20);
    g_free(faces_path);g_free(directory);g_free(runtime);
    g_print("PASS: labels correct in every paint; smooth growth/shrink; stable rebuilds; interrupted transitions; hide/show; teardown; reduced motion.\n");
    return 0;
}
