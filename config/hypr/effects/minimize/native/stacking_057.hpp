// SPDX-License-Identifier: GPL-2.0-or-later
// The pinned compositor has a separate floating-over-fullscreen plane. Merely
// raising its maximized window does not lower other windows out of that plane.
// Keep the existing alterzorder binding/editor contract and fix both planes.
namespace Order {
struct Item { PHLWINDOWREF window; bool above=false; };
struct Saved { PHLWORKSPACEREF workspace; PHLWINDOWREF focus; std::vector<Item> items; };
std::map<std::string,Saved> workspaces;
using OrderFn=Config::Actions::ActionResult (*)(const std::string&,std::optional<PHLWINDOW>);
OrderFn ordinaryOrder;
using ChangeFn=void (*)(Monitor::CMonitor*,const PHLWORKSPACE&,bool,bool,bool);
ChangeFn originalChange;
bool applying=false;

bool eligible(PHLWINDOW w,PHLWORKSPACE ws) {
    return w && w->mapped() && !w->isHidden() && w->m_workspace==ws && !recordFor(w);
}
void remember(PHLWORKSPACE ws) {
    if(!ws || Fusion057::special(ws))return;
    Saved saved;saved.workspace=ws;
    auto focus=Desktop::focusState()->window();if(eligible(focus,ws))saved.focus=focus;
    for(auto& w:Desktop::windowState()->windows())if(eligible(w,ws))saved.items.push_back({w,w->fullscreenPolicy().allowedOverFullscreen()});
    workspaces[ws->addressableName()]=std::move(saved);
    std::erase_if(workspaces,[](const auto& pair){return pair.second.workspace.expired();});
}
void permission(PHLWINDOW w,bool above) {
    w->fullscreenPolicy().setAllowedOverFullscreen(above);
    w->updateFullscreenInputState();
    w->presentation().alpha(Desktop::View::WINDOW_ALPHA_FULLSCREEN)->setValueAndWarp(w->isBlockedByFullscreen()?0.F:1.F);
}
void reconcile(PHLWORKSPACE ws) {
    auto fullscreen=Fullscreen::controller()->getFullscreenWindow(ws);
    if(!fullscreen)return;
    bool over=false;
    for(auto& w:Desktop::windowState()->windows()) {
        if(!eligible(w,ws))continue;
        if(w==fullscreen){over=true;continue;}
        permission(w,over && w->isFloating());
    }
}
void change(Monitor::CMonitor* monitor,const PHLWORKSPACE& ws,bool internal,bool noMouseMove,bool noFocus) {
    if(applying || internal || !ws || monitor->m_activeWorkspace==ws){originalChange(monitor,ws,internal,noMouseMove,noFocus);return;}
    remember(monitor->m_activeWorkspace);
    originalChange(monitor,ws,internal,noMouseMove,noFocus);
    auto found=workspaces.find(ws->addressableName());if(found==workspaces.end() || found->second.workspace.lock()!=ws)return;
    auto saved=found->second;
    applying=true;
    // Workspace entry synthesizes pointer movement; it must not permanently
    // raise the settings window that happens to be underneath the pointer.
    if(!noFocus)if(auto w=saved.focus.lock();eligible(w,ws))Desktop::focusState()->fullWindowFocus(w,Desktop::FOCUS_REASON_WORKSPACE_CHANGE);
    for(auto& item:saved.items)if(auto w=item.window.lock();eligible(w,ws))Desktop::windowState()->raise(w);
    for(auto& item:saved.items)if(auto w=item.window.lock();eligible(w,ws))permission(w,item.above);
    applying=false;
    if(auto m=ws->m_monitor.lock()){m->recheckSolitary();g_pHyprRenderer->damageMonitor(m);}
}
Config::Actions::ActionResult dispatch(const std::string& mode,std::optional<PHLWINDOW> window) {
    if(mode!="top" && mode!="bottom")return ordinaryOrder(mode,window);
    auto w=window.value_or(Desktop::focusState()->window());
    if(!w || !w->mapped())return {};
    if(recordFor(w))return Config::Actions::actionError("Restore the minimized window first");
    auto ws=w->m_workspace;const bool active=Desktop::focusState()->window()==w;
    if(mode=="top")Desktop::windowState()->raise(w);else Desktop::windowState()->lower(w);
    reconcile(ws);
    if(mode=="bottom" && active) {
        // Leave focus on the newly exposed window. A synthetic pointer move
        // here would immediately undo the requested order in follow-mouse mode.
        auto windows=Desktop::windowState()->windows();
        for(auto& candidate:std::views::reverse(windows))if(candidate!=w && eligible(candidate,ws) && candidate->acceptsInput()){
            Desktop::focusState()->fullWindowFocus(candidate,Desktop::FOCUS_REASON_KEYBIND);break;
        }
        reconcile(ws);
    }
    remember(ws);
    if(auto m=w->m_monitor.lock()){m->recheckSolitary();g_pHyprRenderer->damageMonitor(m);}
    return {};
}
void init() {
    hook("changeWorkspace","CSharedPointer<Workspace::CHLWorkspace> const&",(void*)change,originalChange);
    hook("alterZOrder","Config::Actions::alterZOrder(",(void*)dispatch,ordinaryOrder);
}
void stop() {
    workspaces.clear();
}
}
