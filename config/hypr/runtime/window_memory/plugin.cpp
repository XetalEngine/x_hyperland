// SPDX-License-Identifier: GPL-2.0-or-later
// Typed dialog metadata and addressed fullscreen restoration. No focus changes.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <sstream>

namespace {
SP<SHyprCtlCommand> metadataCommand, stateCommand;
uint64_t hash(const std::string& value) {
    uint64_t result = 14695981039346656037ULL;
    for (unsigned char byte : value) { result ^= byte; result *= 1099511628211ULL; }
    return result;
}
std::string metadata() {
    std::string result = "{";
    for (const auto& window : Desktop::windowState()->windows()) {
        if (!window->m_isMapped) continue;
        const auto parent = window->parent();
        const auto xdg = window->m_xdgSurface.lock();
        const auto top = xdg ? xdg->m_toplevel.lock() : nullptr;
        const auto x11 = window->m_xwaylandSurface.lock();
        const bool dialog = parent || (top && top->m_dialog.lock());
        // xdg-shell uses zero for an unspecified limit, not a zero-size lock.
        const bool fixed = top && top->m_current.minSize.x > 0 && top->m_current.minSize.y > 0 &&
                           top->m_current.minSize == top->m_current.maxSize;
        // Never persist/export titles, document paths, or a window's contents.
        const auto role = x11 && !x11->m_role.empty() ? x11->m_role : dialog ? window->m_initialTitle : "main";
        if (result.size() > 1) result += ',';
        result += std::format("\"0x{:x}\":{{\"dialog\":{},\"fixed\":{},\"role\":\"{:016x}\"}}",
                              reinterpret_cast<uintptr_t>(window.get()), dialog, fixed, hash(role));
    }
    return result + '}';
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Rebuild window memory for this compositor ABI");
    metadataCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-windows", true,
        [](eHyprCtlOutputFormat, std::string) { return metadata(); }});
    stateCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-window-state", false,
        [](eHyprCtlOutputFormat, std::string input) {
            std::istringstream args(input);
            std::string command, address, extra;
            int internal = -1, client = -1;
            args >> command >> address >> internal >> client;
            if (args.fail() || (args >> extra) || internal < 0 || internal > 2 || client < 0 || client > 2)
                return std::string("invalid state");
            for (const auto& window : Desktop::windowState()->windows()) {
                if (!window->m_isMapped || address != std::format("0x{:x}", reinterpret_cast<uintptr_t>(window.get()))) continue;
                Fullscreen::controller()->setFullscreenMode(window, static_cast<Fullscreen::eFullscreenMode>(internal),
                                                            static_cast<Fullscreen::eFullscreenMode>(client));
                return std::string("ok");
            }
            return std::string("window not found");
        }});
    return {"Xetal Window Memory", "Per-application window and dialog geometry", "XetalEngine", "1.0"};
}
APICALL EXPORT void PLUGIN_EXIT() {}
