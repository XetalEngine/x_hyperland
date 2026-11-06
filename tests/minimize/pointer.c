/* SPDX-License-Identifier: MIT
 * Test input goes only to the disposable compositor's WAYLAND_DISPLAY. */
#include <wayland-client.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <unistd.h>
#include "virtual-pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data,struct wl_registry *registry,uint32_t name,const char *interface,uint32_t version) {
    if(!strcmp(interface,"zwlr_virtual_pointer_manager_v1"))
        manager=wl_registry_bind(registry,name,&zwlr_virtual_pointer_manager_v1_interface,1);
}
static void removed(void *data,struct wl_registry *registry,uint32_t name) {}
static const struct wl_registry_listener listener={global,removed};
int main(int argc,char **argv) {
    assert(argc==6);
    struct wl_display *display=wl_display_connect(NULL);assert(display);
    struct wl_registry *registry=wl_display_get_registry(display);
    wl_registry_add_listener(registry,&listener,NULL);wl_display_roundtrip(display);assert(manager);
    struct zwlr_virtual_pointer_v1 *pointer=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager,NULL);
    zwlr_virtual_pointer_v1_motion_absolute(pointer,1,atoi(argv[1]),atoi(argv[2]),atoi(argv[3]),atoi(argv[4]));
    zwlr_virtual_pointer_v1_frame(pointer);wl_display_roundtrip(display);
    if(!strcmp(argv[5],"click") || !strcmp(argv[5],"drag")) {
        zwlr_virtual_pointer_v1_button(pointer,2,272,1);zwlr_virtual_pointer_v1_frame(pointer);
        if(!strcmp(argv[5],"drag")) {
            wl_display_roundtrip(display);usleep(80000);
            zwlr_virtual_pointer_v1_motion_absolute(pointer,3,atoi(argv[1])+12,atoi(argv[2])+8,atoi(argv[3]),atoi(argv[4]));
            zwlr_virtual_pointer_v1_frame(pointer);wl_display_roundtrip(display);usleep(80000);
        }
        zwlr_virtual_pointer_v1_button(pointer,4,272,0);zwlr_virtual_pointer_v1_frame(pointer);
    } else if(strcmp(argv[5],"move")) {
        int direction=atoi(argv[5]);
        zwlr_virtual_pointer_v1_axis_source(pointer,WL_POINTER_AXIS_SOURCE_WHEEL);
        zwlr_virtual_pointer_v1_axis_discrete(pointer,2,WL_POINTER_AXIS_VERTICAL_SCROLL,wl_fixed_from_int(15*direction),direction);
        zwlr_virtual_pointer_v1_frame(pointer);
    }
    wl_display_roundtrip(display);
    zwlr_virtual_pointer_v1_destroy(pointer);zwlr_virtual_pointer_manager_v1_destroy(manager);
    wl_registry_destroy(registry);wl_display_flush(display);wl_display_disconnect(display);
}
