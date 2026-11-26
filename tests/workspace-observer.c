/* Read-only frame observations inside a disposable, real Waybar process. */
#include "../config/hypr/waybar/pins/waybar_cffi_module.h"
#include <gtk-layer-shell.h>
#include <json-glib/json-glib.h>
#include <stdio.h>
#include <string.h>
const size_t wbcffi_version=2;
typedef struct { GtkWidget *root;GdkFrameClock *clock;gulong signal; } Observer;
static GtkWidget *find(GtkWidget *widget,const char *name,gboolean style) {
    if(style ? gtk_style_context_has_class(gtk_widget_get_style_context(widget),name) : !strcmp(gtk_widget_get_name(widget),name))return widget;
    if(!GTK_IS_CONTAINER(widget))return NULL;
    GList *children=gtk_container_get_children(GTK_CONTAINER(widget));GtkWidget *result=NULL;
    for(GList *it=children;it && !result;it=it->next)result=find(it->data,name,style);
    g_list_free(children);return result;
}
static void after_paint(GdkFrameClock *clock,gpointer data) {
    Observer *observer=data;GtkWidget *top=gtk_widget_get_toplevel(observer->root);
    GtkWidget *box=find(top,"workspaces",FALSE),*add=find(top,"new-workspace",FALSE);
    if(!GTK_IS_CONTAINER(box)||!add)return;
    GdkRectangle area={0};GdkMonitor *monitor=gtk_layer_get_monitor(GTK_WINDOW(top));
    if(monitor)gdk_monitor_get_geometry(monitor,&area);
    int x=0,y=0;gtk_widget_translate_coordinates(add,top,0,0,&x,&y);
    JsonBuilder *builder=json_builder_new();json_builder_begin_object(builder);
    json_builder_set_member_name(builder,"monitor_x");json_builder_add_int_value(builder,area.x);
    json_builder_set_member_name(builder,"add_x");json_builder_add_int_value(builder,x);
    json_builder_set_member_name(builder,"time");json_builder_add_int_value(builder,g_get_monotonic_time());
    GtkWidget *mode=find(top,"workspace-mode",FALSE);const char *layout="unavailable";
    const char *modes[]={"individual","tiling","floating","kde"};
    if(mode)for(guint i=0;i<G_N_ELEMENTS(modes);i++)
        if(gtk_style_context_has_class(gtk_widget_get_style_context(mode),modes[i]))layout=modes[i];
    json_builder_set_member_name(builder,"mode");json_builder_add_string_value(builder,layout);
    json_builder_set_member_name(builder,"buttons");json_builder_begin_array(builder);
    GList *children=gtk_container_get_children(GTK_CONTAINER(box));
    for(GList *it=children;it;it=it->next) {
        GtkWidget *button=it->data,*label=find(button,"workspace-label",TRUE);
        if(!gtk_widget_get_mapped(button)||!GTK_IS_LABEL(label))continue;
        gtk_widget_translate_coordinates(button,top,0,0,&x,&y);
        json_builder_begin_object(builder);
        json_builder_set_member_name(builder,"id");json_builder_add_int_value(builder,(long)g_object_get_data(G_OBJECT(button),"xetal-workspace-id"));
        json_builder_set_member_name(builder,"label");json_builder_add_string_value(builder,gtk_label_get_text(GTK_LABEL(label)));
        json_builder_set_member_name(builder,"x");json_builder_add_int_value(builder,x);
        json_builder_set_member_name(builder,"width");json_builder_add_int_value(builder,gtk_widget_get_allocated_width(button));
        json_builder_end_object(builder);
    }
    g_list_free(children);json_builder_end_array(builder);json_builder_end_object(builder);
    JsonNode *node=json_builder_get_root(builder);JsonGenerator *generator=json_generator_new();json_generator_set_root(generator,node);
    char *text=json_generator_to_data(generator,NULL);FILE *file=fopen(g_getenv("FUSION_WORKSPACE_REPORT"),"a");
    if(file){fprintf(file,"%s\n",text);fclose(file);}
    g_free(text);json_node_free(node);g_object_unref(generator);g_object_unref(builder);
}
static void mapped(GtkWidget *widget,gpointer data) {
    Observer *observer=data;if(observer->clock)return;
    observer->clock=gtk_widget_get_frame_clock(widget);g_object_ref(observer->clock);
    observer->signal=g_signal_connect(observer->clock,"after-paint",G_CALLBACK(after_paint),observer);
}
void *wbcffi_init(const wbcffi_init_info *info,const wbcffi_config_entry *entries,size_t length) {
    Observer *observer=g_new0(Observer,1);observer->root=gtk_label_new("");
    gtk_container_add(info->get_root_widget(info->obj),observer->root);
    g_signal_connect(observer->root,"map",G_CALLBACK(mapped),observer);gtk_widget_show(observer->root);return observer;
}
void wbcffi_deinit(void *instance) {
    Observer *observer=instance;
    if(observer->clock){g_signal_handler_disconnect(observer->clock,observer->signal);g_object_unref(observer->clock);}
    gtk_widget_destroy(observer->root);g_free(observer);
}
void wbcffi_update(void *instance) {}
void wbcffi_refresh(void *instance,int signal) {}
