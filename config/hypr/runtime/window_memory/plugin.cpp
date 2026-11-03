// SPDX-License-Identifier: GPL-2.0-or-later
// Typed window memory, launch intent and client-decoration input geometry.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/desktop/view/Popup.hpp>
#include <hyprland/src/desktop/view/WLSurface.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <sstream>

namespace {
SP<SHyprCtlCommand> metadataCommand, stateCommand;
CHyprSignalListener mappedListener;
std::vector<CFunctionHook*> hooks;
void cleanup(){
    mappedListener.reset();
    for(auto hook:std::views::reverse(hooks))hook->unhook();
    hooks.clear();
}
template<typename T> void hook(HANDLE handle,const std::string& name,const std::string& signature,const void* replacement,T& original){
    for(const auto& match:HyprlandAPI::findFunctionsByName(handle,name)){
        if(match.demangled.find(signature)==std::string::npos)continue;
        auto hook=HyprlandAPI::createFunctionHook(handle,match.address,replacement);
        if(!hook||!hook->hook())throw std::runtime_error("Cannot install window input hook: "+name);
        original=reinterpret_cast<T>(hook->m_original);hooks.push_back(hook);return;
    }
    throw std::runtime_error("Unsupported window input API: "+name);
}
using SurfaceAtFn=SP<CWLSurfaceResource> (*)(const Desktop::CViewHitTester*,const Vector2D&,PHLWINDOW,Vector2D&);
using SurfaceBoxFn=std::optional<CBox> (*)(const Desktop::View::CWLSurface*);
SurfaceAtFn originalSurfaceAt;
SurfaceBoxFn originalSurfaceBox;
Vector2D contentOffset(PHLWINDOW w){
    if(!w||!w->m_xdgSurface||!w->wlSurface()->resource())return {};
    const auto geom=w->m_xdgSurface->m_current.geometry;
    const auto size=w->wlSurface()->resource()->m_current.size;
    // Exactly the geometry that the render adapter can crop. Leave unusual
    // client geometry outside the main buffer on the compositor's own path.
    if(size.x<=0||size.y<=0||geom.w<=0||geom.h<=0||geom.x<0||geom.y<0||geom.x+geom.w>size.x||geom.y+geom.h>size.y)return {};
    return geom.pos();
}
SP<CWLSurfaceResource> surfaceAtHook(const Desktop::CViewHitTester* tester,const Vector2D& pos,PHLWINDOW w,Vector2D& local){
    if(!w||!w->m_isMapped||!w->m_xdgSurface||w->m_isX11||w->m_popupHead->at(pos))
        return originalSurfaceAt(tester,pos,w,local);
    // The visible content starts at xdg_window_geometry, not the origin of
    // the surface (Chrome adds 10px of invisible shadow padding). Match the
    // renderer UV crop for hit testing, including subsurfaces inside the window.
    const auto offset=contentOffset(w);
    if(offset==Vector2D{})return originalSurfaceAt(tester,pos,w,local);
    auto [surface,point]=w->wlSurface()->resource()->at(pos-w->position(Desktop::View::IGeometric::GEOMETRIC_GOAL)+offset,true);
    if(surface)local=point;
    return surface;
}
std::optional<CBox> surfaceBoxHook(const Desktop::View::CWLSurface* surface){
    auto box=originalSurfaceBox(surface);
    auto w=Desktop::View::CWindow::fromView(surface->view());
    // Input keeps focus on this surface while a button is held. Its global
    // origin must use the same offset as the initial hit, or a stationary
    // click/selection jumps as soon as the first held motion arrives.
    if(box&&w&&w->m_xdgSurface&&!w->m_isX11&&w->wlSurface().get()==surface)
        box->translate(-contentOffset(w));
    return box;
}

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
    try{
        hook(handle,"windowSurfaceAt","CViewHitTester::windowSurfaceAt(",(void*)surfaceAtHook,originalSurfaceAt);
        hook(handle,"getSurfaceBoxGlobal","CWLSurface::getSurfaceBoxGlobal(",(void*)surfaceBoxHook,originalSurfaceBox);
        mappedListener = Event::bus()->m_events.window.openLate.listen([](PHLWINDOW w){
            if(w&&w->m_isMapped){
                const auto& tags=w->m_ruleApplicator->m_tagKeeper.getTags();
                const bool launched=std::ranges::any_of(tags,[](const auto& tag){return tag.starts_with("xetal-tile-")||tag.starts_with("xetal-float-");});
                if(launched&&w->m_ruleApplicator->static_.fullscreenStateInternal==0&&w->m_ruleApplicator->static_.fullscreenStateClient==0)
                    // fullscreen_state is only our initial choice. Core turns
                    // sync off for that rule; restore it so later native
                    // maximize/restore buttons remain fully functional.
                    w->m_ruleApplicator->syncFullscreenOverride(Desktop::Types::COverridableVar(true,Desktop::Types::PRIORITY_WINDOW_RULE));
            }
        });
    }catch(...){cleanup();throw;}
    return {"Xetal Window Memory", "Window geometry, launch modes and decoration input", "XetalEngine", "1.1"};
}
APICALL EXPORT void PLUGIN_EXIT() { cleanup(); }
