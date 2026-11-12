// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>

namespace WindowTypes {
// Explicit ownership for desktop toplevels whose anchors are set before map.
// Unlike an app-name heuristic, this can also be assigned by a window rule.
template<typename Tags>
bool placementOwned(const Tags& tags) {
    for (const auto& value : tags) {
        std::string_view tag(value);
        if (tag.ends_with('*')) tag.remove_suffix(1);
        if (tag == "fusion-placement-owned") return true;
    }
    return false;
}

// These surfaces own their geometry. A NORMAL fallback in the type list does
// not turn a menu into an application window. Untyped legacy clients, dialogs
// and utility windows still participate in ordinary window management.
inline constexpr std::array applicationPositionedTypes = {
    "_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK",
    "_NET_WM_WINDOW_TYPE_TOOLBAR", "_NET_WM_WINDOW_TYPE_MENU",
    "_NET_WM_WINDOW_TYPE_SPLASH", "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU",
    "_NET_WM_WINDOW_TYPE_POPUP_MENU", "_NET_WM_WINDOW_TYPE_TOOLTIP",
    "_NET_WM_WINDOW_TYPE_NOTIFICATION", "_NET_WM_WINDOW_TYPE_COMBO",
    "_NET_WM_WINDOW_TYPE_DND",
};

template<typename AtomTable>
bool managedX11(bool overrideRedirect, std::span<const uint32_t> types, const AtomTable& atoms) {
    if (overrideRedirect) return false;
    for (const auto name : applicationPositionedTypes) {
        const auto atom = atoms.find(std::string(name));
        if (atom != atoms.end() && atom->second && std::ranges::find(types, atom->second) != types.end())
            return false;
    }
    return true;
}

constexpr bool managedWayland(bool toplevel, bool popup) { return toplevel && !popup; }
}
