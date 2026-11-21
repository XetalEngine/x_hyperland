// Exercise the production subscription with real Hyprutils signals/ownership.
#include <hyprutils/signal/Signal.hpp>
#include <hyprutils/memory/SharedPtr.hpp>
#include <hyprutils/memory/WeakPtr.hpp>
#include <cassert>
#include <optional>
#include <utility>
using namespace Hyprutils::Signal;
using namespace Hyprutils::Memory;
struct Request { std::optional<bool> maximized{}, minimized{}; };
struct Backend { struct { CSignalT<Request> stateRequest; } m_events; };
struct Window { Backend value; Backend& backend() { return value; } };
using PHLWINDOW = CSharedPointer<Window>;
using PHLWINDOWREF = CWeakPointer<Window>;
#include "client_requests_057.hpp"

int main() {
    Minimize::ClientRequests listener;
    auto existing = makeShared<Window>();
    auto created = makeShared<Window>();
    std::vector<std::pair<Window*,bool>> received;
    const auto dispatch = [&](PHLWINDOW w, bool minimized) { received.emplace_back(w.get(),minimized); };
    listener.track(existing, dispatch);
    listener.track(existing, dispatch); // map/re-map notification must not duplicate requests
    listener.track(created, dispatch);
    auto send = [](PHLWINDOW w, Request request) { w->backend().m_events.stateRequest.emit(request); };
    send(existing, {.minimized=true});
    send(created, {.minimized=true});
    send(existing, {.minimized=false});
    send(existing, {.maximized=true});
    send(existing, {.maximized=false});
    send(created, {});
    assert(received.size()==3);
    assert(received[0]==std::make_pair(existing.get(),true));
    assert(received[1]==std::make_pair(created.get(),true));
    assert(received[2]==std::make_pair(existing.get(),false));
    PHLWINDOWREF weak=created; created.reset();
    assert(weak.expired()); // watching a client must not keep a closed app alive
    listener.prune();
    send(existing, {.minimized=true}); assert(received.size()==4);
    listener.clear();
    send(existing, {.minimized=true}); assert(received.size()==4);
    listener.track(existing,dispatch); // reload reconnects already-open windows
    send(existing, {.minimized=true}); assert(received.size()==5);
}
