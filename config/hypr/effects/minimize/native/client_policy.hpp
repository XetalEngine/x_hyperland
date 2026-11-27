// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>

namespace Minimize {
// GLFW and some games request minimize automatically on fullscreen focus loss.
// Keep their fullscreen surface visible while the user works on another display.
// This applies only to client requests: explicit desktop minimize controls bypass
// it, and focused, ordinary/maximized and restore requests retain their behavior.
inline bool ignoreClientMinimize(PHLWINDOW window, bool minimizing) {
    if (!minimizing || !window) return false;
    const auto mode = Fullscreen::controller()->getFullscreenModes(window);
    if (mode.internal != Fullscreen::FSMODE_FULLSCREEN && mode.client != Fullscreen::FSMODE_FULLSCREEN) return false;
    const auto focus = Desktop::focusState();
    // On an empty neighboring output the core can retain the previous window
    // briefly after deactivating it. Check the focused monitor as well.
    return focus->window() != window || focus->monitor() != window->m_monitor.lock();
}
}
