/* Offline GLFW client: deliberately request the primary output from another
 * display, as native Wayland video players and games can do. No app/profile IO. */
#include <GLFW/glfw3.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static void error(int code, const char* message) {
    fprintf(stderr, "GLFW %d: %s\n", code, message);
}

int main(void) {
    glfwSetErrorCallback(error);
    glfwInitHint(GLFW_PLATFORM, GLFW_PLATFORM_WAYLAND);
    if (!glfwInit()) return 2;
    glfwWindowHintString(GLFW_WAYLAND_APP_ID, "fusion-fullscreen-test");
    GLFWwindow* window = glfwCreateWindow(500, 320, "Fullscreen regression", NULL, NULL);
    if (!window) return 3;
    glfwMakeContextCurrent(window);
    glfwSwapInterval(0);
    while (!glfwWindowShouldClose(window)) {
        struct pollfd input = {STDIN_FILENO, POLLIN, 0};
        if (poll(&input, 1, 0) > 0) {
            char command[80];
            if (!fgets(command, sizeof(command), stdin)) break;
            command[strcspn(command, "\r\n")] = 0;
            if (!strcmp(command, "fullscreen")) {
                GLFWmonitor* primary = glfwGetPrimaryMonitor();
                const GLFWvidmode* mode = glfwGetVideoMode(primary);
                glfwSetWindowMonitor(window, primary, 0, 0, mode->width, mode->height, GLFW_DONT_CARE);
            } else if (!strcmp(command, "normal")) {
                if (glfwGetWindowMonitor(window))
                    glfwSetWindowMonitor(window, NULL, 0, 0, 500, 320, GLFW_DONT_CARE);
                glfwRestoreWindow(window);
            } else if (!strcmp(command, "restore")) glfwRestoreWindow(window);
            else if (!strcmp(command, "maximize")) glfwMaximizeWindow(window);
            else if (!strcmp(command, "minimize")) glfwIconifyWindow(window);
            else if (!strcmp(command, "quit")) break;
            else return 4;
            puts("ok"); fflush(stdout);
        }
        int width, height;
        glfwGetFramebufferSize(window, &width, &height);
        glViewport(0, 0, width, height);
        glClearColor(.08f, .18f, .3f, 1);
        glClear(GL_COLOR_BUFFER_BIT);
        glfwSwapBuffers(window);
        glfwPollEvents();
        usleep(20000); /* Bound GPU work even on an unpaced headless output. */
    }
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}
