// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine. Compiz geometry/3D attribution: README.md.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/state/WorkspaceState.hpp>
#include <hyprland/src/state/MonitorState.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/KeybindManager.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/pointer/cursor/CursorManager.hpp>
#include <hyprland/src/protocols/InputCapture.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/config/ConfigValue.hpp>
#include <hyprland/src/config/shared/workspace/WorkspaceRuleManager.hpp>
#include <hyprland/src/render/gl/GLFramebuffer.hpp>
#include <hyprutils/utils/ScopeGuard.hpp>
#include "settings.hpp"
#include <linux/input-event-codes.h>
#include <fstream>
#include <filesystem>
#include <regex>
#include <chrono>
#include <map>
#include "graphics.hpp"

namespace {
using namespace Render;
using Clock = std::chrono::steady_clock;
using Cube::Color;
HANDLE handle;
Cube::Graphics graphics;
bool stopping = false, capturing = false;
std::vector<CFunctionHook *> hooks;
std::vector<CHyprSignalListener> listeners;
SP<CEventLoopTimer> timer;
SP<CEventLoopTimer> previewCleanup;
SP<SHyprCtlCommand> statusCommand;
uint64_t started = 0, finished = 0, draws = 0;
std::set<uint32_t> consumedButtons, consumedKeys;
std::string lastError;

std::filesystem::path configPath() {
    if (const char *p = std::getenv("XETAL_CUBE_CONFIG"))
        return p;
    const char *home = std::getenv("HOME");
    if (!home)
        throw std::runtime_error("No home directory for Desktop Cube");
    return std::filesystem::path(home) / ".config/hypr/effects/cube/settings.json";
}
Cube::Settings settings;
Cube::Settings readSettings() { return Cube::readSettings(configPath()); }

using RenderWorkspaceFn = void (*)(IHyprRenderer *, PHLMONITOR, PHLWORKSPACE, const Time::steady_tp &, const CBox &);
using RenderWindowFn = void (*)(IHyprRenderer *, PHLWINDOW, PHLMONITOR, const Time::steady_tp &, bool, eRenderPassMode, bool, bool);
using RenderLayerFn = void (*)(IHyprRenderer *, PHLLS, PHLMONITOR, const Time::steady_tp &, bool, bool);
using RenderBackgroundFn = void (*)(IHyprRenderer *, PHLMONITOR);
using MouseMoveFn = void (*)(CInputManager *, IPointer::SMotionEvent);
using SolitaryFn = uint32_t (*)(Monitor::CMonitor *, bool);
using ScanoutFn = bool (*)(const Monitor::CMonitor *);
using TearingFn = uint8_t (*)(Monitor::CMonitor *, bool);
RenderWorkspaceFn originalWorkspace;
RenderWindowFn renderWindow;
RenderLayerFn renderLayer;
RenderBackgroundFn renderBackground;
MouseMoveFn originalMotion;
SolitaryFn originalSolitary;
ScanoutFn originalScanout;
TearingFn originalTearing;

struct WindowImage {
    PHLWINDOWREF window;
    SP<IFramebuffer> fb;
    CBox box;
    WORKSPACEID workspace = 0;
    bool pinned = false;
};
struct Face {
    WORKSPACEID id = 0;
    PHLWORKSPACE workspace;
    std::string name;
};
struct Scene {
    PHLMONITORREF monitor;
    Vector2D pixels, position;
    float scale = 1;
    wl_output_transform transform = WL_OUTPUT_TRANSFORM_NORMAL;
    std::vector<Face> faces;
    std::vector<WindowImage> windows;
    SP<IFramebuffer> background;
    SP<IFramebuffer> canvas;
    GLuint depthBuffer = 0;
    int textureLimit = 1536;
    SP<ITexture> ceiling, floor, sky, label, help;
    int initial = 0, selection = 0, maxWindows = 0;
    double yaw = 0, pitch = 0, zoom = 1, spread = 0, fromYaw = 0, fromPitch = 0, fromZoom = 1, fromSpread = 0, targetYaw = 0;
    bool automatic = false;
    bool settling = false, commit = false, preview = false;
    uint32_t button = 0;
    Clock::time_point began = Clock::now(), settled = began, nextRefresh = began;
    uint64_t previewFrames = 0, windowCaptures = 0;
    ~Scene() {
        if (depthBuffer)
            glDeleteRenderbuffers(1, &depthBuffer);
    }
};
std::shared_ptr<Scene> scene;
struct PreviewSource {
    PHLWINDOWREF window;
    Clock::time_point expires;
};
std::vector<PreviewSource> previewSources;

bool cubeShows(PHLWINDOW window) {
    return scene && std::any_of(scene->windows.begin(), scene->windows.end(),
        [&](const auto &image) { return image.window == window; });
}
void restoreSuspension(PHLWINDOW window) {
    if (window && window->m_isMapped && !cubeShows(window))
        window->setSuspended(window->isHidden() || (!window->m_pinned &&
            (!window->m_workspace || !window->m_workspace->isVisible())));
}
void expirePreviews(bool all = false) {
    const auto now = Clock::now();
    std::erase_if(previewSources, [&](const auto &source) {
        if (!source.window)
            return true;
        if (!all && source.expires > now && !g_pSessionLockManager->isSessionLocked())
            return false;
        restoreSuspension(source.window.lock());
        return true;
    });
}

// Toplevel export already sends frame feedback, but it does not wake clients
// suspended by an inactive workspace. Wake only windows actually being copied;
// a short lease restores normal idling when capture stops or its helper exits.
void previewWindowHook(IHyprRenderer *r, PHLWINDOW window, PHLMONITOR monitor,
                       const Time::steady_tp &now, bool decorate, eRenderPassMode mode,
                       bool ignorePosition, bool standalone) {
    if (ignorePosition && standalone && window && window->m_isMapped && !window->isHidden() &&
        !g_pSessionLockManager->isSessionLocked() && window->m_workspace && !window->m_workspace->isVisible()) {
        const bool idle = previewSources.empty();
        auto found = std::find_if(previewSources.begin(), previewSources.end(),
            [&](const auto &source) { return source.window == window; });
        const auto expires = Clock::now() + std::chrono::seconds(2);
        if (found != previewSources.end())
            found->expires = expires;
        else if (previewSources.size() < 128)
            previewSources.push_back({window, expires});
        else {
            renderWindow(r, window, monitor, now, decorate, mode, ignorePosition, standalone);
            return;
        }
        window->setSuspended(false);
        if (previewCleanup && idle)
            previewCleanup->updateTimeout(std::chrono::milliseconds(250));
    }
    renderWindow(r, window, monitor, now, decorate, mode, ignorePosition, standalone);
}

std::vector<Cube::Workspace> workspaceList() {
    std::vector<Cube::Workspace> v;
    for (auto w : State::workspaceState()->workspaces())
        v.push_back({w->m_id, w->monitorID(), w->m_isSpecialWorkspace});
    return v;
}
bool active(Monitor::CMonitor *m) {
    return scene && scene->monitor.lock().get() == m;
}
bool usable(PHLMONITOR m) {
    return m && !m->isMirror() && m->m_output && m->m_pixelSize.x > 0 && m->m_pixelSize.y > 0 && m->m_activeWorkspace &&
           !m->m_activeSpecialWorkspace && !g_pSessionLockManager->isSessionLocked() && g_pCompositor->m_sessionActive;
}

#include "workspaces.hpp"

// Offscreen rendering runs outside renderMonitor, with its own framebuffer and
// projection. No workspace is made visible or focused just to obtain its image.
SP<IFramebuffer> capture(PHLMONITOR m, PHLWINDOW window = nullptr, int limit = 1536, SP<IFramebuffer> reuse = nullptr) {
    auto r = g_pHyprRenderer.get();
    auto saved = r->m_renderData;
    r->glBackend()->makeEGLCurrent();
    GLint oldRead, oldDraw, viewport[4];
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &oldRead);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &oldDraw);
    glGetIntegerv(GL_VIEWPORT, viewport);
    bool previousSnapshot = r->m_bRenderingSnapshot, previousCapture = capturing;
    Hyprutils::Utils::CScopeGuard restore([&] {
        r->m_bRenderingSnapshot = previousSnapshot;
        r->m_renderData = saved;
        capturing = previousCapture;
        glBindFramebuffer(GL_READ_FRAMEBUFFER, oldRead);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, oldDraw);
        r->setViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
    });
    auto box = window ? window->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT) : CBox{0, 0, m->m_size.x, m->m_size.y};
    const double ratio = std::min(1.0, double(limit) / std::max(box.width * m->m_scale, box.height * m->m_scale));
    int w = std::max(1, int(std::ceil(box.width * m->m_scale * ratio))), h = std::max(1, int(std::ceil(box.height * m->m_scale * ratio)));
    auto fb = reuse ? reuse : r->createFB("Xetal cube snapshot");
    if (!fb->isAllocated() || fb->m_size != Vector2D(w, h))
        fb->alloc(w, h, DRM_FORMAT_ABGR8888);
    fb->setImageDescription(m->workBufferImageDescription());
    if (!fb->isAllocated())
        throw std::runtime_error("Cannot allocate a cube preview texture");
    CRegion damage{0, 0, double(w), double(h)};
    capturing = true;
    r->beginFullFakeRender(m, damage, fb);
    r->m_bRenderingSnapshot = true;
    r->m_renderData.fbSize = {w, h};
    r->setProjectionType(RPT_EXPORT);
    r->m_renderData.transformDamage = false;
    r->setViewport(0, 0, w, h);
    r->draw(CClearPassElement::SClearData{window ? CHyprColor(0, 0, 0, 0) : CHyprColor(.035, .04, .065, 1)});
    r->m_renderData.renderModif.modifs.clear();
    r->m_renderData.renderModif.modifs.emplace_back(SRenderModifData::RMOD_TYPE_SCALE, float(ratio));
    if (window) {
        r->m_renderData.renderModif.modifs.emplace_back(SRenderModifData::RMOD_TYPE_TRANSLATE,
                                                        -window->m_floatingOffset * m->m_scale * ratio);
        renderWindow(r, window, m, Time::steadyNow(), false, RENDER_PASS_ALL, true, true);
    } else {
        renderBackground(r, m);
        for (int layer = 0; layer <= 1; layer++)
            for (auto ls : m->m_layerSurfaceLayers[layer])
                if (ls)
                    renderLayer(r, ls.lock(), m, Time::steadyNow(), false, false);
    }
    r->endRender();
    return fb;
}

SP<ITexture> artwork(const std::string &image) {
    if (image.empty())
        return nullptr;
    auto file = configPath().parent_path() / "cache" / (std::filesystem::path(image).stem().string() + ".rgba");
    std::ifstream f(file, std::ios::binary);
    if (!f)
        throw std::runtime_error("Prepare cube artwork with Apply Cube first");
    char magic[8];
    uint32_t width = 0, height = 0;
    f.read(magic, 8);
    f.read(reinterpret_cast<char *>(&width), 4);
    f.read(reinterpret_cast<char *>(&height), 4);
    if (!f || std::string(magic, 7) != "XTCUBE1" || width < 1 || height < 1 || width > 4096 || height > 2048)
        throw std::runtime_error("Invalid cube artwork");
    std::vector<uint8_t> pixels(size_t(width) * height * 4);
    f.read(reinterpret_cast<char *>(pixels.data()), pixels.size());
    if (!f || f.peek() != std::char_traits<char>::eof())
        throw std::runtime_error("Incomplete cube artwork");
    for (size_t i = 0; i < pixels.size(); i += 4)
        for (int c = 0; c < 3; c++)
            pixels[i + c] = unsigned(pixels[i + c]) * pixels[i + 3] / 255;
    return g_pHyprRenderer->createTexture(DRM_FORMAT_ABGR8888, pixels.data(), width * 4, Vector2D{double(width), double(height)});
}

void updateLabel(Scene &s) {
    int next = Cube::selected(s.yaw, s.initial, s.faces.size());
    if (next == s.selection && s.label)
        return;
    s.selection = next;
    auto m = s.monitor.lock();
    if (!m)
        return;
    std::string text = m->m_name + "  ·  " + s.faces[next].name;
    s.label = g_pHyprRenderer->renderText(text, CHyprColor(.91, .92, .95, 1), 22, false, "Inter", 1000, 600);
}

void endScene(bool choose) {
    if (!scene)
        return;
    auto old = scene;
    if (choose && old->automatic) old->selection = Cube::selected(old->targetYaw, old->initial, old->faces.size());
    auto m = old->monitor.lock();
    scene.reset();
    ++finished;
    if (m) {
        if (choose && usable(m)) {
            auto &face = old->faces[old->selection];
            auto ws = face.workspace;
            if (!ws) {
                auto used = workspaceList();
                // Reserve explicit workspace rules as well as existing workspaces.
                // A currently empty workspace assigned to another output is not free.
                for (auto &rule : Config::workspaceRuleMgr()->getAllWorkspaceRules())
                    if (rule->isEnabled() && rule->m_workspaceId > 0 && !rule->m_monitor.empty() &&
                        Config::workspaceRuleMgr()->getBoundMonitorForWS(std::to_string(rule->m_workspaceId)) != m)
                        used.push_back({rule->m_workspaceId, -1, false});
                auto id = Cube::unusedID(used);
                ws = State::workspaceState()->create(id, m->m_id);
            }
            // Workspaces moved to a different monitor during the gesture are never stolen back.
            if (valid(ws) && ws->m_monitor == m) {
                auto before = m->m_activeWorkspace;
                Desktop::focusState()->rawMonitorFocus(m);
                m->changeWorkspace(ws, false, true);
                ws->m_renderOffset->setValueAndWarp({0, 0});
                ws->m_alpha->setValueAndWarp(1.f);
                if (before && before != ws) {
                    before->m_renderOffset->warp();
                    before->m_alpha->warp();
                }
            }
        }
        m->recheckSolitary();
        g_pHyprRenderer->damageMonitor(m);
    }
    // Return temporarily visible cube sources to their ordinary suspend state.
    for (auto &image : old->windows)
        if (auto window = image.window.lock(); window &&
            std::none_of(previewSources.begin(), previewSources.end(),
                [&](const auto &source) { return source.window == window; }))
            restoreSuspension(window);
    if (timer)
        timer->updateTimeout(std::nullopt);
}

void settle(bool commit) {
    if (!scene || scene->settling)
        return;
    auto &s = *scene;
    s.settling = true;
    s.commit = commit && !s.preview;
    s.settled = Clock::now();
    s.fromYaw = s.yaw;
    s.fromPitch = s.pitch;
    s.fromZoom = s.zoom;
    s.fromSpread = s.spread;
    s.targetYaw = commit ? Cube::snap(s.yaw, s.faces.size()) : std::round(s.yaw / (2 * Cube::PI)) * 2 * Cube::PI;
    if (!commit)
        s.selection = s.initial;
}

void begin(PHLMONITOR m, uint32_t button, bool preview = false, bool automatic = false) {
    if (scene || !settings.enabled || !usable(m) || g_pInputManager->isConstrained() || (!automatic && g_pInputManager->hasHeldButtons()) ||
        PROTO::inputCapture->isCaptured())
        return;
    auto s = std::make_shared<Scene>();
    s->monitor = m;
    s->pixels = m->m_pixelSize;
    s->position = m->m_position;
    s->scale = m->m_scale;
    s->transform = m->m_transform;
    s->button = button;
    s->preview = preview;
    s->automatic = automatic;
    for (auto id : faceIDs(m)) {
        auto w = id ? State::workspaceState()->query().id(id).run() : nullptr;
        s->faces.push_back({id, w, "Workspace " + std::to_string(s->faces.size()+1)});
        if (id == m->activeWorkspaceID())
            s->initial = s->faces.size() - 1;
    }
    // A large workspace set is still supported; only window textures are
    // downsampled. There is no screenshot cache containing another monitor.
    s->background = capture(m);
    size_t windowCount = std::count_if(Desktop::windowState()->windows().begin(), Desktop::windowState()->windows().end(),
                                       [&](auto &w) { return w->m_isMapped && w->m_monitor == m && !w->isHidden(); });
    s->textureLimit = std::clamp(int(std::sqrt(64 * 1024 * 1024 / 4.0 / std::max(size_t(1), windowCount))), 64, 1536);
    for (auto w : Desktop::windowState()->windows()) {
        if (!w->m_isMapped || w->isHidden() || w->m_monitor != m || !w->m_workspace || w->m_workspace->m_isSpecialWorkspace ||
            !w->wlSurface()->resource())
            continue;
        auto box = w->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT).translate(-m->m_position);
        if (box.width < 1 || box.height < 1)
            continue;
        s->windows.push_back({w, capture(m, w, s->textureLimit), box, w->workspaceID(), w->m_pinned});
    }
    for (auto &face : s->faces) {
        int n = 0;
        for (auto &w : s->windows)
            if (w.workspace == face.id || w.pinned)
                ++n;
        s->maxWindows = std::max(s->maxWindows, n);
    }
    s->ceiling = artwork(settings.topImage);
    s->floor = artwork(settings.bottomImage);
    s->sky = artwork(settings.skyImage);
    // Depth is private to the cube framebuffer; never attach buffers to the compositor's render targets.
    s->canvas = g_pHyprRenderer->createFB("Xetal cube depth canvas");
    s->canvas->alloc(m->m_pixelSize.x, m->m_pixelSize.y, DRM_FORMAT_ABGR8888);
    {
        GLint fb, rb;
        glGetIntegerv(GL_FRAMEBUFFER_BINDING, &fb);
        glGetIntegerv(GL_RENDERBUFFER_BINDING, &rb);
        s->canvas->bind();
        glGenRenderbuffers(1, &s->depthBuffer);
        glBindRenderbuffer(GL_RENDERBUFFER, s->depthBuffer);
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, m->m_pixelSize.x, m->m_pixelSize.y);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, s->depthBuffer);
        bool complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
        glBindRenderbuffer(GL_RENDERBUFFER, rb);
        glBindFramebuffer(GL_FRAMEBUFFER, fb);
        if (!complete)
            throw std::runtime_error("Cannot allocate cube depth buffer");
    }
    s->help = g_pHyprRenderer->renderText(preview ? "Preview  ·  Esc or click to close"
                                                  : "Hold left button to rotate  ·  Release to select  ·  Esc to cancel",
                                          CHyprColor(.7, .73, .8, 1), 15, false, "Inter", 1200);
    if (preview) {
        s->yaw = .48;
        s->pitch = -.26;
    }
    s->began = Clock::now();
    updateLabel(*s);
    scene = s;
    ++started;
    lastError.clear();
    m->recheckSolitary();
    g_pHyprRenderer->damageMonitor(m);
    timer->updateTimeout(std::chrono::milliseconds(1));
}

void turn(double dx, double dy) {
    if (!scene || scene->settling)
        return;
    auto &s = *scene;
    s.yaw += dx * settings.sensitivity * Cube::PI / 180;
    s.pitch = std::clamp(s.pitch + dy * settings.sensitivity * Cube::PI / 180, -1.4, 1.4);
    updateLabel(s);
    if (auto m = s.monitor.lock())
        g_pHyprRenderer->damageMonitor(m);
}

void tick(SP<CEventLoopTimer> self, void *) {
    if (!scene)
        return;
    auto &s = *scene;
    auto m = s.monitor.lock();
    if (!usable(m) || m->m_pixelSize != s.pixels || m->m_position != s.position || m->m_scale != s.scale || m->m_transform != s.transform ||
        m->activeWorkspaceID() != s.faces[s.initial].id) {
        endScene(false);
        return;
    }
    for (auto &face : s.faces)
        if (face.workspace && (!valid(face.workspace) || face.workspace->m_monitor != m)) {
            endScene(false);
            return;
        }
    auto now = Clock::now();
    static auto animations = CConfigValue<Config::INTEGER>("animations:enabled");
    double duration = *animations ? settings.duration : 0;
    auto elapsed = std::chrono::duration<double, std::milli>(now - (s.settling ? s.settled : s.began)).count();
    double t = duration > 0 ? Cube::smooth(elapsed / duration) : 1;
    if (s.automatic) {
        s.yaw = s.targetYaw * t;
        s.zoom = 1 + (settings.zoom-1) * std::sin(Cube::PI*t);
        s.spread = std::sin(Cube::PI*t);
        updateLabel(s);
        if (t >= 1) { endScene(true); return; }
    } else if (s.settling) {
        s.yaw = s.fromYaw + (s.targetYaw - s.fromYaw) * t;
        s.pitch = s.fromPitch * (1 - t);
        s.zoom = s.fromZoom + (1 - s.fromZoom) * t;
        s.spread = s.fromSpread * (1 - t);
        if (t >= 1) {
            endScene(s.commit);
            return;
        }
    } else {
        s.zoom = 1 + (settings.zoom - 1) * t;
        s.spread = t;
    }
    // Every window receives the requested cadence. A shared round-robin budget
    // divided the old 30 FPS rate by the number of open windows. Reuse the GPU
    // textures and never advance workspaces just to keep their contents alive.
    if (now >= s.nextRefresh) {
        for (auto &w : s.windows) {
            auto window = w.window.lock();
            if (window && window->m_isMapped && !window->isHidden() && window->m_monitor == m) {
                try {
                    // Wayland clients may stop painting entirely after the
                    // compositor marks an inactive workspace as suspended.
                    window->setSuspended(false);
                    w.fb = capture(m, window, s.textureLimit, w.fb);
                    w.box = window->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT).translate(-m->m_position);
                    w.workspace = window->workspaceID();
                    ++s.windowCaptures;
                    // Snapshot rendering suppresses the ordinary surface pass.
                    // Tell video clients (including subsurfaces) to submit their
                    // next frame while the cube owns workspace rendering.
                    if (auto surface = window->wlSurface()->resource())
                        surface->breadthfirst([](SP<CWLSurfaceResource> sub, const Vector2D &, void *) {
                            sub->frame(Time::steadyNow());
                        }, nullptr);
                } catch (const std::exception &e) {
                    lastError = e.what();
                }
            } else
                w.fb.reset();
        }
        ++s.previewFrames;
        const auto period = std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(1.0 / settings.previewFps));
        s.nextRefresh += period;
        const auto completed = Clock::now();
        if (s.nextRefresh <= completed)
            s.nextRefresh = completed + period; // No catch-up storm if the GPU is saturated.
    }
    if (std::chrono::duration<double>(now - s.began).count() > 180) {
        endScene(false);
        return;
    }
    g_pHyprRenderer->damageMonitor(m);
    const auto remaining = std::chrono::duration<double, std::milli>(s.nextRefresh - Clock::now()).count();
    self->updateTimeout(std::chrono::milliseconds(std::clamp(int(std::ceil(remaining)), 1, 8)));
}

Cube::Polygon quad(Scene &s, const std::array<Cube::V3, 4> &corners, SP<ITexture> texture, Color tint, double facet = 0,
                   bool flip = false) {
    auto m = s.monitor.lock();
    double aspect = m->m_size.x / m->m_size.y;
    double camera = Cube::distance(s.faces.size()) + 1.20710678 / s.zoom * (1 + (Cube::radius(s.faces.size()) / .70710678 - 1) * s.spread);
    Cube::Polygon p;
    p.texture = texture;
    p.color = tint;
    std::array<Cube::Vertex, 4> v;
    for (int i = 0; i < 4; i++) {
        auto pos = Cube::rotate(Cube::rotate(corners[i], facet, 0), s.yaw, s.pitch);
        double d = std::max(.05, camera - pos.z);
        v[i] = {float(.5 + pos.x * 1.20710678 / d), float(.5 - pos.y * aspect * 1.20710678 / d), float(d), float(i == 1 || i == 2),
                float((i >= 2) != flip)};
        p.depth += pos.z / 4;
    }
    for (int i : {0, 1, 2, 0, 2, 3})
        p.vertices.push_back(v[i]);
    return p;
}

void drawScene(Scene &s) {
    auto m = s.monitor.lock();
    if (!m)
        return;
    Cube::GLState restore;
    GLint oldRead, oldDraw;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &oldRead);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &oldDraw);
    s.canvas->bind();
    graphics.begin(m);
    g_pHyprRenderer->glBackend()->setCapStatus(GL_SCISSOR_TEST, false);
    glDepthMask(true);
    glClearDepthf(1);
    glClear(GL_DEPTH_BUFFER_BIT);
    glDepthMask(false);
    graphics.draw(Cube::flat(0, 0, 1, 1, nullptr, {settings.top[0], settings.top[1], settings.top[2], 1}));
    glUniform1i(graphics.skyMode, settings.skyMode);
    double seconds = std::chrono::duration<double>(Clock::now() - s.began).count();
    const double skyYaw = (settings.skyMotion ? s.yaw : 0) + seconds * settings.skySpeed * Cube::PI / 180;
    const double skyPitch = settings.skyMotion ? s.pitch : 0;
    glUniform2f(graphics.skyAngles, skyYaw, skyPitch);
    glUniform1f(graphics.aspect, m->m_size.x / m->m_size.y);
    glUniform4fv(graphics.skyTop, 1, settings.top.data());
    glUniform4fv(graphics.skyBottom, 1, settings.bottom.data());
    auto sky = Cube::flat(0, 0, 1, 1, settings.skyMode == 1 ? nullptr : s.sky);
    if (s.sky && settings.skyMode == 2) {
        double screen = m->m_size.x / m->m_size.y, image = s.sky->m_size.x / s.sky->m_size.y;
        for (auto &v : sky.vertices) {
            const auto uv = Cube::pictureUV(v.u, v.v, screen, image, skyYaw, skyPitch,
                                            settings.skyMotion || settings.skySpeed != 0);
            v.u = uv.u;
            v.v = uv.v;
        }
    }
    graphics.draw(sky);
    glUniform1i(graphics.skyMode, 0);
    std::vector<Cube::Polygon> polygons;
    const int count = s.faces.size();
    double aspect = m->m_size.x / m->m_size.y;
    double base = settings.windows3d ? 1 + (Cube::baseScale(s.maxWindows, settings.minimum, settings.spacing) - 1) * s.spread : 1;
    double dist = Cube::distance(count), height = .5 / aspect;
    Color wall = {1, 1, 1, float(1 + (settings.opacity - 1) * s.spread)};
    for (int face = 0; face < count; face++) {
        double angle = (face - s.initial) * 2 * Cube::PI / count;
        auto faceQuad = [&](double x0, double y0, double x1, double y1, double scale, SP<ITexture> tex, Color color, double back = 0) {
            return quad(s,
                        {{{x0 * scale, y0 * scale, dist * scale - back},
                          {x1 * scale, y0 * scale, dist * scale - back},
                          {x1 * scale, y1 * scale, dist * scale - back},
                          {x0 * scale, y1 * scale, dist * scale - back}}},
                        tex, color, angle);
        };
        polygons.push_back(faceQuad(-.5, height, .5, -height, base, s.background->getTexture(), wall));
        int rank = 0;
        for (auto &window : s.windows) {
            if (!window.fb || (window.workspace != s.faces[face].id && !window.pinned))
                continue;
            double layer = settings.windows3d ? Cube::windowScale(rank, s.maxWindows, base) : base;
            double thick = settings.windows3d ? Cube::thickness(settings.windowDepth, s.maxWindows, base) * s.spread : 0;
            ++rank;
            auto b = window.box;
            double x0 = b.x / m->m_size.x - .5, x1 = (b.x + b.width) / m->m_size.x - .5;
            double y0 = height - b.y / m->m_size.y / aspect, y1 = height - (b.y + b.height) / m->m_size.y / aspect;
            if (thick > 0) {
                std::array<Cube::V3, 4> front = {{{x0 * layer, y0 * layer, dist * layer},
                                                  {x1 * layer, y0 * layer, dist * layer},
                                                  {x1 * layer, y1 * layer, dist * layer},
                                                  {x0 * layer, y1 * layer, dist * layer}}};
                for (int i = 0; i < 4; i++) {
                    int j = (i + 1) % 4;
                    auto a = front[i], b = front[j], c = b, d = a;
                    c.z -= thick;
                    d.z -= thick;
                    polygons.push_back(quad(s, {a, b, c, d}, nullptr, settings.windowColor, angle));
                }
            }
            auto color = Color{1, 1, 1, 1};
            auto p = faceQuad(x0, y0, x1, y1, layer, window.fb->getTexture(), color, -.0002);
            polygons.push_back(std::move(p));
        }
        // Thin edges make transparent faces legible without tinting app content.
        double e = .0014;
        auto edge = settings.edge;
        edge[3] *= s.spread * .75;
        polygons.push_back(faceQuad(-.5, height, .5, height - e, base, nullptr, edge, -.0001));
        polygons.push_back(faceQuad(-.5, -height + e, .5, -height, base, nullptr, edge, -.0001));
        polygons.push_back(faceQuad(-.5, height, -.5 + e, -height, base, nullptr, edge, -.0001));
    }
    // Polygon caps use the same radius as Compiz's cubeUpdateGeometry. UVs
    // cover the whole cap, so custom pictures work for four or more faces.
    for (int top = 0; top < 2; top++) {
        double y = (top ? height : -height) * base, rad = Cube::radius(count) * base;
        for (int i = 0; i < count; i++) {
            double a = (i - .5 - s.initial) * 2 * Cube::PI / count, b = (i + .5 - s.initial) * 2 * Cube::PI / count;
            std::array<Cube::V3, 4> q = {
                {{0, y, 0}, {rad * std::sin(a), y, rad * std::cos(a)}, {rad * std::sin(b), y, rad * std::cos(b)}, {0, y, 0}}};
            auto p = quad(s, q, top ? s.ceiling : s.floor, settings.cap, 0, false);
            if (p.texture)
                p.color = {1, 1, 1, settings.cap[3]};
            for (int j = 0; j < 6; j++) {
                int index = std::array<int, 6>{0, 1, 2, 0, 2, 3}[j];
                p.vertices[j].u = .5 + q[index].x / (2 * rad);
                p.vertices[j].v = .5 + q[index].z / (2 * rad);
            }
            polygons.push_back(std::move(p));
        }
    }
    std::stable_sort(polygons.begin(), polygons.end(), [](auto &a, auto &b) { return a.depth < b.depth; });
    // Opaque surfaces establish depth first; transparent walls blend far-to-near
    // against that depth. A window can no longer be hidden by its own cube wall.
    g_pHyprRenderer->glBackend()->setCapStatus(GL_DEPTH_TEST, true);
    glDepthFunc(GL_LEQUAL);
    glDepthMask(true);
    for (auto &p : polygons)
        if (p.color[3] >= .999f)
            graphics.draw(p);
    glDepthMask(false);
    for (auto &p : polygons)
        if (p.color[3] < .999f)
            graphics.draw(p);
    g_pHyprRenderer->glBackend()->setCapStatus(GL_DEPTH_TEST, false);
    double alpha = std::min(1.0, s.spread * 2);
    if (s.label) {
        double w = s.label->m_size.x / m->m_size.x, h = s.label->m_size.y / m->m_size.y;
        graphics.draw(Cube::flat(.5 - w / 2, .89, w, h, s.label, {1, 1, 1, float(alpha)}));
    }
    if (s.help) {
        double w = s.help->m_size.x / m->m_size.x, h = s.help->m_size.y / m->m_size.y;
        graphics.draw(Cube::flat(.5 - w / 2, .945, w, h, s.help, {1, 1, 1, float(alpha)}));
    }
    g_pHyprRenderer->glBackend()->setCapStatus(GL_SCISSOR_TEST, false);
    auto native = dynamic_cast<Render::GL::CGLFramebuffer *>(s.canvas.get());
    glBindFramebuffer(GL_READ_FRAMEBUFFER, native->getFBID());
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, oldDraw);
    glBlitFramebuffer(0, 0, m->m_pixelSize.x, m->m_pixelSize.y, 0, 0, m->m_pixelSize.x, m->m_pixelSize.y, GL_COLOR_BUFFER_BIT, GL_NEAREST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, oldRead);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, oldDraw);
    ++draws;
}

class CubePass : public IPassElement {
    std::shared_ptr<Scene> data;

  public:
    explicit CubePass(std::shared_ptr<Scene> s) : data(std::move(s)) {}
    bool needsLiveBlur() override { return false; }
    bool needsPrecomputeBlur() override { return false; }
    const char *passName() override { return "XetalCube"; }
    ePassElementType type() override { return EK_CUSTOM; }
    bool disableSimplification() override { return true; }
    std::vector<UP<IPassElement>> draw() override {
        if (!stopping && scene == data)
            drawScene(*data);
        return {};
    }
};
#include "cursors.hpp"

void workspaceHook(IHyprRenderer *r, PHLMONITOR m, PHLWORKSPACE w, const Time::steady_tp &now, const CBox &geometry) {
    if (scene && active(m.get()) && !capturing && !g_pSessionLockManager->isSessionLocked())
        r->addPassElement(makeUnique<CubePass>(scene));
    else
        originalWorkspace(r, m, w, now, geometry);
}
void motionHook(CInputManager *input, IPointer::SMotionEvent event) {
    if (scene && !scene->preview && !scene->automatic) {
        if (!scene->settling)
            turn(event.delta.x, event.delta.y);
        input->m_lastCursorMovement.reset();
        return;
    }
    originalMotion(input, event);
}
uint32_t solitaryHook(Monitor::CMonitor *m, bool full) {
    auto result = originalSolitary(m, full);
    return (active(m) || cursorVisible(State::monitorState()->query().id(m->m_id).run())) ? result | Monitor::CMonitor::SC_WORKSPACES : result;
}
bool scanoutHook(const Monitor::CMonitor *m) {
    return active(const_cast<Monitor::CMonitor *>(m)) || cursorVisible(State::monitorState()->query().id(m->m_id).run()) ? false : originalScanout(m);
}
uint8_t tearingHook(Monitor::CMonitor *m, bool full) {
    auto result = originalTearing(m, full);
    return (active(m) || cursorVisible(State::monitorState()->query().id(m->m_id).run())) ? result | Monitor::CMonitor::TC_ZOOM : result;
}

bool matchesGesture(uint32_t button) {
    uint32_t mods = g_pInputManager->getModsFromAllKBs() & ~(HL_MODIFIER_CAPS | HL_MODIFIER_MOD2);
    for (auto &b : g_pKeybindManager->m_keybinds)
        if (b->enabled && !b->release && b->handler == "event" && b->arg == "xetal-cube:rotate" &&
            b->key == "mouse:" + std::to_string(button) && (b->ignoreMods || b->modmask == mods) &&
            (b->submapUniversal || b->submap.name == g_pKeybindManager->getCurrentSubmap().name))
            return true;
    return false;
}
void buttonEvent(IPointer::SButtonEvent e, Event::SCallbackInfo &info) {
    if (e.state == WL_POINTER_BUTTON_STATE_RELEASED && consumedButtons.erase(e.button)) {
        info.cancelled = true;
        if (scene && e.button == scene->button)
            settle(true);
        return;
    }
    if (info.cancelled)
        return;
    if (scene && scene->automatic) { if (e.state == WL_POINTER_BUTTON_STATE_PRESSED) endScene(true); return; }
    if (scene) {
        info.cancelled = true;
        if (e.state == WL_POINTER_BUTTON_STATE_PRESSED) {
            consumedButtons.insert(e.button);
            if (e.button == BTN_RIGHT || scene->preview)
                settle(false);
        }
        return;
    }
    if (e.state != WL_POINTER_BUTTON_STATE_PRESSED || !settings.enabled || !matchesGesture(e.button))
        return;
    auto m = State::monitorState()->query().vec(Pointer::mgr()->position()).run();
    try {
        begin(m, e.button);
        if (scene) {
            consumedButtons.insert(e.button);
            info.cancelled = true;
        }
    } catch (const std::exception &error) {
        lastError = error.what();
        endScene(false);
    }
}

SDispatchResult switchWorkspace(std::string arg) {
    if (!settings.enabled || reconcilingFaces || stopping || arg.starts_with("special")) return ordinaryWorkspace(arg);
    if (scene) endScene(scene->automatic);
    reconcileFaces();
    auto m = State::monitorState()->query().vec(Pointer::mgr()->position()).run();
    PHLWORKSPACE target;
    if (arg.starts_with("name:")) target = State::workspaceState()->query().name(arg.substr(5)).run();
    try {
        size_t end = 0; auto id = std::stoll(arg, &end);
        if (end == arg.size()) target = State::workspaceState()->query().id(id).run();
    } catch (...) {}
    if (target && target->m_monitor) m = target->m_monitor.lock();
    if (!m || m->m_activeSpecialWorkspace) return ordinaryWorkspace(arg);
    auto ids = faceIDs(m);
    auto current = std::find(ids.begin(), ids.end(), m->activeWorkspaceID());
    if (!target) {
        if (arg == "e+1" || arg == "e-1") {
            int index = current == ids.end() ? 0 : current-ids.begin();
            target = State::workspaceState()->query().id(ids[(index+(arg=="e+1"?1:3))%4]).run();
        } else return ordinaryWorkspace(arg);
    }
    if (std::find(ids.begin(), ids.end(), target->m_id) == ids.end()) target = State::workspaceState()->query().id(ids.back()).run();
    if (!settings.rotateWorkspace || !usable(m) || target == m->m_activeWorkspace || !settings.duration)
        return ordinaryWorkspace(workspaceAddress(target));
    try {
        begin(m, 0, false, true);
        if (!scene) return ordinaryWorkspace(workspaceAddress(target));
        int index = std::find(ids.begin(), ids.end(), target->m_id)-ids.begin();
        int delta = (index-scene->initial+4)%4;
        if (delta > 2) delta -= 4;
        scene->targetYaw = -delta * Cube::PI/2;
        scene->help.reset();
        return SDispatchResult{};
    } catch (const std::exception &e) {
        lastError = e.what(); endScene(false);
        return ordinaryWorkspace(workspaceAddress(target));
    }
}
SDispatchResult localWorkspace(std::string arg) {
    std::istringstream in(arg); std::string action, number; in >> action >> number;
    bool move = action == "move";
    if (action != "switch" && !move) return {.success=false, .error="Expected switch or move and a workspace"};
    if (!settings.enabled) return move ? g_pKeybindManager->m_dispatchers["movetoworkspace"](number) : ordinaryWorkspace(number);
    if (scene) endScene(scene->automatic);
    reconcileFaces();
    auto m = State::monitorState()->query().vec(Pointer::mgr()->position()).run();
    if (!m) return {.success=false, .error="No monitor under the pointer"};
    auto ids = faceIDs(m); int index = -1;
    if (number == "e+1" || number == "e-1") {
        auto active = std::find(ids.begin(), ids.end(), m->activeWorkspaceID());
        index = ((active == ids.end() ? 0 : active-ids.begin())+(number=="e+1"?1:3))%4;
    } else if (number.size() == 1 && number[0] >= '1' && number[0] <= '4') index = number[0]-'1';
    if (index < 0 || index >= int(ids.size())) return SDispatchResult{}; // 5–0 are intentionally inactive in Cube mode.
    auto target = workspaceAddress(State::workspaceState()->query().id(ids[index]).run());
    if (move) {
        auto result = ordinaryMove(target);
        if (!result.success) return result;
    }
    return switchWorkspace(target);
}

void *find(const std::string &name, const std::string &signature) {
    for (auto &symbol : HyprlandAPI::findFunctionsByName(handle, name))
        if (symbol.demangled.find(signature) != std::string::npos)
            return symbol.address;
    throw std::runtime_error("Unsupported Desktop Cube API: " + name);
}
template <typename T> void hook(const std::string &name, const std::string &signature, const void *replacement, T &original) {
    auto h = HyprlandAPI::createFunctionHook(handle, find(name, signature), replacement);
    if (!h || !h->hook())
        throw std::runtime_error("Cannot install Desktop Cube hook: " + name);
    original = reinterpret_cast<T>(h->m_original);
    hooks.push_back(h);
}
} // namespace

APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle = h;
    stopping = false;
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Desktop Cube needs rebuilding for this Hyprland ABI");
    if (g_pHyprRenderer->type() != IHyprRenderer::RT_GL)
        throw std::runtime_error("Desktop Cube needs Hyprland's OpenGL renderer");
    settings = readSettings();
    try {
        g_pHyprRenderer->glBackend()->makeEGLCurrent();
        graphics.init();
        hook("renderWindow", "IHyprRenderer::renderWindow(", (void *)previewWindowHook, renderWindow);
        renderLayer = reinterpret_cast<RenderLayerFn>(find("renderLayer", "IHyprRenderer::renderLayer("));
        renderBackground = reinterpret_cast<RenderBackgroundFn>(find("renderBackground", "IHyprRenderer::renderBackground("));
        hook("renderWorkspace", "IHyprRenderer::renderWorkspace(", (void *)workspaceHook, originalWorkspace);
        hook("onMouseMoved", "CInputManager::onMouseMoved(", (void *)motionHook, originalMotion);
        hook("isSolitaryBlocked", "CMonitor::isSolitaryBlocked(", (void *)solitaryHook, originalSolitary);
        hook("canAttemptDirectScanoutFast", "CMonitor::canAttemptDirectScanoutFast(", (void *)scanoutHook, originalScanout);
        hook("isTearingBlocked", "CMonitor::isTearingBlocked(", (void *)tearingHook, originalTearing);
        timer = makeShared<CEventLoopTimer>(std::nullopt, tick, nullptr);
        g_pEventLoopManager->addTimer(timer);
        previewCleanup = makeShared<CEventLoopTimer>(std::nullopt, [](SP<CEventLoopTimer> self, void *) {
            expirePreviews();
            if (!previewSources.empty())
                self->updateTimeout(std::chrono::milliseconds(250));
        }, nullptr);
        g_pEventLoopManager->addTimer(previewCleanup);
        ordinaryWorkspace = g_pKeybindManager->m_dispatchers.at("workspace");
        ordinaryMove = g_pKeybindManager->m_dispatchers.at("movetoworkspacesilent");
        faceTimer = makeShared<CEventLoopTimer>(std::nullopt, [](SP<CEventLoopTimer>, void *) { reconcileFaces(); }, nullptr);
        g_pEventLoopManager->addTimer(faceTimer);
        listeners.push_back(Event::bus()->m_events.monitor.layoutChanged.listen([] { scheduleFaces(); }));
        listeners.push_back(Event::bus()->m_events.workspace.created.listen([](PHLWORKSPACEREF) { scheduleFaces(); }));
        listeners.push_back(Event::bus()->m_events.workspace.moveToMonitor.listen([](PHLWORKSPACE, PHLMONITOR) { scheduleFaces(); }));
        listeners.push_back(Event::bus()->m_events.config.reloaded.listen([] { scheduleFaces(); }));
        HyprlandAPI::addDispatcherV2(handle, "xetalcube:workspace", localWorkspace);
        g_pKeybindManager->m_dispatchers["workspace"] = switchWorkspace;
        scheduleFaces();
        cursorTimer = makeShared<CEventLoopTimer>(std::nullopt, [](SP<CEventLoopTimer> self, void *) {
            damageMarks();
            if (g_pSessionLockManager->isSessionLocked() || g_pInputManager->isConstrained() || PROTO::inputCapture->isCaptured()) { clearMarks(); return; }
            auto now=Clock::now();
            std::erase_if(cursorMarks,[&](auto &mark){ return std::chrono::duration<double,std::milli>(now-mark.born).count()>=cursorOptions.duration; });
            if (!cursorMarks.empty()) self->updateTimeout(std::chrono::milliseconds(16));
            else for(auto m:State::monitorState()->monitors())m->recheckSolitary();
        },nullptr);
        g_pEventLoopManager->addTimer(cursorTimer);
        listeners.push_back(Event::bus()->m_events.input.mouse.move.listen([](Vector2D pos, Event::SCallbackInfo &info) {
            if (!info.cancelled) addCursorMark(pos,false);
        }));
        listeners.push_back(Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent e, Event::SCallbackInfo &info) {
            if (!info.cancelled && e.state==WL_POINTER_BUTTON_STATE_PRESSED) addCursorMark(Pointer::mgr()->position(),true);
        }));
        listeners.push_back(Event::bus()->m_events.render.stage.listen([](eRenderStage stage) {
            if(stage!=RENDER_LAST_MOMENT || capturing || g_pHyprRenderer->m_bRenderingSnapshot) return;
            auto m=g_pHyprRenderer->m_renderData.pMonitor.lock();
            if(cursorVisible(m)) g_pHyprRenderer->addPassElement(makeUnique<CursorPass>(m));
        }));
        HyprlandAPI::addDispatcherV2(handle,"xetalcube:cursor",[](std::string) {
            try { reloadCursors(); return SDispatchResult{}; }
            catch(const std::exception &e) { return SDispatchResult{.success=false,.error=e.what()}; }
        });
        try { reloadCursors(); } catch(const std::exception &e) { lastError=e.what(); }
        listeners.push_back(Event::bus()->m_events.input.mouse.button.listen(buttonEvent));
        listeners.push_back(Event::bus()->m_events.input.mouse.axis.listen([](IPointer::SAxisEvent, Event::SCallbackInfo &i) {
            if (scene)
                i.cancelled = true;
        }));
        listeners.push_back(Event::bus()->m_events.input.mouse.move.listen([](Vector2D, Event::SCallbackInfo &i) {
            if (scene && !scene->preview && !scene->automatic)
                i.cancelled = true;
        }));
        listeners.push_back(Event::bus()->m_events.input.keyboard.key.listen([](IKeyboard::SKeyEvent e, Event::SCallbackInfo &i) {
            if (e.state == WL_KEYBOARD_KEY_STATE_RELEASED && consumedKeys.erase(e.keycode)) {
                i.cancelled = true;
                return;
            }
            if (!scene || i.cancelled || scene->automatic)
                return;
            if (e.keycode == KEY_ESC) {
                i.cancelled = true;
                if (e.state == WL_KEYBOARD_KEY_STATE_PRESSED) {
                    consumedKeys.insert(e.keycode);
                    settle(false);
                }
                return;
            }
            if (e.keycode == KEY_LEFTCTRL || e.keycode == KEY_RIGHTCTRL || e.keycode == KEY_LEFTALT || e.keycode == KEY_RIGHTALT ||
                e.keycode == KEY_LEFTSHIFT || e.keycode == KEY_RIGHTSHIFT || e.keycode == KEY_LEFTMETA || e.keycode == KEY_RIGHTMETA)
                return;
            if (e.state == WL_KEYBOARD_KEY_STATE_PRESSED) {
                consumedKeys.insert(e.keycode);
                i.cancelled = true;
            }
        }));
        listeners.push_back(Event::bus()->m_events.monitor.preRemoved.listen([](PHLMONITOR m) {
            if (active(m.get()))
                endScene(false);
        }));
        listeners.push_back(Event::bus()->m_events.render.preChecks.listen([](PHLMONITOR m) {
            if (!active(m.get()))
                return;
            if (!usable(m)) {
                endScene(false);
                return;
            }
            m->m_solitaryClient.reset();
        }));
        HyprlandAPI::addDispatcherV2(handle, "xetalcube:reload", [](std::string) {
            try {
                auto next = readSettings();
                endScene(false);
                settings = next;
                reconcileFaces();
                return SDispatchResult{};
            } catch (const std::exception &e) {
                return SDispatchResult{.success = false, .error = e.what()};
            }
        });
        HyprlandAPI::addDispatcherV2(handle, "xetalcube:preview", [](std::string name) {
            try {
                auto m = name.empty() ? State::monitorState()->query().vec(Pointer::mgr()->position()).run()
                                      : State::monitorState()->query().name(name).run();
                begin(m, 0, true);
                if (!scene)
                    return SDispatchResult{.success = false, .error = "Cube is disabled or this monitor is unavailable"};
                return SDispatchResult{};
            } catch (const std::exception &e) {
                lastError = e.what();
                endScene(false);
                return SDispatchResult{.success = false, .error = e.what()};
            }
        });
        HyprlandAPI::addDispatcherV2(handle, "xetalcube:turn", [](std::string args) {
            std::istringstream in(args);
            double x, y;
            if (!(in >> x >> y) || !std::isfinite(x) || !std::isfinite(y) || std::abs(x) > 3600 || std::abs(y) > 3600)
                return SDispatchResult{.success = false, .error = "Expected two bounded rotation deltas"};
            turn(x, y);
            return SDispatchResult{};
        });
        HyprlandAPI::addDispatcherV2(handle, "xetalcube:finish", [](std::string arg) {
            settle(arg == "select");
            return SDispatchResult{};
        });
        statusCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-cube", true, [](eHyprCtlOutputFormat, std::string) {
            Cube::Json root(json_object_new_object(), json_object_put);
            auto add = [&](const char *key, json_object *value) { json_object_object_add(root.get(), key, value); };
            add("enabled", json_object_new_boolean(settings.enabled));
            add("preview_fps", json_object_new_int(settings.previewFps));
            add("cursor_marks", json_object_new_int64(cursorMarks.size()));
            add("cursor_trail", json_object_new_string(cursorOptions.trail.c_str()));
            add("four_faces", json_object_new_boolean(true));
            add("workspace_animation", json_object_new_string(settings.rotateWorkspace ? "cube" : "standard"));
            add("active", json_object_new_boolean(bool(scene)));
            add("started", json_object_new_int64(started));
            add("finished", json_object_new_int64(finished));
            add("draws", json_object_new_int64(draws));
            add("error", json_object_new_string(lastError.c_str()));
            add("consumed_buttons", json_object_new_int64(consumedButtons.size()));
            add("preview_sources", json_object_new_int64(previewSources.size()));
            if (scene) {
                add("preview_frames", json_object_new_int64(scene->previewFrames));
                add("window_captures", json_object_new_int64(scene->windowCaptures));
                add("monitor", json_object_new_string(scene->monitor ? scene->monitor->m_name.c_str() : ""));
                add("selected", json_object_new_int64(scene->selection));
                add("windows", json_object_new_int64(scene->windows.size()));
                add("held_button", json_object_new_int64(scene->button));
                add("settling", json_object_new_boolean(scene->settling));
                add("yaw", json_object_new_double(scene->yaw));
                auto faces = json_object_new_array();
                add("workspaces", faces);
                for (auto &f : scene->faces)
                    json_object_array_add(faces, json_object_new_int64(f.id));
            }
            return std::string(json_object_to_json_string_ext(root.get(), JSON_C_TO_STRING_PLAIN));
        }});
    } catch (...) {
        if (ordinaryWorkspace) g_pKeybindManager->m_dispatchers["workspace"] = ordinaryWorkspace;
        if (faceTimer) { g_pEventLoopManager->removeTimer(faceTimer); faceTimer.reset(); }
    clearMarks();
    if (cursorTimer) { g_pEventLoopManager->removeTimer(cursorTimer); cursorTimer.reset(); }
        releaseFaces();
        for (auto h : hooks)
            h->unhook();
        hooks.clear();
        listeners.clear();
        if (timer)
            g_pEventLoopManager->removeTimer(timer);
        timer.reset();
        if (previewCleanup)
            g_pEventLoopManager->removeTimer(previewCleanup);
        previewCleanup.reset();
        graphics.release();
        throw;
    }
    return {"Xetal Desktop Cube", "Per-monitor cube and Compiz-style 3D windows", "XetalEngine / Compiz contributors", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() {
    stopping = true;
    if (ordinaryWorkspace) g_pKeybindManager->m_dispatchers["workspace"] = ordinaryWorkspace;
    if (faceTimer) { g_pEventLoopManager->removeTimer(faceTimer); faceTimer.reset(); }
    clearMarks();
    if (cursorTimer) { g_pEventLoopManager->removeTimer(cursorTimer); cursorTimer.reset(); }
    listeners.clear();
    releaseFaces();
    endScene(false);
    expirePreviews(true);
    if (previewCleanup) {
        g_pEventLoopManager->removeTimer(previewCleanup);
        previewCleanup.reset();
    }
    if (timer) {
        g_pEventLoopManager->removeTimer(timer);
        timer.reset();
    }
    for (auto h : hooks)
        h->unhook();
    hooks.clear();
    g_pHyprRenderer->m_renderPass.removeAllOfType("XetalCube");
    g_pHyprRenderer->m_renderPass.removeAllOfType("XetalCursorEffects");
    g_pHyprRenderer->glBackend()->makeEGLCurrent();
    graphics.release();
}
