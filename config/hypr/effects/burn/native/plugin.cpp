// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine. Compiz engine/texture attribution: README.md.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/helpers/math/Math.hpp>
#include <hyprland/src/config/ConfigValue.hpp>
#include <fstream>
#include <sstream>
#include <memory>
#include <filesystem>
#include "engine.hpp"
#include "fire_texture.hpp"

namespace {
using Clock = std::chrono::steady_clock;
HANDLE handle;
Burn::Settings settings;
CFunctionHook *snapshotHook = nullptr, *fadeoutsHook = nullptr;
CHyprSignalListener closeListener;
SP<CEventLoopTimer> timer;
SP<SHyprCtlCommand> statusCommand;
PHLWINDOWREF closing;
uint64_t started = 0, finished = 0, draws = 0;
bool stopping = false;
bool blockingScanout = false, previousScanoutBlock = false;

struct Record {
    Burn::Engine engine;
    SP<Render::IFramebuffer> snapshot;
    PHLMONITORREF monitor;
    PHLWORKSPACE workspace;
    Desktop::eFadeoutPlane plane;
    Vector2D monitorSize;
    float scale;
    Clock::time_point next;
    Record(Burn::Engine e) : engine(std::move(e)) {}
};
std::vector<std::shared_ptr<Record>> records;

// All GL calls are confined to the compositor thread and restore the state
// they touch. A private VAO prevents changing Hyprland's vertex attributes.
struct GLState {
    GLint program, vao, buffer, active, texture, srcRGB, dstRGB, srcA, dstA, eqRGB, eqA;
    GLint scissor[4];
    GLboolean blending, scissoring;
    GLState() {
        glGetIntegerv(GL_CURRENT_PROGRAM, &program); glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao);
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &buffer); glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
        glActiveTexture(GL_TEXTURE0); glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
        glGetIntegerv(GL_BLEND_SRC_RGB, &srcRGB); glGetIntegerv(GL_BLEND_DST_RGB, &dstRGB);
        glGetIntegerv(GL_BLEND_SRC_ALPHA, &srcA); glGetIntegerv(GL_BLEND_DST_ALPHA, &dstA);
        glGetIntegerv(GL_BLEND_EQUATION_RGB, &eqRGB); glGetIntegerv(GL_BLEND_EQUATION_ALPHA, &eqA);
        blending = glIsEnabled(GL_BLEND); scissoring = glIsEnabled(GL_SCISSOR_TEST);
        glGetIntegerv(GL_SCISSOR_BOX, scissor);
    }
    ~GLState() {
        glUseProgram(program); glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, buffer);
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, texture); glActiveTexture(active);
        glBlendFuncSeparate(srcRGB, dstRGB, srcA, dstA); glBlendEquationSeparate(eqRGB, eqA);
        auto gl = g_pHyprRenderer->glBackend();
        gl->setCapStatus(GL_BLEND, blending);
        // Keep Hyprland's scissor/capability caches in sync with real GL state.
        if (g_pHyprRenderer->m_renderData.pMonitor)
            gl->scissor(scissor[0], scissor[1], scissor[2], scissor[3], false);
        gl->setCapStatus(GL_SCISSOR_TEST, scissoring);
    }
};

struct Vertex { float x, y, u, v, r, g, b, a; };
struct Graphics {
    GLuint program = 0, texture = 0, vao = 0, vbo = 0;
    GLint projection = -1, alpha = -1;
    GLuint compile(GLenum type, const char* source) {
        GLuint shader = glCreateShader(type);
        glShaderSource(shader, 1, &source, nullptr); glCompileShader(shader);
        GLint ok; glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
        if (!ok) {
            char message[2048]{}; glGetShaderInfoLog(shader, sizeof(message), nullptr, message);
            glDeleteShader(shader); throw std::runtime_error(std::string("Burn shader: ") + message);
        }
        return shader;
    }
    void init() {
        g_pHyprRenderer->glBackend()->makeEGLCurrent();
        GLState restore;
        const char* vs = R"(#version 300 es
            layout(location=0) in vec2 position;
            layout(location=1) in vec2 uv;
            layout(location=2) in vec4 color;
            uniform mat3 projection;
            out vec2 texcoord; out vec4 tint;
            void main() { vec3 p=projection*vec3(position,1.0); gl_Position=vec4(p.xy,0.0,1.0); texcoord=uv; tint=color; }
        )";
        const char* fs = R"(#version 300 es
            precision highp float;
            uniform sampler2D sprite; uniform float alphaScale;
            in vec2 texcoord; in vec4 tint; out vec4 fragColor;
            void main() { fragColor=texture(sprite,texcoord)*tint; fragColor.a*=alphaScale; }
        )";
        GLuint vert = compile(GL_VERTEX_SHADER, vs), frag = 0;
        try { frag = compile(GL_FRAGMENT_SHADER, fs); }
        catch (...) { glDeleteShader(vert); throw; }
        program = glCreateProgram(); glAttachShader(program, vert); glAttachShader(program, frag);
        glLinkProgram(program); glDeleteShader(vert); glDeleteShader(frag);
        GLint ok; glGetProgramiv(program, GL_LINK_STATUS, &ok);
        if (!ok) throw std::runtime_error("Cannot link the Burn particle shader");
        glUseProgram(program);
        projection = glGetUniformLocation(program, "projection"); alpha = glGetUniformLocation(program, "alphaScale");
        glUniform1i(glGetUniformLocation(program, "sprite"), 0);
        glGenTextures(1, &texture); glBindTexture(GL_TEXTURE_2D, texture);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
        static_assert(sizeof(fireTex) == 4097); // original 4096 RGBA bytes + C string terminator
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 32, 32, 0, GL_RGBA, GL_UNSIGNED_BYTE, fireTex);
        glGenVertexArrays(1, &vao); glGenBuffers(1, &vbo);
        glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo);
        for (int n = 0; n < 3; ++n) glEnableVertexAttribArray(n);
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex), nullptr);
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)(2 * sizeof(float)));
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)(4 * sizeof(float)));
    }
    void release() {
        if (!g_pHyprRenderer || !g_pHyprRenderer->glBackend()) return;
        g_pHyprRenderer->glBackend()->makeEGLCurrent();
        GLState restore;
        if (vbo) glDeleteBuffers(1, &vbo);
        if (vao) glDeleteVertexArrays(1, &vao);
        if (texture) glDeleteTextures(1, &texture);
        if (program) glDeleteProgram(program);
        vbo = vao = texture = program = 0;
    }
    void particles(const std::vector<Burn::Particle>& particles, const Record& record, bool smoke) {
        std::vector<Vertex> vertices; vertices.reserve(particles.size() * 6);
        for (const auto& p : particles) if (p.life > 0) {
            const float w = p.width * 0.5F * (1 + p.w_mod * p.life);
            const float h = p.height * 0.5F * (1 + p.h_mod * p.life);
            const auto color = g_pHyprRenderer->getConvertedColor(CHyprColor(p.r, p.g, p.b, p.life * p.a));
            auto v = [&](float dx, float dy, float u, float uv) {
                return Vertex{float((p.x + dx) * record.scale / record.monitorSize.x),
                              float((p.y + dy) * record.scale / record.monitorSize.y), u, uv,
                              float(color.r), float(color.g), float(color.b), p.life * p.a};
            };
            auto a = v(-w, -h, 0, 0), b = v(-w, h, 0, 1), c = v(w, h, 1, 1), d = v(w, -h, 1, 0);
            vertices.insert(vertices.end(), {a,b,c,a,c,d});
        }
        if (vertices.empty()) return;
        glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(Vertex), vertices.data(), GL_STREAM_DRAW);
        auto draw = [&] {
            g_pHyprRenderer->m_renderData.damage.forEachRect([&](const auto& r) {
                g_pHyprRenderer->glBackend()->scissor(&r, g_pHyprRenderer->m_renderData.transformDamage);
                glDrawArrays(GL_TRIANGLES, 0, vertices.size());
            });
        };
        if (!smoke) {
            glUniform1f(alpha, 0.5F); glBlendFunc(GL_ZERO, GL_ONE_MINUS_SRC_ALPHA); draw();
        }
        glUniform1f(alpha, 1.F);
        glBlendFunc(GL_SRC_ALPHA, smoke ? GL_ONE_MINUS_SRC_ALPHA : GL_ONE); draw();
    }
    void draw(const Record& record) {
        GLState restore;
        glUseProgram(program); glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBindTexture(GL_TEXTURE_2D, texture);
        g_pHyprRenderer->glBackend()->setCapStatus(GL_BLEND, true); glBlendEquation(GL_FUNC_ADD);
        CBox box{0,0,record.monitorSize.x,record.monitorSize.y};
        g_pHyprRenderer->m_renderData.renderModif.applyToBox(box);
        // These vertices are monitor-local positions, not UVs in a snapshot
        // texture. targetProjection already rotates/flips those positions.
        const auto matrix = g_pHyprRenderer->projectBoxToTarget(box, HYPRUTILS_TRANSFORM_NORMAL).transpose().getMatrix();
        glUniformMatrix3fv(projection, 1, GL_FALSE, matrix.data());
        particles(record.engine.smoke, record, true); particles(record.engine.fire, record, false);
    }
} graphics;

class BurnPass : public IPassElement {
    std::shared_ptr<Record> record;
  public:
    explicit BurnPass(std::shared_ptr<Record> r) : record(std::move(r)) {}
    bool needsLiveBlur() override { return false; }
    bool needsPrecomputeBlur() override { return false; }
    const char* passName() override { return "XetalBurn"; }
    ePassElementType type() override { return EK_CUSTOM; }
    bool disableSimplification() override { return true; }
    std::vector<UP<IPassElement>> draw() override {
        if (stopping || record->monitor.expired()) return {};
        const auto r = record->engine.visible();
        if (r.w > 0 && r.h > 0) {
            CTexPassElement::SRenderData data;
            data.tex = record->snapshot->getTexture(); data.flipEndFrame = true;
            data.box = {0,0,record->monitorSize.x,record->monitorSize.y};
            data.clipRegion = CRegion{CBox{r.x,r.y,r.w,r.h}.scale(record->scale)};
            g_pHyprRenderer->draw(data, g_pHyprRenderer->m_renderData.damage);
        }
        graphics.draw(*record); ++draws;
        return {};
    }
};

Burn::Settings readSettings() {
    const char* overridePath = std::getenv("XETAL_BURN_CONFIG");
    const auto path = overridePath ? std::filesystem::path(overridePath) :
        std::filesystem::path(std::getenv("HOME")) / ".config/hypr/effects/burn/settings.conf";
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot read Burn settings: " + path.string());
    Burn::Settings s;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        const auto pos = line.find('=');
        if (pos == std::string::npos) throw std::runtime_error("Invalid Burn setting");
        const auto name = line.substr(0,pos), value = line.substr(pos+1);
        if (name == "fire_color") {
            std::istringstream in(value); unsigned n;
            for (auto& c : s.fire_color) { if (!(in >> n) || n > 65535) throw std::runtime_error("Invalid fire color"); c = n; }
            if (in >> n) throw std::runtime_error("Invalid fire color length");
            continue;
        }
        size_t used = 0; const float v = std::stof(value, &used);
        if (used != value.size() || !std::isfinite(v)) throw std::runtime_error("Invalid Burn number");
        auto number = [&](auto& target, float lo, float hi) {
            if (v < lo || v > hi || (std::is_integral_v<std::remove_reference_t<decltype(target)>> && std::floor(v) != v))
                throw std::runtime_error("Burn setting out of range: " + name);
            target = v;
        };
        if (name == "enabled") number(s.enabled,0,1);
        else if (name == "duration") number(s.duration,50,4000);
        else if (name == "time_step_intense") number(s.time_step_intense,1,400);
        else if (name == "fire_particles") number(s.fire_particles,100,10000);
        else if (name == "fire_size") number(s.fire_size,0.1,20);
        else if (name == "fire_slowdown") number(s.fire_slowdown,0.1,10);
        else if (name == "fire_life") number(s.fire_life,0.1,1);
        else if (name == "fire_direction") number(s.fire_direction,0,5);
        else if (name == "fire_constant_speed") number(s.fire_constant_speed,0,1);
        else if (name == "fire_smoke") number(s.fire_smoke,0,1);
        else if (name == "fire_mystical") number(s.fire_mystical,0,1);
        else throw std::runtime_error("Unknown Burn setting: " + name);
    }
    return s;
}

void clearRecords() {
    for (const auto& r : records) if (auto m = r->monitor.lock()) g_pHyprRenderer->damageMonitor(m);
    records.clear();
    if (blockingScanout) {
        g_pHyprRenderer->m_directScanoutBlocked = previousScanoutBlock;
        blockingScanout = false;
    }
}

using SnapshotFn = SP<Render::IFramebuffer> (*)(Render::IHyprRenderer*, PHLWINDOW);
SP<Render::IFramebuffer> snapshot(Render::IHyprRenderer* renderer, PHLWINDOW window) {
    auto fb = reinterpret_cast<SnapshotFn>(snapshotHook->m_original)(renderer, window);
    static auto animations = CConfigValue<Config::INTEGER>("animations:enabled");
    if (stopping || !settings.enabled || !*animations || !fb || closing.lock() != window || records.size() >= 8) return fb;
    closing.reset();
    auto monitor = window->m_monitor.lock();
    if (!monitor || monitor->m_mirrorOf) return fb;
    try {
        // Include the window's decorations, as Compiz's WIN_* macros do, but
        // not getFullWindowBoundingBox's whole-monitor dim-around special case.
        auto box = window->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
        box.addExtents(window->getFullWindowExtents()).translate(-monitor->m_position);
        if (box.width <= 0 || box.height <= 0) return fb;
        const auto pointer = Pointer::mgr()->position() - monitor->m_position;
        auto r = std::make_shared<Record>(Burn::Engine(settings,
            {float(box.x),float(box.y),float(box.width),float(box.height)}, pointer.x, pointer.y,
            uint32_t(Clock::now().time_since_epoch().count())));
        r->snapshot = fb; r->monitor = monitor; r->workspace = window->m_workspace;
        const bool over = window->m_isFloating && window->shouldRenderOverFullscreen() && window->m_workspace &&
            Fullscreen::controller()->hasFullscreen(window->m_workspace, true);
        r->plane = !window->m_isFloating ? Desktop::FADEOUT_PLANE_WINDOW_TILED :
            (over ? Desktop::FADEOUT_PLANE_WINDOW_OVER_FULLSCREEN : Desktop::FADEOUT_PLANE_WINDOW_FLOATING);
        r->scale = monitor->m_scale; r->monitorSize = monitor->m_transformedSize;
        r->engine.step(); r->next = Clock::now() + std::chrono::milliseconds(settings.time_step_intense);
        records.emplace_back(std::move(r)); ++started;
        if (!blockingScanout) {
            previousScanoutBlock = renderer->m_directScanoutBlocked;
            renderer->m_directScanoutBlocked = true; blockingScanout = true;
        }
        renderer->damageMonitor(monitor);
        timer->updateTimeout(std::chrono::milliseconds(1));
        return nullptr; // suppress only this close's ordinary fadeout
    } catch (const std::exception& e) {
        Log::logger->log(Log::ERR, "[Xetal Burn] {}", e.what());
        return fb; // retain Hyprland's normal close animation on failure
    }
}

using FadeoutsFn = void (*)(Render::IHyprRenderer*, PHLMONITOR, Desktop::eFadeoutPlane, PHLWORKSPACE);
void fadeouts(Render::IHyprRenderer* renderer, PHLMONITOR monitor, Desktop::eFadeoutPlane plane, PHLWORKSPACE workspace) {
    reinterpret_cast<FadeoutsFn>(fadeoutsHook->m_original)(renderer, monitor, plane, workspace);
    if (stopping || renderer->m_bRenderingSnapshot) return;
    for (const auto& r : records)
        if (r->monitor.lock() == monitor && r->plane == plane && (!r->workspace || r->workspace == workspace))
            renderer->addPassElement(makeUnique<BurnPass>(r));
}

void tick(SP<CEventLoopTimer> self, void*) {
    if (stopping) return;
    const auto now = Clock::now();
    int delay = 400;
    std::erase_if(records, [&](const auto& r) {
        auto m = r->monitor.lock();
        if (!m) return true;
        // An output mode/scale change invalidates the full-monitor snapshot.
        if (m->m_scale != r->scale || m->m_transformedSize != r->monitorSize) {
            g_pHyprRenderer->damageMonitor(m); return true;
        }
        int steps = 0;
        while (now >= r->next && !r->engine.done() && steps < 32) {
            r->engine.step(); r->next += std::chrono::milliseconds(r->engine.settings.time_step_intense); ++steps;
        }
        if (steps == 32) r->next = now + std::chrono::milliseconds(r->engine.settings.time_step_intense);
        if (steps) g_pHyprRenderer->damageMonitor(m);
        if (r->engine.done()) { ++finished; return true; }
        delay = std::min(delay, std::max(1, int(std::chrono::duration_cast<std::chrono::milliseconds>(r->next - now).count())));
        return false;
    });
    if (!records.empty()) self->updateTimeout(std::chrono::milliseconds(delay));
    else clearRecords();
}

CFunctionHook* hook(const std::string& name, const std::string& signature, const void* replacement) {
    for (const auto& match : HyprlandAPI::findFunctionsByName(handle, name)) {
        if (match.demangled.find(signature) == std::string::npos) continue;
        auto h = HyprlandAPI::createFunctionHook(handle, match.address, replacement);
        if (h && h->hook()) return h;
        throw std::runtime_error("Could not install Burn hook: " + name);
    }
    throw std::runtime_error("Unsupported Hyprland renderer: " + name);
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle = h; stopping = false;
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Xetal Burn needs rebuilding for this Hyprland ABI");
    if (g_pHyprRenderer->type() != Render::IHyprRenderer::RT_GL)
        throw std::runtime_error("Xetal Burn requires Hyprland's OpenGL renderer");
    settings = readSettings();
    try {
        graphics.init();
        timer = makeShared<CEventLoopTimer>(std::nullopt, tick, nullptr);
        g_pEventLoopManager->addTimer(timer);
        snapshotHook = hook("makeSnapshotFB", "CWindow>", (void*)snapshot);
        fadeoutsHook = hook("renderFadeouts", "IHyprRenderer::renderFadeouts(", (void*)fadeouts);
        closeListener = Event::bus()->m_events.window.close.listen([](PHLWINDOW w) { closing = w; });
        HyprlandAPI::addDispatcherV2(handle, "xetalburn:reload", [](std::string) {
            try {
                auto next = readSettings(); settings = next;
                if (!settings.enabled) clearRecords();
                return SDispatchResult{};
            } catch (const std::exception& e) { return SDispatchResult{.success=false,.error=e.what()}; }
        });
        statusCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-burn", true,
            [](eHyprCtlOutputFormat, std::string) {
                return std::format("{{\"enabled\":{},\"active\":{},\"started\":{},\"finished\":{},\"draws\":{}}}",
                    settings.enabled, records.size(), started, finished, draws);
            }});
    } catch (...) {
        if (snapshotHook) snapshotHook->unhook();
        if (fadeoutsHook) fadeoutsHook->unhook();
        if (timer) g_pEventLoopManager->removeTimer(timer);
        timer.reset();
        graphics.release(); throw;
    }
    return {"Xetal Burn", "Compiz Burn close animation", "XetalEngine / Compiz contributors", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() {
    stopping = true; closeListener.reset(); closing.reset();
    if (timer) { timer->cancel(); g_pEventLoopManager->removeTimer(timer); timer.reset(); }
    if (snapshotHook) snapshotHook->unhook();
    if (fadeoutsHook) fadeoutsHook->unhook();
    g_pHyprRenderer->m_renderPass.removeAllOfType("XetalBurn");
    clearRecords(); graphics.release();
}
