// A padded xdg window that commits only the changed pixels, like text input.
#define _GNU_SOURCE
#include <wayland-client.h>
#include "xdg-shell.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct xdg_wm_base *shell;
static struct wl_surface *surface;
static int configured, padding, scale, width, height;
static uint32_t *canvas;
struct allocation { void *pixels; size_t length; };

static void release(void *data, struct wl_buffer *buffer) {
    struct allocation *a = data;
    wl_buffer_destroy(buffer);munmap(a->pixels,a->length);free(a);
}
static const struct wl_buffer_listener buffer_listener = { .release = release };

static void commit(int x, int y, int w, int h, int buffer_damage) {
    struct allocation *a = calloc(1,sizeof(*a));
    a->length = (size_t)width*height*4;
    int fd = memfd_create("text-damage",MFD_CLOEXEC);
    if(fd<0 || ftruncate(fd,a->length))exit(2);
    a->pixels = mmap(NULL,a->length,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(a->pixels==MAP_FAILED)exit(2);
    memcpy(a->pixels,canvas,a->length);
    struct wl_shm_pool *pool = wl_shm_create_pool(shm,fd,a->length);
    struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool,0,width,height,width*4,WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool);close(fd);
    wl_buffer_add_listener(buffer,&buffer_listener,a);
    wl_surface_attach(surface,buffer,0,0);
    if(buffer_damage)wl_surface_damage_buffer(surface,x*scale,y*scale,w*scale,h*scale);
    else wl_surface_damage(surface,x,y,w,h);
    wl_surface_commit(surface);
}
static void ping(void *data, struct xdg_wm_base *base, uint32_t serial) { xdg_wm_base_pong(base,serial); }
static const struct xdg_wm_base_listener shell_listener = { .ping = ping };
static void configure(void *data, struct xdg_surface *xdg, uint32_t serial) {
    xdg_surface_ack_configure(xdg,serial);
    if(!configured){configured=1;commit(0,0,width/scale,height/scale,1);}
}
static const struct xdg_surface_listener surface_listener = { .configure = configure };
static void top_configure(void *data, struct xdg_toplevel *top, int32_t w, int32_t h, struct wl_array *states) {}
static void top_close(void *data, struct xdg_toplevel *top) { exit(0); }
static const struct xdg_toplevel_listener top_listener = { .configure=top_configure,.close=top_close };
static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version) {
    if(!strcmp(interface,"wl_compositor"))compositor=wl_registry_bind(registry,name,&wl_compositor_interface,4);
    else if(!strcmp(interface,"wl_shm"))shm=wl_registry_bind(registry,name,&wl_shm_interface,1);
    else if(!strcmp(interface,"xdg_wm_base")){
        shell=wl_registry_bind(registry,name,&xdg_wm_base_interface,1);
        xdg_wm_base_add_listener(shell,&shell_listener,NULL);
    }
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener registry_listener = { .global=global,.global_remove=removed };
int main(int argc, char **argv) {
    if(argc!=3)return 2;
    padding=atoi(argv[1]);scale=atoi(argv[2]);
    if(padding<0||padding>40||scale<1||scale>2)return 2;
    width=(400+2*padding)*scale;height=(260+2*padding)*scale;
    canvas=malloc((size_t)width*height*4);
    for(int i=0;i<width*height;++i)canvas[i]=0xff223344;
    display=wl_display_connect(NULL);if(!display)return 2;
    struct wl_registry *registry=wl_display_get_registry(display);
    wl_registry_add_listener(registry,&registry_listener,NULL);
    if(wl_display_roundtrip(display)<0||!compositor||!shm||!shell)return 2;
    surface=wl_compositor_create_surface(compositor);
    wl_surface_set_buffer_scale(surface,scale);
    struct xdg_surface *xdg=xdg_wm_base_get_xdg_surface(shell,surface);
    xdg_surface_add_listener(xdg,&surface_listener,NULL);
    struct xdg_toplevel *top=xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top,&top_listener,NULL);
    xdg_toplevel_set_app_id(top,"fusion-text-damage-fixture");
    xdg_toplevel_set_title(top,"Partial text repaint test");
    xdg_surface_set_window_geometry(xdg,padding,padding,400,260);
    wl_surface_commit(surface);
    while(!configured)if(wl_display_dispatch(display)<0)return 2;
    if(wl_display_roundtrip(display)<0)return 2;
    puts("ready");fflush(stdout);
    char line[128];int x,y,w,h,buffer_damage;unsigned color;
    // Commands are content coordinates; the protocol receives surface/buffer
    // coordinates including the invisible padding. No frame callback or full
    // damage request can accidentally repair an incorrect partial repaint.
    while(fgets(line,sizeof(line),stdin)){
        if(sscanf(line,"%d %d %d %d %x %d",&x,&y,&w,&h,&color,&buffer_damage)!=6)return 2;
        if(x<0||y<0||w<1||h<1||x+w>400||y+h>260)return 2;
        x+=padding;y+=padding;
        for(int row=y*scale;row<(y+h)*scale;++row)
            for(int col=x*scale;col<(x+w)*scale;++col)canvas[row*width+col]=0xff000000|color;
        commit(x,y,w,h,buffer_damage);
        if(wl_display_roundtrip(display)<0)return 2;
        puts("ok");fflush(stdout);
    }
    wl_display_disconnect(display);free(canvas);return 0;
}
