/* Session-local hover requests. GTK owns the widget and disconnects its handlers.
 * A separate preview process captures; the bar never blocks on compositor IPC. */
#include <json-glib/json-glib.h>
static void fusion_preview_request(GtkWidget *widget, gboolean show) {
    const char *runtime=g_getenv("XDG_RUNTIME_DIR"), *signature=g_getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if(!runtime||!signature||strchr(signature,'/'))return;
    char *path=g_build_filename(runtime,"hypr",signature,"fusion-hover.json",NULL);
    JsonBuilder *builder=json_builder_new();json_builder_begin_object(builder);
    json_builder_set_member_name(builder,"show");json_builder_add_boolean_value(builder,show);
    json_builder_set_member_name(builder,"time");json_builder_add_double_value(builder,g_get_real_time()/1000000.);
    if(show){
        GtkWidget *content=GTK_IS_BIN(widget)?gtk_bin_get_child(GTK_BIN(widget)):NULL;
        char *title=content?gtk_widget_get_tooltip_text(content):NULL;
        json_builder_set_member_name(builder,"title");json_builder_add_string_value(builder,title?title:"");g_free(title);
        json_builder_set_member_name(builder,"workspace");json_builder_add_int_value(builder,(long)g_object_get_data(G_OBJECT(widget),"fusion-preview-workspace"));
        GtkWidget *top=gtk_widget_get_toplevel(widget);int x=0,y=0;
        gtk_widget_translate_coordinates(widget,top,0,0,&x,&y);
        GdkMonitor *monitor=gtk_layer_is_layer_window(GTK_WINDOW(top))?gtk_layer_get_monitor(GTK_WINDOW(top)):NULL;
        GdkRectangle area={0};if(monitor)gdk_monitor_get_geometry(monitor,&area);
        json_builder_set_member_name(builder,"monitor_x");json_builder_add_int_value(builder,area.x);
        json_builder_set_member_name(builder,"monitor_y");json_builder_add_int_value(builder,area.y);
        gboolean layer=gtk_layer_is_layer_window(GTK_WINDOW(top));
        const int width=gtk_widget_get_allocated_width(top),height=gtk_widget_get_allocated_height(top);
        if(layer){
            const int left=gtk_layer_get_margin(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_LEFT);
            const int right=gtk_layer_get_margin(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_RIGHT);
            const int upper=gtk_layer_get_margin(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_TOP);
            const int lower=gtk_layer_get_margin(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_BOTTOM);
            x+=gtk_layer_get_anchor(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_LEFT)?left:
               gtk_layer_get_anchor(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_RIGHT)?area.width-width-right:(area.width-width+left-right)/2;
            y+=gtk_layer_get_anchor(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_TOP)?upper:
               gtk_layer_get_anchor(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_BOTTOM)?area.height-height-lower:(area.height-height+upper-lower)/2;
        }
        json_builder_set_member_name(builder,"x");json_builder_add_int_value(builder,area.x+x+gtk_widget_get_allocated_width(widget)/2);
        json_builder_set_member_name(builder,"y");json_builder_add_int_value(builder,area.y+y+gtk_widget_get_allocated_height(widget)/2);
        gboolean bottom=layer && height<width && gtk_layer_get_anchor(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_BOTTOM);
        json_builder_set_member_name(builder,"bottom");json_builder_add_boolean_value(builder,bottom);
        const char *edge=height>width?(layer&&gtk_layer_get_anchor(GTK_WINDOW(top),GTK_LAYER_SHELL_EDGE_RIGHT)?"right":"left"):(bottom?"bottom":"top");
        json_builder_set_member_name(builder,"edge");json_builder_add_string_value(builder,edge);
    }
    json_builder_end_object(builder);JsonNode *node=json_builder_get_root(builder);
    JsonGenerator *generator=json_generator_new();json_generator_set_root(generator,node);
    char *data=json_generator_to_data(generator,NULL);g_file_set_contents(path,data,-1,NULL);
    g_free(data);g_free(path);json_node_free(node);g_object_unref(generator);g_object_unref(builder);
}
static gboolean fusion_preview_tick(gpointer data){fusion_preview_request(GTK_WIDGET(data),TRUE);return G_SOURCE_CONTINUE;}
static void fusion_preview_stop(gpointer data){if(data)g_source_remove(GPOINTER_TO_UINT(data));}
static void fusion_preview_destroy(GtkWidget *widget,gpointer data){
    if(g_object_get_data(G_OBJECT(widget),"fusion-preview-timer")){
        g_object_set_data(G_OBJECT(widget),"fusion-preview-timer",NULL);fusion_preview_request(widget,FALSE);
    }
}
static gboolean fusion_preview_enter(GtkWidget *widget,GdkEventCrossing *event,gpointer data){
    if(event->detail==GDK_NOTIFY_INFERIOR)return FALSE;
    fusion_preview_request(widget,TRUE);
    g_object_set_data_full(G_OBJECT(widget),"fusion-preview-timer",GUINT_TO_POINTER(g_timeout_add(250,fusion_preview_tick,widget)),fusion_preview_stop);
    return FALSE;
}
static gboolean fusion_preview_leave(GtkWidget *widget,GdkEventCrossing *event,gpointer data){
    if(event->detail==GDK_NOTIFY_INFERIOR)return FALSE;
    g_object_set_data(G_OBJECT(widget),"fusion-preview-timer",NULL);fusion_preview_request(widget,FALSE);return FALSE;
}
static void fusion_preview_attach(GtkWidget *widget,long workspace){
    if(GTK_IS_BUTTON(widget)&&gtk_style_context_has_class(gtk_widget_get_style_context(widget),"taskbar-window")){
        g_object_set_data(G_OBJECT(widget),"fusion-preview-workspace",(gpointer)workspace);
        if(!g_object_get_data(G_OBJECT(widget),"fusion-preview-attached")){
            g_object_set_data(G_OBJECT(widget),"fusion-preview-attached",GINT_TO_POINTER(1));
            gtk_widget_add_events(widget,GDK_ENTER_NOTIFY_MASK|GDK_LEAVE_NOTIFY_MASK);
            g_signal_connect(widget,"enter-notify-event",G_CALLBACK(fusion_preview_enter),NULL);
            g_signal_connect(widget,"leave-notify-event",G_CALLBACK(fusion_preview_leave),NULL);
            g_signal_connect(widget,"destroy",G_CALLBACK(fusion_preview_destroy),NULL);
        }
    }
    if(GTK_IS_CONTAINER(widget)){
        GList *children=gtk_container_get_children(GTK_CONTAINER(widget));
        for(GList *it=children;it;it=it->next)fusion_preview_attach(it->data,workspace);
        g_list_free(children);
    }
}
