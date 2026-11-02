/* SPDX-License-Identifier: MIT
 * Test input is sent only to the disposable compositor's WAYLAND_DISPLAY. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "virtual-pointer.h"
#include "virtual-keyboard.h"
#include "system-bell.h"
static struct zwlr_virtual_pointer_manager_v1 *pm;
static struct zwp_virtual_keyboard_manager_v1 *km;
static struct wl_seat *seat;
static struct xdg_system_bell_v1 *bell;
static void global(void *data,struct wl_registry *registry,uint32_t name,const char *interface,uint32_t version) {
    if(!strcmp(interface,"zwlr_virtual_pointer_manager_v1"))pm=wl_registry_bind(registry,name,&zwlr_virtual_pointer_manager_v1_interface,1);
    if(!strcmp(interface,"zwp_virtual_keyboard_manager_v1"))km=wl_registry_bind(registry,name,&zwp_virtual_keyboard_manager_v1_interface,1);
    if(!strcmp(interface,"xdg_system_bell_v1"))bell=wl_registry_bind(registry,name,&xdg_system_bell_v1_interface,1);
    if(!strcmp(interface,"wl_seat"))seat=wl_registry_bind(registry,name,&wl_seat_interface,1);
}
static void removed(void *data,struct wl_registry *registry,uint32_t name) {}
static const struct wl_registry_listener listener={global,removed};
int main(int argc,char **argv) {
    assert(argc==3);int width=atoi(argv[1]),height=atoi(argv[2]);
    struct wl_display *d=wl_display_connect(NULL);assert(d);
    struct wl_registry *r=wl_display_get_registry(d);wl_registry_add_listener(r,&listener,NULL);wl_display_roundtrip(d);
    assert(pm && km && seat);
    struct zwlr_virtual_pointer_v1 *p=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(pm,seat);
    struct zwp_virtual_keyboard_v1 *k=zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(km,seat);
    struct xkb_context *context=xkb_context_new(0);struct xkb_keymap *map=xkb_keymap_new_from_names(context,NULL,0);
    struct xkb_state *state=xkb_state_new(map);char *keymap=xkb_keymap_get_as_string(map,XKB_KEYMAP_FORMAT_TEXT_V1);
    int fd=memfd_create("fusion-test-keymap",0);assert(fd>=0);size_t len=strlen(keymap)+1;assert(write(fd,keymap,len)==len);
    zwp_virtual_keyboard_v1_keymap(k,WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1,fd,len);close(fd);free(keymap);wl_display_roundtrip(d);
    char line[100],command[20];int a,b;unsigned serial=1;
    while(fgets(line,sizeof(line),stdin)) {
        a=b=0;sscanf(line,"%19s %d %d",command,&a,&b);
        if(!strcmp(command,"move"))zwlr_virtual_pointer_v1_motion_absolute(p,serial++,a,b,width,height);
        else if(!strcmp(command,"down"))zwlr_virtual_pointer_v1_button(p,serial++,a,1);
        else if(!strcmp(command,"up"))zwlr_virtual_pointer_v1_button(p,serial++,a,0);
        else if(!strcmp(command,"bell")){assert(bell);xdg_system_bell_v1_ring(bell,NULL);}
        else if(!strcmp(command,"key")) {
            xkb_state_update_key(state,a+8,b?XKB_KEY_DOWN:XKB_KEY_UP);
            zwp_virtual_keyboard_v1_key(k,serial++,a,b);
            zwp_virtual_keyboard_v1_modifiers(k,xkb_state_serialize_mods(state,XKB_STATE_MODS_DEPRESSED),
                xkb_state_serialize_mods(state,XKB_STATE_MODS_LATCHED),xkb_state_serialize_mods(state,XKB_STATE_MODS_LOCKED),0);
        } else if(!strcmp(command,"quit"))break;
        zwlr_virtual_pointer_v1_frame(p);wl_display_roundtrip(d);puts("ok");fflush(stdout);
    }
    xkb_state_unref(state);xkb_keymap_unref(map);xkb_context_unref(context);
    zwp_virtual_keyboard_v1_destroy(k);zwlr_virtual_pointer_v1_destroy(p);wl_display_flush(d);wl_display_disconnect(d);
}
