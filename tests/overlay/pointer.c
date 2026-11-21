/* Send a synthetic click only to the named output of the private compositor. */
#include <wayland-client.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "virtual-pointer.h"

struct output { struct wl_output *object; char name[128]; };
static struct output outputs[16];
static unsigned count;
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void geometry(void *d,struct wl_output *o,int32_t x,int32_t y,int32_t w,int32_t h,int32_t s,const char *m,const char *n,int32_t t) {(void)d;(void)o;(void)x;(void)y;(void)w;(void)h;(void)s;(void)m;(void)n;(void)t;}
static void mode(void *d,struct wl_output *o,uint32_t f,int32_t w,int32_t h,int32_t r) {(void)d;(void)o;(void)f;(void)w;(void)h;(void)r;}
static void done(void *d,struct wl_output *o) {(void)d;(void)o;}
static void scale(void *d,struct wl_output *o,int32_t s) {(void)d;(void)o;(void)s;}
static void name(void *d,struct wl_output *o,const char *n) {(void)o;struct output *p=d;strncpy(p->name,n,sizeof(p->name)-1);}
static void description(void *d,struct wl_output *o,const char *s) {(void)d;(void)o;(void)s;}
static const struct wl_output_listener output_listener={geometry,mode,done,scale,name,description};
static void global(void *data,struct wl_registry *registry,uint32_t id,const char *interface,uint32_t version) {
    (void)data;
    if(!strcmp(interface,"zwlr_virtual_pointer_manager_v1") && version>=2)
        manager=wl_registry_bind(registry,id,&zwlr_virtual_pointer_manager_v1_interface,2);
    if(!strcmp(interface,"wl_output") && version>=4 && count<16) {
        struct output *p=&outputs[count++];p->object=wl_registry_bind(registry,id,&wl_output_interface,4);
        wl_output_add_listener(p->object,&output_listener,p);
    }
}
static void removed(void *d,struct wl_registry *r,uint32_t id) {(void)d;(void)r;(void)id;}
static const struct wl_registry_listener registry_listener={global,removed};
static uint32_t timestamp(void) {
    struct timespec now;assert(clock_gettime(CLOCK_MONOTONIC,&now)==0);
    return (uint32_t)((uint64_t)now.tv_sec*1000+now.tv_nsec/1000000);
}
int main(int argc,char **argv) {
    assert(argc==6); /* OUTPUT X Y WIDTH HEIGHT */
    struct wl_display *display=wl_display_connect(NULL);assert(display);
    struct wl_registry *registry=wl_display_get_registry(display);
    wl_registry_add_listener(registry,&registry_listener,NULL);
    wl_display_roundtrip(display);wl_display_roundtrip(display);assert(manager);
    struct wl_output *output=NULL;
    for(unsigned i=0;i<count;++i)if(!strcmp(outputs[i].name,argv[1]))output=outputs[i].object;
    assert(output);
    struct zwlr_virtual_pointer_v1 *pointer=zwlr_virtual_pointer_manager_v1_create_virtual_pointer_with_output(manager,NULL,output);
    /* Do not rely on the keyboard-focus warp. Hyprland skips a motion whose
     * floored coordinates did not change, and Xwayland's pointer may still
     * have coordinates from the preceding window. Approach, then enter the
     * intended point so both backends receive an actual motion event. */
    const int x=atoi(argv[2]),width=atoi(argv[4]);
    const int approach=x+16<width ? x+16 : x-16;
    assert(approach>=0 && approach<width && approach!=x);
    zwlr_virtual_pointer_v1_motion_absolute(pointer,timestamp(),approach,atoi(argv[3]),width,atoi(argv[5]));
    zwlr_virtual_pointer_v1_frame(pointer);wl_display_roundtrip(display);usleep(80000);
    zwlr_virtual_pointer_v1_motion_absolute(pointer,timestamp(),atoi(argv[2]),atoi(argv[3]),atoi(argv[4]),atoi(argv[5]));
    zwlr_virtual_pointer_v1_frame(pointer);wl_display_roundtrip(display);
    /* A Wayland roundtrip does not synchronize the separate Xwayland client.
     * Allow its pointer enter/focus and press/release to cross that boundary. */
    usleep(100000);
    zwlr_virtual_pointer_v1_button(pointer,timestamp(),272,1);zwlr_virtual_pointer_v1_frame(pointer);wl_display_roundtrip(display);
    usleep(80000);
    zwlr_virtual_pointer_v1_button(pointer,timestamp(),272,0);zwlr_virtual_pointer_v1_frame(pointer);wl_display_roundtrip(display);
    usleep(100000);
    zwlr_virtual_pointer_v1_destroy(pointer);zwlr_virtual_pointer_manager_v1_destroy(manager);
    for(unsigned i=0;i<count;++i)wl_output_release(outputs[i].object);
    wl_registry_destroy(registry);wl_display_flush(display);wl_display_disconnect(display);
}
