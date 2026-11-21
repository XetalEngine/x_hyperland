// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <algorithm>
#include <functional>
#include <vector>

namespace Minimize {
// Subscribe to the backend signal itself. The pinned 0.57 binary inlines
// CWindow::onUpdateState into its signal callback, bypassing a function detour.
// Weak window references also cover already-open clients during plugin reload.
class ClientRequests {
    struct Watch {
        PHLWINDOWREF window;
        CHyprSignalListener listener;
    };
    std::vector<Watch> watches;
  public:
    void prune() { std::erase_if(watches, [](const auto& watch) { return watch.window.expired(); }); }
    void clear() { watches.clear(); }
    void track(PHLWINDOW window, const std::function<void(PHLWINDOW, bool)>& dispatch) {
        prune();
        if (!window || std::ranges::any_of(watches, [&](const auto& watch) { return watch.window.lock() == window; })) return;
        PHLWINDOWREF weak = window;
        auto listener = window->backend().m_events.stateRequest.listen([weak, dispatch](const auto& request) {
            if (request.minimized.has_value())
                if (auto current = weak.lock()) dispatch(current, *request.minimized);
        });
        watches.push_back({weak, std::move(listener)});
    }
};
}
