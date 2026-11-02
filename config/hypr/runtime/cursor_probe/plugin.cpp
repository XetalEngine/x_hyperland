// SPDX-License-Identifier: GPL-2.0-or-later
// Read-only cursor metadata for the session's floating-title drag helper.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/managers/SeatManager.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/protocols/core/DataDevice.hpp>
#include <hyprland/src/protocols/core/Seat.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <drm_fourcc.h>
#include <linux/input-event-codes.h>

namespace {
SP<SHyprCtlCommand> command;
CHyprSignalListener buttonListener;
bool down = false;
uint64_t serial = 0;
std::string press = "{}";

std::string cursor() {
    const auto& data = g_pHyprRenderer->m_lastCursorData;
    // Never expose client-provided strings in JSON or mistake an unknown
    // shape for an ordinary arrow. This also leaves resize/link cursors alone.
    if (!g_pSeatManager->m_state.pointerFocus.lock() || PROTO::data->dndActive())
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
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Rebuild cursor probe for this compositor ABI");
    buttonListener = Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent event, Event::SCallbackInfo& info) {
        if (event.button != BTN_LEFT) return;
        down = event.state == WL_POINTER_BUTTON_STATE_PRESSED && !info.cancelled;
        if (down) { ++serial; press = cursor(); }
    });
    command = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-cursor", true, [](eHyprCtlOutputFormat, std::string) {
        return std::format("{{\"current\":{},\"press\":{},\"down\":{},\"serial\":{}}}", cursor(), press, down, serial);
    }});
    return {"Xetal Cursor Probe", "Cursor metadata for text-safe floating drags", "XetalEngine", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() { buttonListener.reset(); }
