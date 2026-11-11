// SPDX-License-Identifier: GPL-2.0-or-later
// Cursor metadata and native movement for the text-safe floating-title grip.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/managers/SeatManager.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/protocols/core/DataDevice.hpp>
#include <hyprland/src/protocols/core/Seat.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/layout/LayoutManager.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <sstream>
#include <drm_fourcc.h>
#include <linux/input-event-codes.h>
#include "drag_actions.hpp"
#include "../window_types_native.hpp"

namespace {
SP<SHyprCtlCommand> command;
SP<SHyprCtlCommand> fileDragCommand;
CHyprSignalListener buttonListener;
bool down = false;
uint64_t serial = 0;
std::string press = "{}";
std::string origin = "null";
PHLWINDOWREF pressedWindow;
Vector2D pressedPosition;
CBox pressedBox;
PHLWINDOWREF grip;
void endGrip() {
    auto target=g_layoutManager->dragController()->target();
    if(auto w=grip.lock();w&&target&&target->window()==w)g_layoutManager->dragController()->dragEnd();
    grip.reset();
}

std::string cursor() {
    const auto& data = g_pHyprRenderer->m_lastCursorData;
    // Never expose client-provided strings in JSON or mistake an unknown
    // shape for an ordinary arrow. This also leaves resize/link cursors alone.
    // A compositor-owned border has no client surface focus. Its named arrow
    // is still known; the press hit test below limits eligibility to a window.
    if (PROTO::data->dndActive())
        return "{\"kind\":\"unknown\"}";
    if (!data.name.empty()) {
        if (data.name == "default" || data.name == "left_ptr" || data.name == "arrow")
            return "{\"kind\":\"arrow\"}";
        if (data.name == "text" || data.name == "vertical-text" || data.name == "xterm")
            return "{\"kind\":\"text\"}";
        return "{\"kind\":\"other\"}";
    }
    const auto surface = Pointer::mgr()->currentCursorImage().surface.lock();
    const auto resource = surface ? surface->resource() : nullptr;
    if (!resource || !resource->m_role || resource->m_role->role() != SURFACE_ROLE_CURSOR)
        return "{\"kind\":\"unknown\",\"reason\":\"no-cursor-surface\"}";
    const auto& state = resource->m_current;
    // No GPU reads, window pixels, screenshots, or application text. Legacy
    // clients' small SHM cursor images are compared with installed arrows.
    // The pinned GL renderer can leave the texture format unset (0), as its
    // own CPU cursor path handles. Exact artwork matching still must succeed.
    if (!state.texture || state.texture->isDMA() ||
        (state.texture->m_drmFormat && state.texture->m_drmFormat != DRM_FORMAT_ARGB8888))
        return std::format("{{\"kind\":\"unknown\",\"reason\":\"cursor-format\",\"format\":{}}}", state.texture ? state.texture->m_drmFormat : 0);
    const int width = state.bufferSize.x, height = state.bufferSize.y;
    if (width < 1 || height < 1 || width > 256 || height > 256)
        return "{\"kind\":\"unknown\",\"reason\":\"cursor-size\"}";
    // SHM wl_buffers are released after upload; use the compositor's existing
    // cursor-only CPU copy rather than retaining or rereading client mappings.
    const auto& pixels = CCursorSurfaceRole::cursorPixelData(resource);
    if (pixels.size() < size_t(width * height * 4) || pixels.size() % height)
        return "{\"kind\":\"unknown\",\"reason\":\"no-cursor-pixels\"}";
    const size_t stride = pixels.size() / height;
    uint64_t hash = 14695981039346656037ULL;
    for (int y = 0; y < height; ++y)
        for (int x = 0; x < width * 4; ++x) {
            hash ^= pixels[y * stride + x];
            hash *= 1099511628211ULL;
        }
    return std::format("{{\"kind\":\"bitmap\",\"width\":{},\"height\":{},\"hash\":\"{:016x}\"}}", width, height, hash);
}

void captureOrigin() {
    origin = "null";
    pressedWindow.reset();
    pressedPosition = Pointer::mgr()->position();
    const auto focus = g_pSeatManager->m_state.pointerFocus.lock();
    const auto focusedSurface = focus ? Desktop::View::CWLSurface::fromResource(focus) : nullptr;
    const auto focusedView = focusedSurface ? focusedSurface->view() : nullptr;
    if (focusedView && focusedView->type() == Desktop::View::VIEW_TYPE_POPUP) return;
    const auto focusedWindow = focusedView ? Desktop::View::CWindow::fromView(focusedView) : nullptr;
    if (focusedWindow && !WindowTypes::geometryManaged(focusedWindow)) return;
    // Reserved extents include the actual per-window border, without shadows.
    auto w = Desktop::viewState()->hitTest().windowAt(pressedPosition,
        Desktop::View::ALLOW_FLOATING | Desktop::View::RESERVED_EXTENTS);
    if (!w || !WindowTypes::geometryManaged(w) || w->hasPopupAt(pressedPosition)) return;
    auto monitor = w->m_monitor.lock();
    if (!monitor) return;
    Vector2D local; PHLLS layer;
    for (int level : {3, 2})
        if (Desktop::viewState()->hitTest().layerSurfaceAt(pressedPosition, &monitor->m_layerSurfaceLayers[level], &local, &layer)) return;
    if (Desktop::viewState()->hitTest().layerPopupSurfaceAt(pressedPosition, monitor, &local, &layer)) return;
    pressedWindow = w;
    pressedBox = w->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
    origin = std::format("{{\"x\":{},\"y\":{},\"address\":\"0x{:x}\",\"stableId\":\"{:x}\",\"border\":{}}}",
        pressedPosition.x, pressedPosition.y, reinterpret_cast<uintptr_t>(w.get()), w->m_stableID, w->getRealBorderSize());
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Rebuild cursor probe for this compositor ABI");
    FileDragActions::start(g_pCompositor->m_wlDisplay);
    fileDragCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-file-drag", true, [](eHyprCtlOutputFormat, std::string) {
        const auto mods = g_pInputManager->getModsFromAllKBs();
        const bool active = FileDragActions::source.value && PROTO::data->dndActive();
        const auto action = active ? FileDragActions::last : 0;
        const auto name = action == 1 ? ((mods & 4) && (mods & 1) ? "link" : "copy") : action == 2 ? "move" : "none";
        return std::format("{{\"active\":{},\"action\":\"{}\"}}", active, name);
    }});
    buttonListener = Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent event, Event::SCallbackInfo& info) {
        if (event.button != BTN_LEFT) return;
        down = event.state == WL_POINTER_BUTTON_STATE_PRESSED && !info.cancelled;
        if (down) { ++serial; press = cursor(); captureOrigin(); }
        else { endGrip(); pressedWindow.reset(); origin = "null"; }
    });
    HyprlandAPI::addDispatcherV2(handle,"xetaldrag:begin",[](std::string args) {
        std::istringstream input(args);std::string address,extra;uint64_t token=0;
        if(!(input>>address>>token)||(input>>extra)||!down||token!=serial||
           !g_pCompositor->m_sessionActive||g_pSessionLockManager->isSessionLocked()||
           PROTO::data->dndActive()||g_layoutManager->dragController()->target())
            return SDispatchResult{.success=false,.error="The title grip is no longer available"};
        for(auto& w:Desktop::windowState()->windows()) {
            if(std::format("0x{:x}",reinterpret_cast<uintptr_t>(w.get()))!=address)continue;
            if(w!=pressedWindow.lock()||!w->m_isMapped||!WindowTypes::geometryManaged(w)||w->isHidden()||!w->m_isFloating||!w->m_workspace||
               w->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT)!=pressedBox||
               Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_NONE)
                return SDispatchResult{.success=false,.error="The window cannot be dragged"};
            // The helper already checked the press AND current cursor artwork.
            // Start from the current window and pointer positions. The hold
            // delay decides whether this is a drag; replaying its accumulated
            // motion here teleports the window before the native/Wobbly grab.
            auto target=w->layoutTarget();
            if(!target||!target->space())
                return SDispatchResult{.success=false,.error="The window has no drag target"};
            // Pointer motion now goes directly through the compositor, at the
            // display/input cadence, rather than 16 ms IPC position updates.
            g_layoutManager->beginDragTarget(target,MBIND_MOVE,std::nullopt,true);
            if(g_layoutManager->dragController()->target()!=target) {
                return SDispatchResult{.success=false,.error="The title grip could not start"};
            }
            grip=w;return SDispatchResult{};
        }
        return SDispatchResult{.success=false,.error="The window has closed"};
    });
    HyprlandAPI::addDispatcherV2(handle,"xetaldrag:end",[](std::string){endGrip();return SDispatchResult{};});
    command = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-cursor", true, [](eHyprCtlOutputFormat, std::string) {
        return std::format("{{\"current\":{},\"press\":{},\"down\":{},\"serial\":{},\"native_drag\":true,\"dragging\":{},\"origin\":{}}}", cursor(), press, down, serial,!grip.expired(),origin);
    }});
    return {"Xetal Cursor Probe", "Cursor metadata for text-safe floating drags", "XetalEngine", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() { FileDragActions::stop();buttonListener.reset();endGrip(); }
