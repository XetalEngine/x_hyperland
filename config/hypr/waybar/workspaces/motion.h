/* Animate the native workspace row without reparenting its buttons. Waybar
 * keeps ownership, ordering, app icons and all of their input handlers. */
#pragma once

typedef struct {
    char *key;
    GtkWidget *widget;
    cairo_surface_t *image;
    GtkAllocation target;
    double x, width, alpha, from_x, from_width, from_alpha;
    gboolean present, seen;
} WorkspaceMotion;

typedef struct {
    GtkWidget *box, *clip, *parent;
    GSList *items;
    gulong allocation_handler, draw_handler, visible_handler;
    guint tick;
    gint64 started;
    double width, from_width;
    int target_width;
    gboolean ready, allocating;
} WorkspaceStrip;

static void motion_widget(WorkspaceMotion *item, GtkWidget *widget) {
    if (item->widget == widget) return;
    if (item->widget) g_object_remove_weak_pointer(G_OBJECT(item->widget), (gpointer *)&item->widget);
    item->widget = widget;
    if (widget) g_object_add_weak_pointer(G_OBJECT(widget), (gpointer *)&item->widget);
}

static void motion_free(WorkspaceMotion *item) {
    motion_widget(item, NULL);
    if (item->image) cairo_surface_destroy(item->image);
    g_free(item->key); g_free(item);
}

static double motion_progress(WorkspaceStrip *strip) {
    gboolean enabled = TRUE;
    g_object_get(gtk_widget_get_settings(strip->box), "gtk-enable-animations", &enabled, NULL);
    if (!strip->tick || !enabled) return 1;
    double t = CLAMP((g_get_monotonic_time() - strip->started) / 220000.0, 0.0, 1.0);
    return 1 - (1-t)*(1-t)*(1-t);
}

static void motion_sample(WorkspaceStrip *strip) {
    double p = motion_progress(strip);
    strip->width = strip->from_width + (strip->target_width-strip->from_width)*p;
    for (GSList *it=strip->items; it; it=it->next) {
        WorkspaceMotion *item=it->data;
        item->x = item->from_x + (item->target.x-item->from_x)*p;
        item->width = item->from_width + ((item->present ? item->target.width : 0)-item->from_width)*p;
        item->alpha = item->from_alpha + ((item->present ? 1 : 0)-item->from_alpha)*p;
    }
}

static void motion_place(WorkspaceStrip *strip) {
    GtkAllocation box; gtk_widget_get_allocation(strip->box, &box);
    for (GSList *it=strip->items; it; it=it->next) {
        WorkspaceMotion *item=it->data;
        if (!item->present || !item->widget) continue;
        /* Allocate at its natural width so text/icons never squash. The row
         * clips the reveal; the native input window moves with the pill. */
        GtkAllocation area=item->target;
        area.x=box.x+(int)(item->x+.5); area.y+=box.y;
        gtk_widget_size_allocate(item->widget, &area);
    }
}

static gboolean motion_frame(GtkWidget *widget, GdkFrameClock *clock, gpointer data) {
    WorkspaceStrip *strip=data;
    motion_sample(strip);
    gboolean done=motion_progress(strip)>=1;
    gtk_widget_set_size_request(strip->clip, MAX(1, (int)(strip->width+.5)), -1);
    motion_place(strip);
    gtk_widget_queue_draw(strip->box);
    if (!done) return G_SOURCE_CONTINUE;
    strip->tick=0;
    for (GSList *it=strip->items, *next; it; it=next) {
        next=it->next; WorkspaceMotion *item=it->data;
        if (!item->present) { strip->items=g_slist_delete_link(strip->items,it); motion_free(item); }
    }
    return G_SOURCE_REMOVE;
}

static void motion_allocated(GtkWidget *box, GtkAllocation *allocation, gpointer data) {
    WorkspaceStrip *strip=data;
    if (strip->allocating) return;
    strip->allocating=TRUE;
    motion_sample(strip);
    int minimum, natural; gtk_widget_get_preferred_width(box,&minimum,&natural);
    gboolean changed=strip->target_width!=natural;
    for (GSList *it=strip->items; it; it=it->next) {
        WorkspaceMotion *item=it->data;
        item->seen=FALSE;
    }
    GList *children=gtk_container_get_children(GTK_CONTAINER(box));
    for (GList *it=children; it; it=it->next) {
        GtkWidget *button=it->data;
        if (!gtk_widget_get_visible(button)) continue;
        const char *key=g_object_get_data(G_OBJECT(button),"xetal-workspace-motion-key");
        char fallback[64]; g_snprintf(fallback,sizeof fallback,"widget:%p",(void *)button);
        if (!key) key=fallback;
        WorkspaceMotion *item=NULL;
        for (GSList *node=strip->items; node; node=node->next)
            if (!g_strcmp0(((WorkspaceMotion *)node->data)->key,key)) { item=node->data; break; }
        GtkAllocation target; gtk_widget_get_allocation(button,&target);
        target.x-=allocation->x; target.y-=allocation->y;
        if (!item) {
            item=g_new0(WorkspaceMotion,1); item->key=g_strdup(key);
            item->x=item->from_x=target.x;
            strip->items=g_slist_append(strip->items,item); changed=TRUE;
        }
        if (!item->present || item->target.x!=target.x || item->target.width!=target.width)
            changed=TRUE;
        item->target=target; item->seen=TRUE; motion_widget(item,button);
    }
    g_list_free(children);
    for (GSList *it=strip->items; it; it=it->next) {
        WorkspaceMotion *item=it->data;
        if (item->present!=item->seen) changed=TRUE;
        item->present=item->seen;
    }
    if (changed) {
        for (GSList *it=strip->items; it; it=it->next) {
            WorkspaceMotion *item=it->data;
            item->from_x=item->x; item->from_width=item->width; item->from_alpha=item->alpha;
        }
        strip->from_width=strip->width; strip->target_width=natural;
        if (strip->ready && !strip->tick)
            strip->tick=gtk_widget_add_tick_callback(strip->clip,motion_frame,strip,NULL);
        strip->started=g_get_monotonic_time();
        motion_sample(strip);
    }
    if (!strip->ready) {
        strip->ready=TRUE;
        gtk_widget_set_size_request(strip->clip,MAX(1,natural),-1);
    }
    motion_place(strip);
    strip->allocating=FALSE;
}

static gboolean motion_draw(GtkWidget *box, cairo_t *cr, gpointer data) {
    WorkspaceStrip *strip=data;
    if (!strip->ready) return FALSE;
    GtkStyleContext *style=gtk_widget_get_style_context(box);
    gtk_render_background(style,cr,0,0,gtk_widget_get_allocated_width(box),gtk_widget_get_allocated_height(box));
    gtk_render_frame(style,cr,0,0,gtk_widget_get_allocated_width(box),gtk_widget_get_allocated_height(box));
    for (GSList *it=strip->items; it; it=it->next) {
        WorkspaceMotion *item=it->data;
        if (item->present && item->widget) {
            int width=gtk_widget_get_allocated_width(item->widget), height=gtk_widget_get_allocated_height(item->widget);
            int scale=gtk_widget_get_scale_factor(box);
            if (item->image) cairo_surface_destroy(item->image);
            item->image=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,MAX(1,width*scale),MAX(1,height*scale));
            cairo_surface_set_device_scale(item->image,scale,scale);
            cairo_t *snapshot=cairo_create(item->image);
            gtk_widget_draw(item->widget,snapshot); cairo_destroy(snapshot);
        }
        if (!item->image || item->alpha<=0) continue;
        cairo_save(cr);
        cairo_rectangle(cr,item->x,item->target.y,MAX(0,item->width),item->target.height);
        cairo_clip(cr); cairo_set_source_surface(cr,item->image,item->x,item->target.y);
        cairo_paint_with_alpha(cr,item->alpha); cairo_restore(cr);
    }
    return TRUE;
}

static void motion_visibility(GObject *box,GParamSpec *property,gpointer data) {
    WorkspaceStrip *strip=data;
    gtk_widget_set_visible(strip->clip,gtk_widget_get_visible(GTK_WIDGET(box)));
}

static gboolean motion_scroll(GtkWidget *widget,GdkEventScroll *event,gpointer data) {
    /* This viewport clips animation; it is not a new scrollable control.
     * Leave wheel actions to the original Waybar module above it. */
    g_signal_stop_emission_by_name(widget,"scroll-event");
    return FALSE;
}

static WorkspaceStrip *motion_attach(GtkWidget *box) {
    GtkWidget *parent=gtk_widget_get_parent(box);
    if (!GTK_IS_BIN(parent) || gtk_orientable_get_orientation(GTK_ORIENTABLE(box))!=GTK_ORIENTATION_HORIZONTAL) return NULL;
    WorkspaceStrip *strip=g_new0(WorkspaceStrip,1); strip->box=box; strip->parent=parent;
    strip->clip=gtk_scrolled_window_new(NULL,NULL);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(strip->clip),GTK_POLICY_EXTERNAL,GTK_POLICY_NEVER);
    gtk_scrolled_window_set_shadow_type(GTK_SCROLLED_WINDOW(strip->clip),GTK_SHADOW_NONE);
    gtk_scrolled_window_set_propagate_natural_height(GTK_SCROLLED_WINDOW(strip->clip),TRUE);
    gtk_scrolled_window_set_kinetic_scrolling(GTK_SCROLLED_WINDOW(strip->clip),FALSE);
    gtk_scrolled_window_set_capture_button_press(GTK_SCROLLED_WINDOW(strip->clip),FALSE);
    g_signal_connect(strip->clip,"scroll-event",G_CALLBACK(motion_scroll),NULL);
    gtk_widget_set_can_focus(strip->clip,FALSE);
    int minimum,natural; gtk_widget_get_preferred_width(box,&minimum,&natural);
    strip->width=strip->from_width=strip->target_width=natural;
    gtk_widget_set_size_request(strip->clip,MAX(1,natural),-1);
    g_object_ref(box); gtk_container_remove(GTK_CONTAINER(parent),box);
    gtk_container_add(GTK_CONTAINER(strip->clip),box); g_object_unref(box);
    gtk_container_add(GTK_CONTAINER(parent),strip->clip);
    gtk_widget_show(gtk_bin_get_child(GTK_BIN(strip->clip)));
    gtk_widget_set_visible(strip->clip,gtk_widget_get_visible(box));
    strip->allocation_handler=g_signal_connect_after(box,"size-allocate",G_CALLBACK(motion_allocated),strip);
    strip->draw_handler=g_signal_connect(box,"draw",G_CALLBACK(motion_draw),strip);
    strip->visible_handler=g_signal_connect(box,"notify::visible",G_CALLBACK(motion_visibility),strip);
    g_object_add_weak_pointer(G_OBJECT(box),(gpointer *)&strip->box);
    g_object_add_weak_pointer(G_OBJECT(parent),(gpointer *)&strip->parent);
    g_object_add_weak_pointer(G_OBJECT(strip->clip),(gpointer *)&strip->clip);
    return strip;
}

static void motion_detach(WorkspaceStrip *strip) {
    if (!strip) return;
    if (strip->tick && strip->clip) gtk_widget_remove_tick_callback(strip->clip,strip->tick);
    if (strip->box) {
        g_signal_handler_disconnect(strip->box,strip->allocation_handler);
        g_signal_handler_disconnect(strip->box,strip->draw_handler);
        g_signal_handler_disconnect(strip->box,strip->visible_handler);
        if (strip->parent && strip->clip && !gtk_widget_in_destruction(strip->parent)) {
            g_object_ref(strip->box);
            gtk_container_remove(GTK_CONTAINER(gtk_widget_get_parent(strip->box)),strip->box);
            gtk_container_remove(GTK_CONTAINER(strip->parent),strip->clip);
            gtk_container_add(GTK_CONTAINER(strip->parent),strip->box); g_object_unref(strip->box);
        }
        g_object_remove_weak_pointer(G_OBJECT(strip->box),(gpointer *)&strip->box);
    }
    if (strip->parent) g_object_remove_weak_pointer(G_OBJECT(strip->parent),(gpointer *)&strip->parent);
    if (strip->clip) g_object_remove_weak_pointer(G_OBJECT(strip->clip),(gpointer *)&strip->clip);
    g_slist_free_full(strip->items,(GDestroyNotify)motion_free); g_free(strip);
}
