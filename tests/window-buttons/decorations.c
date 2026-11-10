/* Echo-like Wayland client: asks the compositor for its window controls.
 * Also supports X11 with/without a client-owned frame for detection tests. */
#include <GLFW/glfw3.h>
#include <gtk/gtk.h>
#include <stdio.h>
#include <string.h>

int main(int argc,char** argv){
    if(argc>1&&!strcmp(argv[1],"gtk")){
        g_set_prgname("fusion-csd-test");gtk_init(NULL,NULL);
        GtkWidget* window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
        gtk_window_set_title(GTK_WINDOW(window),"Wayland client frame");
        gtk_window_set_default_size(GTK_WINDOW(window),620,400);
        GtkWidget* header=gtk_header_bar_new();gtk_header_bar_set_title(GTK_HEADER_BAR(header),"Wayland client frame");
        gtk_header_bar_set_show_close_button(GTK_HEADER_BAR(header),TRUE);
        gtk_header_bar_set_decoration_layout(GTK_HEADER_BAR(header),":minimize,maximize,close");
        gtk_window_set_titlebar(GTK_WINDOW(window),header);
        gtk_container_add(GTK_CONTAINER(window),gtk_label_new("This app provides its own controls"));
        g_signal_connect(window,"destroy",G_CALLBACK(gtk_main_quit),NULL);
        gtk_widget_show_all(window);gtk_main();return 0;
    }
    const int x11=argc>1&&!strcmp(argv[1],"x11");
    const int own=argc>2&&!strcmp(argv[2],"client");
    glfwInitHint(GLFW_PLATFORM,x11?GLFW_PLATFORM_X11:GLFW_PLATFORM_WAYLAND);
    if(!glfwInit())return 2;
    glfwWindowHint(GLFW_DECORATED,own?GLFW_FALSE:GLFW_TRUE);
    glfwWindowHintString(GLFW_WAYLAND_APP_ID,"fusion-decoration-test");
    GLFWwindow* window=glfwCreateWindow(620,400,own?"Client frame":x11?"X11 controls":"Missing controls",NULL,NULL);
    if(!window)return 3;
    glfwMakeContextCurrent(window);glfwSwapInterval(1);
    while(!glfwWindowShouldClose(window)){
        int w,h;glfwGetFramebufferSize(window,&w,&h);glViewport(0,0,w,h);
        glClearColor(.07,.19,.25,1);glClear(GL_COLOR_BUFFER_BIT);
        glfwSwapBuffers(window);glfwWaitEventsTimeout(.04);
    }
    glfwDestroyWindow(window);glfwTerminate();return 0;
}
