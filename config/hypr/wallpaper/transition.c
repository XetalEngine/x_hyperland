/* A short-lived, input-transparent wallpaper transition. GTK owns Wayland;
 * the surface stays below application windows and above hyprpaper. */
#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <gtk-layer-shell.h>
#include <epoxy/gl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static GtkWidget *window, *area;
static GLuint program, vao, vbo, textures[2];
static GdkPixbuf *images[2];
static int fits[2], style, ready_frames;
static gboolean ready_sent, running, done, failed;
static gint64 started;
static double duration = 850;

static const char *vertex_source =
    "#version 330 core\n"
    "layout(location=0) in vec2 pos; out vec2 uv;"
    "void main(){uv=vec2(pos.x*.5+.5,.5-pos.y*.5);gl_Position=vec4(pos,0,1);}";
static const char *fragment_source =
    "#version 330 core\n"
    "in vec2 uv;out vec4 frag;uniform sampler2D beforeImage,afterImage;"
    "uniform vec2 screenSize,beforeSize,afterSize;uniform int beforeFit,afterFit,effect;uniform float progress;"
    "float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}"
    "float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);"
    "return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}"
    "vec4 picture(sampler2D tex,vec2 size,int fit,vec2 q){"
    "if(fit==3)return texture(tex,fract(q*screenSize/size));"
    "if(fit!=2){float factor=fit==1?min(screenSize.x/size.x,screenSize.y/size.y):max(screenSize.x/size.x,screenSize.y/size.y);"
    "q=(q-.5)*screenSize/(size*factor)+.5;}"
    "if(any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1))))return vec4(0,0,0,1);return texture(tex,q);}"
    "void main(){float t=clamp(progress,0.,1.),p=t*t*(3.-2.*t);float a=p,shade=0.;vec2 q=uv,r=uv;"
    "if(effect==1){vec2 d=(uv-.5)*vec2(screenSize.x/screenSize.y,1);"
    "float radius=length(d)/length(vec2(screenSize.x/screenSize.y,1)*.5);"
    "float field=radius*.90+noise(uv*11.)*.07+noise(uv*27.)*.03;"
    "a=1.-smoothstep(p*1.18-.13,p*1.18+.03,field);"
    "q+=normalize(d+vec2(.0001))*sin(radius*32.-p*9.)*.004*sin(t*3.14159)*(1.-a)*smoothstep(0.,.05,min(min(uv.x,1.-uv.x),min(uv.y,1.-uv.y)));"
    "}else if(effect==2){float field=uv.x*.8+uv.y*.2+.025*sin(uv.y*8.+p*4.);"
    "a=1.-smoothstep(p*1.25-.15,p*1.25+.08,field);"
    "}else if(effect==3){vec2 aspect=vec2(screenSize.x/screenSize.y,1.),d=(uv-.5)*aspect;"
    "float radius=length(d)/length(aspect*.5),delta=radius-(p*1.2-.1);"
    "float ring=exp(-delta*delta*110.),wave=sin(delta*48.)*ring*.022*sin(t*3.14159);"
    "float border=smoothstep(0.,.08,min(min(uv.x,1.-uv.x),min(uv.y,1.-uv.y)));"
    "vec2 bend=normalize(d+vec2(.0001))/aspect*wave*border;"
    "q+=bend;r-=bend*.65;a=1.-smoothstep(-.07,.07,delta);"
    "}else if(effect==4){vec2 d=(uv-.5)*vec2(screenSize.x/screenSize.y,1.);"
    "float radius=length(d)/length(vec2(screenSize.x/screenSize.y,1.)*.5);"
    "float angle=atan(d.y+.00001,d.x+.00001)+p*.55,blade=cos(mod(angle+0.523599,1.047198)-0.523599);"
    "a=1.-smoothstep(p*1.2-.09,p*1.2-.045,radius*blade);"
    "q=(uv-.5)*(1.-.06*p)+.5;r=(uv-.5)*(.92+.08*p)+.5;"
    "shade=.15*sin(t*3.14159)*a*(1.-a);"
    "}else if(effect==5){float edge=1.-p;"
    "a=smoothstep(edge-.012,edge+.012,uv.x);q.x+=p*.18;r.x=clamp(uv.x-edge,0.,1.);"
    "shade=.16*sin(t*3.14159)*exp(-abs(uv.x-edge)*24.)*(1.-a);}"
    "if(t<=0.)a=0.;if(t>=1.)a=1.;"
    "vec4 b=picture(beforeImage,beforeSize,beforeFit,q),c=picture(afterImage,afterSize,afterFit,r);"
    "frag=vec4(mix(b.rgb,c.rgb,a)*(1.-shade),1.);}";

static GLuint shader(GLenum kind, const char *source) {
    GLuint s = glCreateShader(kind); glShaderSource(s, 1, &source, NULL); glCompileShader(s);
    GLint ok; glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) { char error[2048]; glGetShaderInfoLog(s, sizeof(error), NULL, error); fprintf(stderr, "%s\n", error); failed = TRUE; }
    return s;
}

static void realize(GtkGLArea *gl, gpointer unused) {
    (void)unused; gtk_gl_area_make_current(gl);
    if (gtk_gl_area_get_error(gl)) { failed = TRUE; return; }
    GLuint vert = shader(GL_VERTEX_SHADER, vertex_source), frag = shader(GL_FRAGMENT_SHADER, fragment_source);
    program = glCreateProgram(); glAttachShader(program, vert); glAttachShader(program, frag); glLinkProgram(program);
    GLint ok; glGetProgramiv(program, GL_LINK_STATUS, &ok); if (!ok) failed = TRUE;
    glDeleteShader(vert); glDeleteShader(frag);
    const GLfloat points[] = {-1,-1, 1,-1, -1,1, -1,1, 1,-1, 1,1};
    glGenVertexArrays(1, &vao); glBindVertexArray(vao); glGenBuffers(1, &vbo); glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(points), points, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL); glEnableVertexAttribArray(0);
    glGenTextures(2, textures);
    for (int i=0; i<2; ++i) {
        glBindTexture(GL_TEXTURE_2D, textures[i]); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, gdk_pixbuf_get_width(images[i]), gdk_pixbuf_get_height(images[i]), 0,
                    gdk_pixbuf_get_has_alpha(images[i]) ? GL_RGBA : GL_RGB, GL_UNSIGNED_BYTE, gdk_pixbuf_get_pixels(images[i]));
    }
}

static gboolean rendered(GtkGLArea *gl, GdkGLContext *context, gpointer unused) {
    (void)context; (void)unused;
    if (failed || gtk_gl_area_get_error(gl)) { failed = TRUE; gtk_main_quit(); return TRUE; }
    int width = gtk_widget_get_allocated_width(GTK_WIDGET(gl)), height = gtk_widget_get_allocated_height(GTK_WIDGET(gl));
    int scale = gtk_widget_get_scale_factor(GTK_WIDGET(gl));
    glViewport(0,0,width*scale,height*scale); glDisable(GL_BLEND); glUseProgram(program); glBindVertexArray(vao);
    double t = running ? (g_get_monotonic_time()-started)/(duration*1000) : 0;
    glUniform1f(glGetUniformLocation(program, "progress"), (GLfloat)t);
    glUniform1i(glGetUniformLocation(program, "effect"), style);
    glUniform2f(glGetUniformLocation(program, "screenSize"), width*scale, height*scale);
    for (int i=0; i<2; ++i) {
        glActiveTexture(GL_TEXTURE0+i); glBindTexture(GL_TEXTURE_2D, textures[i]);
        glUniform1i(glGetUniformLocation(program, i ? "afterImage" : "beforeImage"), i);
        glUniform1i(glGetUniformLocation(program, i ? "afterFit" : "beforeFit"), fits[i]);
        glUniform2f(glGetUniformLocation(program, i ? "afterSize" : "beforeSize"), gdk_pixbuf_get_width(images[i]), gdk_pixbuf_get_height(images[i]));
    }
    glDrawArrays(GL_TRIANGLES, 0, 6);
    if (!ready_sent && ++ready_frames>=2) { ready_sent=TRUE; puts("READY"); fflush(stdout); }
    if (t>=1 && !done) { done=TRUE; puts("DONE"); fflush(stdout); }
    return TRUE;
}

static gboolean tick(GtkWidget *widget, GdkFrameClock *clock, gpointer unused) {
    (void)clock; (void)unused;
    if (!ready_sent || (running && !done)) gtk_gl_area_queue_render(GTK_GL_AREA(widget));
    return G_SOURCE_CONTINUE;
}

static gboolean input(GIOChannel *channel, GIOCondition condition, gpointer unused) {
    (void)unused;
    if (condition & (G_IO_HUP | G_IO_ERR)) { gtk_main_quit(); return G_SOURCE_REMOVE; }
    gchar *line=NULL; gsize size=0;
    GIOStatus result = g_io_channel_read_line(channel, &line, &size, NULL, NULL);
    if (result == G_IO_STATUS_EOF) { gtk_main_quit(); return G_SOURCE_REMOVE; }
    if (line && strcmp(line,"GO\n")==0 && !running) { running=TRUE; started=g_get_monotonic_time(); }
    if (line && strcmp(line,"CLOSE\n")==0) gtk_main_quit();
    g_free(line); return G_SOURCE_CONTINUE;
}

static void transparent_input(GtkWidget *widget, gpointer unused) {
    (void)unused;
    cairo_region_t *region=cairo_region_create(); gdk_window_input_shape_combine_region(gtk_widget_get_window(widget),region,0,0); cairo_region_destroy(region);
}

static gboolean deadline(gpointer unused) { (void)unused; gtk_main_quit(); return G_SOURCE_REMOVE; }
static void monitor_removed(GdkDisplay *display, GdkMonitor *monitor, gpointer selected) {
    (void)display; if (monitor==selected) gtk_main_quit();
}

int main(int argc, char **argv) {
    /* x y logical-width logical-height old-path old-fit new-path new-fit effect */
    if (argc!=10) return 2;
    int x=atoi(argv[1]), y=atoi(argv[2]), width=atoi(argv[3]), height=atoi(argv[4]);
    if (!gtk_init_check(&argc, &argv) || !gtk_layer_is_supported()) return 3;
    GdkDisplay *display=gdk_display_get_default(); GdkMonitor *selected=NULL;
    for (int i=0; i<gdk_display_get_n_monitors(display); ++i) {
        GdkMonitor *monitor=gdk_display_get_monitor(display,i); GdkRectangle rect; gdk_monitor_get_geometry(monitor,&rect);
        if (rect.x==x && rect.y==y && abs(rect.width-width)<=2 && abs(rect.height-height)<=2) { selected=monitor; break; }
    }
    if (!selected) { fputs("Output layout changed\n",stderr); return 4; }
    for (int i=0; i<2; ++i) {
        int image_width=4096,image_height=4096; gdk_pixbuf_get_file_info(argv[5+i*2],&image_width,&image_height);
        GError *error=NULL; GdkPixbuf *loaded=gdk_pixbuf_new_from_file_at_scale(argv[5+i*2], MIN(4096,MAX(1,image_width)), MIN(4096,MAX(1,image_height)), TRUE, &error);
        if (loaded) { images[i]=gdk_pixbuf_apply_embedded_orientation(loaded); g_object_unref(loaded); }
        else if (!i) { images[i]=gdk_pixbuf_new(GDK_COLORSPACE_RGB, FALSE, 8, 1, 1); gdk_pixbuf_fill(images[i],0x000000ff); }
        if (error) g_error_free(error);
        if (!images[i]) return 5;
        const char *fit=argv[6+i*2]; fits[i]=!strcmp(fit,"contain")?1:!strcmp(fit,"fill")?2:!strcmp(fit,"tile")?3:0;
    }
    style=!strcmp(argv[9],"bloom")?1:!strcmp(argv[9],"sweep")?2:!strcmp(argv[9],"ripple")?3:
          !strcmp(argv[9],"iris")?4:!strcmp(argv[9],"glide")?5:0;
    window=gtk_window_new(GTK_WINDOW_TOPLEVEL); gtk_widget_set_app_paintable(window,TRUE);
    gtk_layer_init_for_window(GTK_WINDOW(window)); gtk_layer_set_namespace(GTK_WINDOW(window),"xetal-wallpaper-transition");
    gtk_layer_set_layer(GTK_WINDOW(window),GTK_LAYER_SHELL_LAYER_BOTTOM); gtk_layer_set_monitor(GTK_WINDOW(window),selected);
    gtk_layer_set_exclusive_zone(GTK_WINDOW(window),-1); gtk_layer_set_keyboard_mode(GTK_WINDOW(window),GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
    for (int edge=0; edge<GTK_LAYER_SHELL_EDGE_ENTRY_NUMBER; ++edge) gtk_layer_set_anchor(GTK_WINDOW(window),edge,TRUE);
    g_signal_connect(window,"realize",G_CALLBACK(transparent_input),NULL);
    g_signal_connect(display,"monitor-removed",G_CALLBACK(monitor_removed),selected);
    area=gtk_gl_area_new(); gtk_gl_area_set_required_version(GTK_GL_AREA(area),3,3); gtk_gl_area_set_auto_render(GTK_GL_AREA(area),FALSE);
    g_signal_connect(area,"realize",G_CALLBACK(realize),NULL); g_signal_connect(area,"render",G_CALLBACK(rendered),NULL);
    gtk_container_add(GTK_CONTAINER(window),area); gtk_widget_add_tick_callback(area,tick,NULL,NULL);
    GIOChannel *channel=g_io_channel_unix_new(STDIN_FILENO); g_io_channel_set_flags(channel,G_IO_FLAG_NONBLOCK,NULL);
    g_io_add_watch(channel,G_IO_IN|G_IO_HUP|G_IO_ERR,input,NULL); g_timeout_add_seconds(15,deadline,NULL);
    gtk_widget_show_all(window); gtk_main();
    gtk_widget_destroy(window); g_io_channel_unref(channel);
    for (int i=0;i<2;++i) g_object_unref(images[i]);
    return failed ? 6 : 0;
}
