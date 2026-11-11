// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/desktop/view/Popup.hpp>
#include <hyprland/src/desktop/view/LayerSurface.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <cmath>

namespace WindowInspector {
// On-demand metadata only: no hooks, input, retained surfaces, screenshots,
// geometry changes or polling inside the compositor.
inline std::string surfaces() {
    using namespace Desktop::View;
    std::string result = "{\"version\":1,\"surfaces\":[";
    bool first = true;
    for (const auto& weak : Desktop::viewState()->otherViews()) {
        const auto view = weak.lock();
        if (!view || (view->type() != VIEW_TYPE_POPUP && view->type() != VIEW_TYPE_SUBSURFACE)) continue;
        const auto resource = view->resource();
        const auto box = view->logicalBox();
        if (!resource || !resource->m_mapped || !box ||
            !std::isfinite(box->x) || !std::isfinite(box->y) ||
            !std::isfinite(box->w) || !std::isfinite(box->h)) continue;
        pid_t pid = 0;
        if (auto client = resource->client()) wl_client_get_credentials(client, &pid, nullptr, nullptr);
        uintptr_t ownerAddress = 0;
        const char* ownerType = "";
        if (view->type() == VIEW_TYPE_POPUP) {
            const auto popup = CPopup::fromView(view);
            const auto owner = popup ? popup->getT1Owner() : nullptr;
            const auto parent = owner ? owner->view() : nullptr;
            if (parent && parent->type() == VIEW_TYPE_WINDOW) {
                ownerAddress = reinterpret_cast<uintptr_t>(CWindow::fromView(parent).get()); ownerType = "window";
            } else if (parent && parent->type() == VIEW_TYPE_LAYER_SURFACE) {
                ownerAddress = reinterpret_cast<uintptr_t>(CLayerSurface::fromView(parent).get()); ownerType = "layer";
            }
        }
        if (!first) result += ',';
        first = false;
        result += std::format("{{\"address\":\"0x{:x}\",\"role\":\"{}\",\"resourceId\":{},\"pid\":{},"
                              "\"x\":{},\"y\":{},\"width\":{},\"height\":{},\"mapped\":true,\"visible\":{},"
                              "\"ownerAddress\":\"0x{:x}\",\"ownerType\":\"{}\"}}",
                              reinterpret_cast<uintptr_t>(view.get()), view->type() == VIEW_TYPE_POPUP ? "popup" : "subsurface",
                              resource->id(), pid, box->x, box->y, box->w, box->h, view->visible(), ownerAddress, ownerType);
    }
    return result + "]}";
}
}
