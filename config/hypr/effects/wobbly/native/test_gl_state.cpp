// SPDX-License-Identifier: GPL-2.0-or-later
// Exercise the production guard on a real, isolated software GLES context.
#include "gl_state.hpp"
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <array>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>

void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

struct Context {
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLContext context = EGL_NO_CONTEXT;
    EGLSurface surface = EGL_NO_SURFACE;
    Context() {
        display = eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, nullptr);
        require(display != EGL_NO_DISPLAY && eglInitialize(display, nullptr, nullptr), "Software EGL unavailable");
        require(eglBindAPI(EGL_OPENGL_ES_API), "Cannot select GLES");
        const EGLint attrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
            EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
        EGLConfig config{}; EGLint count = 0;
        require(eglChooseConfig(display, attrs, &config, 1, &count) && count, "No GLES config");
        const EGLint size[] = {EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE};
        surface = eglCreatePbufferSurface(display, config, size);
        const EGLint version[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
        context = eglCreateContext(display, config, EGL_NO_CONTEXT, version);
        require(surface != EGL_NO_SURFACE && context != EGL_NO_CONTEXT &&
            eglMakeCurrent(display, surface, surface, context), "Cannot create isolated GLES context");
        glViewport(0, 0, 64, 64);
    }
    ~Context() {
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        eglDestroyContext(display, context); eglDestroySurface(display, surface); eglTerminate(display);
    }
};

GLuint compile(GLenum kind, const std::string& source) {
    const auto shader = glCreateShader(kind); const char* text = source.c_str();
    glShaderSource(shader, 1, &text, nullptr); glCompileShader(shader);
    GLint ok{}; glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[2048]{}; glGetShaderInfoLog(shader, sizeof(log), nullptr, log);
        throw std::runtime_error(log);
    }
    return shader;
}

struct Shader {
    GLuint program;
    GLint rectangle;
    std::optional<std::array<float, 4>> cachedRectangle;
    explicit Shader(bool fullscreen) {
        const std::string points = R"(
            const vec2 p[6] = vec2[6](vec2(-1,-1),vec2(1,-1),vec2(1,1),
                                      vec2(-1,-1),vec2(1,1),vec2(-1,1));
        )";
        const auto vertex = compile(GL_VERTEX_SHADER, "#version 300 es\n" + points +
            (fullscreen ? "void main(){gl_Position=vec4(p[gl_VertexID],0,1);}" :
                "uniform vec4 box; void main(){gl_Position=vec4(box.xy+(p[gl_VertexID]+1.)*.5*box.zw,0,1);}"));
        const auto fragment = compile(GL_FRAGMENT_SHADER, std::string("#version 300 es\nprecision highp float; out vec4 color;\n") +
            (fullscreen ? "uniform vec4 box; void main(){color=vec4(abs(box.xyz),1);}" :
                          "void main(){color=vec4(0,1,0,1);}"));
        program = glCreateProgram(); glAttachShader(program, vertex); glAttachShader(program, fragment);
        glLinkProgram(program); glDeleteShader(vertex); glDeleteShader(fragment);
        GLint ok{}; glGetProgramiv(program, GL_LINK_STATUS, &ok); require(ok, "Cannot link test shader");
        rectangle = glGetUniformLocation(program, "box"); require(rectangle >= 0, "Missing rectangle uniform");
    }
    ~Shader() { glDeleteProgram(program); }
    void box(const std::array<float, 4>& value) {
        // CShader caches uniform values too. A write to the wrong active
        // program can therefore persist after later draws rebind this shader.
        if (cachedRectangle == value) return;
        cachedRectangle = value; glUniform4fv(rectangle, 1, value.data());
    }
};

struct Renderer {
    struct { bool pMonitor = true; } m_renderData;
    GLuint cachedProgram = 0;
    Renderer* glBackend() { return this; }
    void setCapStatus(GLenum cap, bool enabled) { if (enabled) glEnable(cap); else glDisable(cap); }
    void scissor(int x, int y, int width, int height, bool) { glScissor(x, y, width, height); }
    void use(const Shader& shader) {
        // The pinned CHyprOpenGLImpl::useShader optimization (OpenGL.cpp).
        if (cachedProgram == shader.program) return;
        glUseProgram(shader.program); cachedProgram = shader.program;
    }
    bool coherent() const {
        GLint actual{}; glGetIntegerv(GL_CURRENT_PROGRAM, &actual);
        return GLuint(actual) == cachedProgram;
    }
};

void clear() { glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT); }
std::array<unsigned char, 4> pixel(int x, int y) {
    std::array<unsigned char, 4> value{};
    glReadPixels(x, y, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, value.data()); return value;
}
bool iconOnly() {
    const auto inside = pixel(32, 32), outside = pixel(60, 60);
    return inside[1] > 250 && inside[0] == 0 && inside[2] == 0 &&
        outside[0] == 0 && outside[1] == 0 && outside[2] == 0;
}

bool captureThenIcon(Renderer& renderer, Shader& screen, Shader& surface, Wobbly::ShaderOwner owner) {
    surface.cachedRectangle.reset(); screen.cachedRectangle.reset();
    renderer.use(screen); screen.box({.2, .2, .2, 1});
    {
        Wobbly::GLState capture{renderer, owner};
        renderer.use(surface); surface.box({-1, -1, 2, 2}); glDrawArrays(GL_TRIANGLES, 0, 6);
    }
    const bool coherent = renderer.coherent();
    clear(); renderer.use(surface); surface.box({-.5, -.5, 1, 1}); glDrawArrays(GL_TRIANGLES, 0, 6);
    const bool firstFrame = iconOnly();
    // A different window briefly switches shaders; the next icon draw skips
    // the cached uniform. Old capture now draws the icon fullscreen even
    // though the program binding itself has recovered.
    renderer.use(screen); renderer.use(surface);
    clear(); surface.box({-.5, -.5, 1, 1}); glDrawArrays(GL_TRIANGLES, 0, 6);
    const bool laterFrame = iconOnly();
    require(glGetError() == GL_NO_ERROR, "Unexpected GL error during capture/icon test");
    if (owner == Wobbly::ShaderOwner::Effect) {
        require(!coherent && !firstFrame && !laterFrame, "Legacy negative control did not reproduce corruption");
        std::cout << "Legacy capture reproduced shader mismatch and persistent fullscreen icon\n";
    }
    return coherent && firstFrame && laterFrame;
}

int main() try {
    Context context;
    std::cout << "Renderer: " << glGetString(GL_RENDERER) << '\n';
    GLuint vao{}; glGenVertexArrays(1, &vao); glBindVertexArray(vao);
    Renderer renderer;
    Shader screen(true), surface(false);
    require(screen.rectangle == surface.rectangle, "Negative control requires overlapping uniform locations");
    require(!captureThenIcon(renderer, screen, surface, Wobbly::ShaderOwner::Effect), "Old capture unexpectedly passed");
    for (int i = 0; i < 100; ++i)
        require(captureThenIcon(renderer, screen, surface, Wobbly::ShaderOwner::Renderer), "Renderer capture corrupts later draws");
    // Raw mesh draws still restore their caller's binding, with no native
    // shader/cache changes in between. The two kinds of scope can nest.
    renderer.use(screen);
    {
        Wobbly::GLState capture{renderer, Wobbly::ShaderOwner::Renderer};
        renderer.use(surface);
        {
            Wobbly::GLState effect{renderer, Wobbly::ShaderOwner::Effect};
            glUseProgram(screen.program); glColorMask(false, false, false, false);
        }
        require(renderer.coherent(), "Raw effect did not restore native shader");
        GLboolean color[4]; glGetBooleanv(GL_COLOR_WRITEMASK, color);
        require(color[0] && color[1] && color[2] && color[3], "Effect leaked color mask");
    }
    require(renderer.coherent(), "Nested scopes desynchronized shader cache");
    try {
        Wobbly::GLState capture{renderer, Wobbly::ShaderOwner::Renderer};
        renderer.use(screen); throw 1;
    } catch (int) {}
    require(renderer.coherent(), "Exception cleanup desynchronized shader cache");
    require(glGetError() == GL_NO_ERROR, "GL error after state restoration");
    glDeleteVertexArrays(1, &vao);
    std::cout << "Wobbly render-state regression passed: 100 capture/icon cycles, nesting, exception cleanup\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
}
