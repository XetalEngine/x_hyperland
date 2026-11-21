/* Isolated Echo-shaped ARGB/XFixes fixture. No Echo process or profile is used. */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xatom.h>
#include <X11/extensions/Xfixes.h>
#include <X11/extensions/Xrender.h>
#include <X11/extensions/shape.h>
#include <assert.h>
#include <stdio.h>

int main(void) {
    Display *d = XOpenDisplay(NULL); assert(d);
    XVisualInfo wanted = {.screen=DefaultScreen(d), .depth=32, .class=TrueColor};
    int count=0; XVisualInfo *visuals=XGetVisualInfo(d, VisualScreenMask|VisualDepthMask|VisualClassMask, &wanted, &count);
    Visual *visual=NULL;
    for(int i=0;i<count;++i) {
        XRenderPictFormat *f=XRenderFindVisualFormat(d,visuals[i].visual);
        if(f && f->type==PictTypeDirect && f->direct.alphaMask) { visual=visuals[i].visual; break; }
    }
    assert(visual); XFree(visuals);
    Colormap map=XCreateColormap(d,DefaultRootWindow(d),visual,AllocNone);
    XSetWindowAttributes a={.override_redirect=True, .colormap=map, .background_pixel=0, .border_pixel=0, .event_mask=ExposureMask};
    Window window=XCreateWindow(d,DefaultRootWindow(d),0,0,1024,768,0,32,InputOutput,visual,
        CWOverrideRedirect|CWColormap|CWBackPixel|CWBorderPixel|CWEventMask,&a);
    XStoreName(d,window,"Echo Overlay");
    XWMHints hints={.flags=InputHint,.input=False}; XSetWMHints(d,window,&hints);
    XserverRegion empty=XFixesCreateRegion(d,NULL,0);
    XFixesSetWindowShapeRegion(d,window,ShapeInput,0,0,empty); XFixesDestroyRegion(d,empty);
    Atom states[]={XInternAtom(d,"_NET_WM_STATE_ABOVE",False),XInternAtom(d,"_NET_WM_STATE_SKIP_TASKBAR",False),XInternAtom(d,"_NET_WM_STATE_SKIP_PAGER",False)};
    XChangeProperty(d,window,XInternAtom(d,"_NET_WM_STATE",False),XA_ATOM,32,PropModeReplace,(unsigned char*)states,3);
    unsigned long bypass=2;
    XChangeProperty(d,window,XInternAtom(d,"_NET_WM_BYPASS_COMPOSITOR",False),XA_CARDINAL,32,PropModeReplace,(unsigned char*)&bypass,1);
    XMapRaised(d,window); XFlush(d);
    GC gc=XCreateGC(d,window,0,NULL);
    printf("%lu\n",window); fflush(stdout);
    for(;;) {
        XEvent event; XNextEvent(d,&event);
        if(event.type!=Expose)continue;
        XSetForeground(d,gc,0); XFillRectangle(d,window,gc,0,0,1024,768);
        XSetForeground(d,gc,0xffff4030); XFillRectangle(d,window,gc,24,24,150,60); XFlush(d);
    }
}
