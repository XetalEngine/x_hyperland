// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "window_types.hpp"
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/xwayland/XWayland.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>

namespace WindowTypes {
// Use protocol roles, never class/title/size heuristics. This is also called
// before mapping, so mapped/hidden checks belong to each operation's caller.
inline bool geometryManaged(PHLWINDOW window) {
    if (!window) return false;
    if (window->m_isX11) {
        const auto x11 = window->m_xwaylandSurface.lock();
        return x11 && managedX11(x11->m_overrideRedirect, x11->m_atoms, HYPRATOMS);
    }
    const auto xdg = window->m_xdgSurface.lock();
    return xdg && managedWayland(bool(xdg->m_toplevel), bool(xdg->m_popup));
}
}
