/* Shared only within one Waybar window; app pins keep their own menu. */
#pragma once
#include <gtk/gtk.h>

typedef struct {
    GtkWidget *(*submenu)(gpointer owner);
    gpointer owner;
} XetalBarOptionsMenu;

static inline void xetal_append_bar_options(GtkWidget *menu, GtkWidget *anchor, gboolean separator) {
    GtkWidget *top = gtk_widget_get_toplevel(anchor);
    XetalBarOptionsMenu *options = g_object_get_data(G_OBJECT(top), "xetal-bar-options");
    if (!options) return;
    if (separator) gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
    GtkWidget *item = gtk_menu_item_new_with_label("Options");
    gtk_style_context_add_class(gtk_widget_get_style_context(item), "xetal-bar-options-entry");
    gtk_menu_item_set_submenu(GTK_MENU_ITEM(item), options->submenu(options->owner));
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
}
