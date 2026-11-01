// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/view/Group.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/state/GlobalWindowController.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/layout/target/Target.hpp>
#include <hyprland/src/state/WorkspaceState.hpp>
#include <hyprland/src/state/MonitorState.hpp>
#include <hyprland/src/managers/KeybindManager.hpp>
#include <hyprland/src/managers/EventManager.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/config/shared/actions/ConfigActions.hpp>
#include <hyprland/src/config/ConfigValue.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/protocols/InputCapture.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <hyprland/src/render/gl/GLFramebuffer.hpp>
#include <linux/input-event-codes.h>
#include <hyprutils/utils/ScopeGuard.hpp>
#include <fstream>
#include <filesystem>
#include <set>
#include <map>
#include "graphics.hpp"
#include "settings.hpp"
#include "icons.hpp"
#include <hyprgraphics/image/Image.hpp>
#include <drm_fourcc.h>

namespace {
using Clock=std::chrono::steady_clock;
using Rect=Minimize::Rect;
HANDLE handle;
Minimize::Settings settings;
Minimize::Graphics graphics;
bool stopping=false, mutating=false, capturing=false, effectsHidden=false;
uint64_t sequence=0, requests=0, restored=0, draws=0;
SP<CEventLoopTimer> timer;
SP<SHyprCtlCommand> statusCommand;
std::vector<CHyprSignalListener> listeners;
std::vector<CFunctionHook*> hooks;
std::function<SDispatchResult(std::string)> ordinaryFocus;
std::map<MONITORID,int> scroll;
std::set<uint32_t> consumedButtons;
struct Pending { PHLWINDOWREF window; bool minimize; };
std::vector<Pending> pending;

struct Record {
    uint64_t id=0;
    std::vector<PHLWINDOWREF> members;
    PHLWINDOWREF primary;
    PHLWORKSPACE original, stash;
    PHLMONITORREF monitor;
    Fullscreen::SFullscreenMode fullscreen;
    bool pinned=false, floating=false, restoring=false, settled=false;
    Rect geometry, source, target, flight;
    Vector2D snapshotScreen;
    SP<Render::IFramebuffer> snapshot;
    SP<Render::ITexture> appIcon;
    std::filesystem::file_time_type iconStamp{};
    Clock::time_point iconCheck{};
    Clock::time_point born;
    uint32_t seed=uint32_t(Clock::now().time_since_epoch().count()) ^ uint32_t(sequence*2654435761U);
    Minimize::Fire fire{seed};
    Clock::time_point lastFrame=Clock::now();
    double effectTime=0;
};
std::vector<std::shared_ptr<Record>> records;

PHLWINDOW member(const Record& r) {
    if (auto w=r.primary.lock(); w && w->m_isMapped) return w;
    for (const auto& weak:r.members) if (auto w=weak.lock(); w && w->m_isMapped) return w;
    return nullptr;
}
std::shared_ptr<Record> recordFor(PHLWINDOW w) {
    for (auto& r:records) for (auto& weak:r->members) if (weak.lock()==w) return r;
    return nullptr;
}
bool online(PHLMONITOR m) {
    const auto& monitors=State::monitorState()->monitors();
    return m && !m->m_mirrorOf && std::ranges::find(monitors,m)!=monitors.end();
}
PHLMONITOR fallback() {
    auto m=Desktop::focusState()->monitor(); if(online(m))return m;
    for(auto& monitor:State::monitorState()->monitors())if(online(monitor))return monitor;
    return nullptr;
}
bool visible(PHLMONITOR m) {
    return !stopping && !effectsHidden && online(m) && g_pCompositor->m_sessionActive &&
        !g_pSessionLockManager->isSessionLocked() && !PROTO::inputCapture->isCaptured() &&
        std::ranges::any_of(records,[&](const auto& r){return r->monitor.lock()==m;});
}
Rect rect(CBox b) {return {b.x,b.y,b.width,b.height};}
CBox box(Rect r) {return {r.x,r.y,r.w,r.h};}
Rect windowBox(PHLWINDOW w, PHLMONITOR m, bool goal=false) {
    auto b=w->geometricBox(goal?Desktop::View::IGeometric::GEOMETRIC_GOAL:Desktop::View::IGeometric::GEOMETRIC_CURRENT);
    return rect(b.addExtents(w->getFullWindowExtents()).translate(-m->m_position));
}
double progress(const Record& r) {
    static auto animations=CConfigValue<Config::INTEGER>("animations:enabled");
    if(!*animations)return 1;
    return std::clamp(std::chrono::duration<double,std::milli>(Clock::now()-r.born).count()/settings.duration,0.0,1.0);
}
Minimize::Column column(PHLMONITOR m) {
    int count=std::ranges::count_if(records,[&](const auto& r){return r->monitor.lock()==m;});
    Minimize::Column c(m->m_size.x,m->m_size.y,m->m_reservedArea.left(),m->m_reservedArea.top(),m->m_reservedArea.right(),m->m_reservedArea.bottom(),
                       settings.size,count,scroll[m->m_id],settings.rightEdge,settings.bottomToTop);
    scroll[m->m_id]=c.offset; return c;
}
std::optional<Rect> slot(const Record& r) {
    auto m=r.monitor.lock();if(!m)return {};
    auto c=column(m);int i=0;
    for(auto& item:records)if(item->monitor.lock()==m){
        if(item.get()==&r)return c.visible(i)?std::optional<Rect>(c.box(i)):std::nullopt;
        ++i;
    }
    return {};
}
Rect thumbnail(Rect b, const Record& r) {
    if(r.appIcon){const double size=b.w*.43;return {b.x+(b.w-size)/2,b.y+b.h*(settings.effect=="splat"?.53:.72)-size/2,size,size};}
    double w=b.w*.29,h=std::min(b.h*.19,w*r.source.h/std::max(1.0,r.source.w));
    return {b.x+(b.w-w)/2,b.y+b.h*(settings.effect=="splat"?.53:.72)-h/2,w,h};
}
void refreshIcon(Record& r) {
    if(Clock::now()<r.iconCheck)return;
    r.iconCheck=Clock::now()+std::chrono::seconds(1);
    const auto window=member(r);const char* runtime=std::getenv("XDG_RUNTIME_DIR");
    if(!window || !runtime)return;
    const auto directory=std::filesystem::path(runtime)/"hypr"/g_pCompositor->m_instanceSignature/"xetal-minimize-icons";
    for(const auto& name:{window->m_class,window->m_initialClass}){
        if(name.empty())continue;
        std::error_code error;
        const auto path=directory/Minimize::iconKey(name);
        if(!std::filesystem::is_regular_file(path,error) || error)continue;
        const auto stamp=std::filesystem::last_write_time(path,error);
        if(error)continue;
        if(r.appIcon && stamp==r.iconStamp)return;
        const auto bytes=std::filesystem::file_size(path,error);
        if(error || bytes>1024*1024)continue;
        Hyprgraphics::CImage image(path.string());
        if(!image.success())continue;
        auto surface=image.cairoSurface();
        if(!surface || surface->size().x>512 || surface->size().y>512)continue;
        g_pHyprRenderer->glBackend()->makeEGLCurrent();
        r.appIcon=g_pHyprRenderer->createTexture(DRM_FORMAT_ARGB8888,surface->data(),surface->stride(),surface->size());
        r.iconStamp=stamp;return;
    }
    r.appIcon.reset();
}
void damage(bool full=true) {
    for(auto& r:records)if(auto m=r->monitor.lock();visible(m)){
        if(full || !r->settled)g_pHyprRenderer->damageMonitor(m);
        else if(auto b=slot(*r))g_pHyprRenderer->damageBox(box(*b).expand(8).translate(m->m_position));
    }
}
void arm() {if(timer)timer->updateTimeout(std::chrono::milliseconds(1));}
void enqueue(PHLWINDOW w, bool minimize) {
    if(stopping || mutating || !w)return;
    pending.push_back({w,minimize});arm();
}

// Keep bounded previews instead of one full-resolution monitor texture per window.
SP<Render::IFramebuffer> capture(PHLWINDOW w) {
    struct Guard { Guard(){capturing=true;} ~Guard(){capturing=false;} } guard;
    auto renderer=g_pHyprRenderer.get();auto data=renderer->m_renderData;
    renderer->glBackend()->makeEGLCurrent();
    GLint read=0,draw=0,viewport[4];
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);glGetIntegerv(GL_VIEWPORT,viewport);
    const bool snapshotMode=renderer->m_bRenderingSnapshot;
    Hyprutils::Utils::CScopeGuard reset([&]{
        renderer->m_renderData=data;renderer->m_bRenderingSnapshot=snapshotMode;
        glBindFramebuffer(GL_READ_FRAMEBUFFER,read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
        renderer->setViewport(viewport[0],viewport[1],viewport[2],viewport[3]);
    });
    auto original=g_pHyprRenderer->makeSnapshotFB(w);if(!original)return nullptr;
    double scale=std::min(1.0,1024.0/std::max(original->m_size.x,original->m_size.y));
    if(scale==1)return original;
    auto small=g_pHyprRenderer->createFB("minimized preview");
    if(!small->alloc(std::max(1,int(original->m_size.x*scale)),std::max(1,int(original->m_size.y*scale)),DRM_FORMAT_ABGR8888))return nullptr;
    small->setImageDescription(original->imageDescription());
    Minimize::GLState restore;
    glBindFramebuffer(GL_READ_FRAMEBUFFER,static_cast<Render::GL::CGLFramebuffer*>(original.get())->getFBID());
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER,static_cast<Render::GL::CGLFramebuffer*>(small.get())->getFBID());
    g_pHyprRenderer->glBackend()->setCapStatus(GL_SCISSOR_TEST,false);
    glBlitFramebuffer(0,0,original->m_size.x,original->m_size.y,0,0,small->m_size.x,small->m_size.y,GL_COLOR_BUFFER_BIT,GL_LINEAR);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
    return small;
}

// Avoid automatic grouping on either side of the temporary workspace move.
bool move(PHLWINDOW w, PHLWORKSPACE workspace) {
    const auto rules=w->m_groupRules;w->m_groupRules|=Desktop::View::GROUP_BARRED;
    const bool wasMutating=mutating;mutating=true;
    Hyprutils::Utils::CScopeGuard reset([&]{mutating=wasMutating;w->m_groupRules=rules;});
    const auto result=Config::Actions::moveToWorkspace(workspace,true,w);
    if(!result || w->m_workspace!=workspace)return false;
    for(auto& window:Desktop::windowState()->windows())if(window==w || (w->m_group && w->m_group->has(window))){
        window->alpha(Desktop::View::WINDOW_ALPHA_MOVE_TO_WORKSPACE)->setValueAndWarp(1.F);
        window->alpha(Desktop::View::WINDOW_ALPHA_MOVE_FROM_WORKSPACE)->setValueAndWarp(1.F);
        window->m_monitorMovedFrom=-1;
    }
    return true;
}
void minimize(PHLWINDOW w) {
    if(!settings.enabled || !w || !w->m_isMapped || w->isHidden() || recordFor(w) ||
       g_pSessionLockManager->isSessionLocked())return;
    auto m=w->m_monitor.lock();if(!online(m) || !w->m_workspace || !w->m_workspace->isVisible())return;
    // Override-redirect X11 menus/popups are not application toplevels.
    if(w->m_isX11 && w->m_xwaylandSurface && w->m_xwaylandSurface->m_overrideRedirect)return;
    auto r=std::make_shared<Record>();r->id=++sequence;r->primary=w;r->monitor=m;r->original=w->m_workspace;
    r->geometry=rect(w->geometricBox(Desktop::View::IGeometric::GEOMETRIC_GOAL).translate(-m->m_position));
    r->source=windowBox(w,m);r->flight=r->source;r->snapshotScreen=m->m_size;
    if(r->source.w<=0 || r->source.h<=0)return;
    r->fullscreen=Fullscreen::controller()->getFullscreenModes(w);r->pinned=w->m_pinned;r->floating=w->m_isFloating;
    r->members=w->m_group?w->m_group->windows():std::vector<PHLWINDOWREF>{w};
    r->snapshot=capture(w);refreshIcon(*r);r->born=Clock::now();
    // Share a hidden workspace per original workspace, so the taskbar can
    // group minimized apps by their home workspace. Never allocate per window.
    for(auto& existing:records)if(existing->stash && existing->stash->m_monitor==m && existing->original==r->original && !existing->stash->inert()){
        r->stash=existing->stash;break;
    }
    if(!r->stash){
        const auto id=State::workspaceState()->newSpecialID();
        if(!State::workspaceState()->isSpecial(id))return;
        r->stash=State::workspaceState()->create(id,m->m_id,"special:xetal-minimized-ws-"+std::to_string(r->original->m_id));
    }
    if(!r->stash)return;
    records.push_back(r);
    for(auto& weak:r->members)if(auto item=weak.lock())item->m_pinned=false;
    Fullscreen::controller()->setFullscreenMode(w,Fullscreen::FSMODE_NONE,Fullscreen::FSMODE_NONE);
    // Save normal floating geometry after leaving fullscreen, so restoring a
    // maximized window does not replace its later unmaximize size.
    if(r->floating)r->geometry=rect(w->layoutTarget()->position().translate(-m->m_position));
    if(!move(w,r->stash)){
        std::erase(records,r);
        for(auto& weak:r->members)if(auto item=weak.lock())item->m_pinned=r->pinned;
        Fullscreen::controller()->setFullscreenMode(w,r->fullscreen.internal,r->fullscreen.client);
        return;
    }
    for(auto& weak:r->members)if(auto item=weak.lock();item && item->m_xwaylandSurface)item->m_xwaylandSurface->setMinimized(true);
    int count=std::ranges::count_if(records,[&](const auto& item){return item->monitor.lock()==m;});
    auto c=column(m);scroll[m->m_id]=std::max(0,count-c.capacity);
    ++requests;m->recheckSolitary();damage();arm();
}

void finish(const std::shared_ptr<Record>& r, bool focus) {
    auto w=member(*r);auto m=r->monitor.lock();
    std::erase(records,r); // allow rendering/focus before any callback can observe the window
    if(w && r->restoring)w->setHidden(false);
    if(w && focus && !g_pSessionLockManager->isSessionLocked()) {
        Desktop::windowState()->raise(w);
        Desktop::focusState()->fullWindowFocus(w,Desktop::FOCUS_REASON_DISPATCH_FOCUSWINDOW);
    }
    if(m){g_pHyprRenderer->damageMonitor(m);m->recheckSolitary();}
    ++restored;
}
void restore(const std::shared_ptr<Record>& r, bool animate=true, bool focus=true) {
    if(r->restoring){if(!animate)finish(r,focus);return;}
    auto w=member(*r);if(!w){finish(r,false);return;}
    auto dock=r->monitor.lock();auto m=r->original?r->original->m_monitor.lock():nullptr;
    if(!online(m))m=fallback();
    if(!m)return; // retain the record until an output returns
    auto c=column(m);
    Rect origin=slot(*r).value_or(c.box(c.offset));
    if(!r->settled)origin=Minimize::travel(r->flight,thumbnail(origin,*r),progress(*r));
    else origin=thumbnail(origin,*r);
    r->restoring=true;r->settled=false;r->flight=origin;r->monitor=m;
    auto destination=r->original;
    if(!destination || destination->inert() || !online(destination->m_monitor.lock()))destination=m->m_activeWorkspace;
    if(!destination){r->restoring=false;return;}
    if(!move(w,destination)){r->restoring=false;return;}
    for(auto& weak:r->members)if(auto item=weak.lock()){
        item->m_pinned=r->pinned;
        if(item->m_xwaylandSurface)item->m_xwaylandSurface->setMinimized(false);
    }
    if(r->floating)w->layoutTarget()->setPositionGlobal(box(r->geometry).translate(m->m_position));
    Fullscreen::controller()->setFullscreenMode(w,r->fullscreen.internal,r->fullscreen.client);
    // The snapshot supplies the transition; do not run Hyprland's move animation as well.
    w->layoutTarget()->warpPositionSize();
    r->target=windowBox(w,m,true);r->born=Clock::now();
    w->setHidden(true);
    if(focus && !g_pSessionLockManager->isSessionLocked()) {
        if(destination->m_isSpecialWorkspace)m->setSpecialWorkspace(destination);
        else {m->setSpecialWorkspace(nullptr);m->changeWorkspace(destination,false,true,true);}
    }
    if(dock && dock!=m)g_pHyprRenderer->damageMonitor(dock);
    if(!animate || effectsHidden || !focus || !r->snapshot || dock!=m)finish(r,focus);
    else {damage();arm();}
}
void restoreAll() {
    auto copy=records;for(auto& r:copy)restore(r,false,false);
}
void toggleVisibility() {
    effectsHidden=!effectsHidden;
    // Finish any restore already in flight: its real window must become visible
    // even when the snapshot animation has just been hidden.
    auto copy=records;
    for(auto& r:copy){
        r->lastFrame=Clock::now();
        if(effectsHidden && r->restoring)finish(r,true);
    }
    // Damage explicitly when hiding, since damage() only visits visible effects.
    for(auto& m:State::monitorState()->monitors())if(online(m)){
        g_pHyprRenderer->damageMonitor(m);m->recheckSolitary();
    }
    arm();
}

void snapshot(const Record& r, PHLMONITOR m, Rect destination, float alpha) {
    if(!r.snapshot || alpha<=0)return;
    const double sx=destination.w/r.source.w,sy=destination.h/r.source.h;
    CTexPassElement::SRenderData data;data.tex=r.snapshot->getTexture();data.flipEndFrame=true;data.a=alpha;
    data.box=box({destination.x-r.source.x*sx,destination.y-r.source.y*sy,r.snapshotScreen.x*sx,r.snapshotScreen.y*sy}).scale(m->m_scale);
    data.clipRegion=CRegion{box(destination).scale(m->m_scale)};
    data.round=std::min(8.0,destination.w*.12)*m->m_scale;
    g_pHyprRenderer->draw(data,g_pHyprRenderer->m_renderData.damage);
}
class MinimizePass:public IPassElement {
    PHLMONITORREF monitor;
  public:
    explicit MinimizePass(PHLMONITOR m):monitor(m){}
    bool needsLiveBlur()override{return false;}
    bool needsPrecomputeBlur()override{return false;}
    const char* passName()override{return "XetalMinimize";}
    ePassElementType type()override{return EK_CUSTOM;}
    bool disableSimplification()override{return true;}
    std::vector<UP<IPassElement>> draw()override{
        auto m=monitor.lock();if(!visible(m))return {};
        const auto pointer=Pointer::mgr()->position()-m->m_position;
        static const auto epoch=Clock::now();
        const double seconds=std::fmod(std::chrono::duration<double>(Clock::now()-epoch).count(),3600.0);
        for(auto& r:records) {
            if(r->monitor.lock()!=m)continue;
            auto b=slot(*r);if(!b && !r->restoring)continue;
            double t=progress(*r);Rect thumb=b?thumbnail(*b,*r):r->flight;
            Rect dest=r->restoring?Minimize::travel(r->flight,r->target,t):Minimize::travel(r->source,thumb,t);
            double burn=r->restoring?1-Minimize::ease(t):Minimize::ease(t);
            // Flames travel with the shrinking window and keep burning at rest.
            Rect fire=b.value_or(Rect{r->flight.x,r->flight.y,double(settings.size),double(settings.size)});
            fire.x=dest.x+dest.w/2-fire.w/2;fire.y=dest.y+dest.h/2-fire.h*(settings.effect=="splat"?.53:.72);
            fire.y+=r->settled?std::sin(seconds*2.2+r->id)*2:0;
            const bool hover=box(fire).containsPoint(pointer);
            if(settings.effect=="splat")graphics.splat(m,fire,r->effectTime,r->seed,settings.shape,settings.surface,settings.bubbles/100.F,settings.rgb,float(burn),hover);
            else graphics.fire(m,fire,r->fire,settings.rgb,float(burn),hover);
            const double iconBlend=r->appIcon?std::clamp((burn-.5)*2.0,0.0,1.0):0;
            snapshot(*r,m,dest,float((1-burn*.25)*(1-iconBlend)));
            if(r->appIcon && iconBlend>0){
                const double size=std::min(dest.w,dest.h);
                CTexPassElement::SRenderData data;data.tex=r->appIcon;data.a=iconBlend;
                data.box=box({dest.x+(dest.w-size)/2,dest.y+(dest.h-size)/2,size,size}).scale(m->m_scale);
                g_pHyprRenderer->draw(data,g_pHyprRenderer->m_renderData.damage);
            }
            ++draws;
        }
        return {};
    }
};

using StateFn=void (*)(Desktop::View::CWindow*);
using RenderFn=bool (*)(Render::IHyprRenderer*,PHLWINDOW,PHLMONITOR);
using ScanoutFn=bool (*)(Monitor::CMonitor*);
using EventFn=void (*)(CEventManager*,const SHyprIPCEvent&);
StateFn originalState;RenderFn originalRender;ScanoutFn originalScanout;EventFn originalEvent;
void stateHook(Desktop::View::CWindow* window) {
    std::optional<bool> request;
    if(window->m_xdgSurface && window->m_xdgSurface->m_toplevel)request=window->m_xdgSurface->m_toplevel->m_state.requestsMinimize;
    else if(window->m_xwaylandSurface)request=window->m_xwaylandSurface->m_state.requestsMinimize;
    originalState(window);
    if(request.has_value())enqueue(window->m_self.lock(),*request);
}
bool renderHook(Render::IHyprRenderer* renderer,PHLWINDOW window,PHLMONITOR monitor) {
    if(!capturing && !stopping && recordFor(window))return false;
    return originalRender(renderer,window,monitor);
}
bool scanoutHook(Monitor::CMonitor* monitor) {
    for(auto& r:records)if(r->monitor.lock().get()==monitor && visible(r->monitor.lock()))return false;
    return originalScanout(monitor);
}
void eventHook(CEventManager* manager,const SHyprIPCEvent& event) {
    originalEvent(manager,event);
    if(event.event!="minimized" || stopping || mutating)return;
    const auto comma=event.data.find(',');if(comma==std::string::npos)return;
    for(auto& w:Desktop::windowState()->windows())if(std::format("{:x}",reinterpret_cast<uintptr_t>(w.get()))==event.data.substr(0,comma)){
        enqueue(w,event.data.substr(comma+1)=="1");break;
    }
}
template<typename T> void hook(const std::string& name,const std::string& signature,const void* replacement,T& original) {
    for(const auto& match:HyprlandAPI::findFunctionsByName(handle,name)) {
        if(match.demangled.find(signature)==std::string::npos)continue;
        auto h=HyprlandAPI::createFunctionHook(handle,match.address,replacement);
        if(!h || !h->hook())throw std::runtime_error("Cannot install Minimize hook: "+name);
        original=reinterpret_cast<T>(h->m_original);hooks.push_back(h);return;
    }
    throw std::runtime_error("Unsupported Minimize API: "+name);
}

#include "stacking.hpp"

Minimize::Settings readSettings() {
    const char* overridePath=std::getenv("XETAL_MINIMIZE_CONFIG");
    auto path=overridePath?std::filesystem::path(overridePath):std::filesystem::path(std::getenv("HOME"))/".config/hypr/effects/minimize/settings.conf";
    const char* colors=std::getenv("XETAL_MINIMIZE_COLORS");
    return Minimize::readSettings(path,colors?std::filesystem::path(colors):path.parent_path().parent_path().parent_path()/"theme/current.colors");
}
std::shared_ptr<Record> hit(Vector2D position) {
    if(g_pInputManager->isConstrained() || g_pInputManager->hasHeldButtons())return nullptr;
    for(auto& r:records)if(!r->restoring && visible(r->monitor.lock()))if(auto b=slot(*r)){
        if(box(*b).translate(r->monitor->m_position).containsPoint(position))return r;
    }
    return nullptr;
}
void tick(SP<CEventLoopTimer> self,void*) {
    if(stopping)return;
    auto queue=std::move(pending);pending.clear();
    for(auto& p:queue)if(auto w=p.window.lock()){
        try{if(p.minimize)minimize(w);else if(auto r=recordFor(w))restore(r);}
        catch(const std::exception& e){Log::logger->log(Log::ERR,"Minimize: {}",e.what());}
    }
    auto copy=records;
    for(auto& r:copy){
        refreshIcon(*r);
        const auto now=Clock::now();
        const double dt=std::chrono::duration<double>(now-r->lastFrame).count();r->lastFrame=now;
        if(visible(r->monitor.lock()) && (slot(*r) || !r->settled)) {
            const double step=std::clamp(dt,0.0,.1)*settings.speed/100.0;
            r->effectTime+=step;
            if(settings.effect=="fireball")r->fire.advance(step);
        }
        if(!member(*r)){finish(r,false);continue;}
        if(!online(r->monitor.lock())){r->monitor=fallback();r->settled=true;}
        if(r->restoring && progress(*r)>=1)finish(r,true);
        else if(progress(*r)>=1)r->settled=true;
    }
    damage(false);
    if(!pending.empty() || std::ranges::any_of(records,[](const auto& r){return !effectsHidden || !r->settled;}))
        self->updateTimeout(std::chrono::milliseconds(16));
}
void cleanup() {
    stopping=true;listeners.clear();pending.clear();
    if(ordinaryFocus)g_pKeybindManager->m_dispatchers["focuswindow"]=ordinaryFocus;
    Order::stop();
    if(timer){timer->cancel();g_pEventLoopManager->removeTimer(timer);timer.reset();}
    restoreAll();
    for(auto h:std::views::reverse(hooks))h->unhook();
    hooks.clear();
    g_pHyprRenderer->m_renderPass.removeAllOfType("XetalMinimize");
    graphics.release();
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle=h;stopping=false;effectsHidden=false;
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())throw std::runtime_error("Rebuild Minimize for this Hyprland ABI");
    if(g_pHyprRenderer->type()!=Render::IHyprRenderer::RT_GL)throw std::runtime_error("Minimize needs the OpenGL renderer");
    settings=readSettings();
    try {
        graphics.init();timer=makeShared<CEventLoopTimer>(std::nullopt,tick,nullptr);g_pEventLoopManager->addTimer(timer);
        hook("onUpdateState","CWindow::onUpdateState(",(void*)stateHook,originalState);
        hook("shouldRenderWindow","CSharedPointer<Monitor::CMonitor>",(void*)renderHook,originalRender);
        hook("attemptDirectScanout","CMonitor::attemptDirectScanout(",(void*)scanoutHook,originalScanout);
        hook("postEvent","CEventManager::postEvent(",(void*)eventHook,originalEvent);
        Order::init();
        ordinaryFocus=g_pKeybindManager->m_dispatchers.at("focuswindow");
        g_pKeybindManager->m_dispatchers["focuswindow"]=[](std::string args){
            auto w=Desktop::viewState()->query().selector(args).runWindow();
            // Restore the requested taskbar icon before the core opens the
            // shared stash and briefly focuses its other minimized clients.
            if(w && recordFor(w)){enqueue(w,false);return SDispatchResult{};}
            return ordinaryFocus(args);
        };
        listeners.push_back(Event::bus()->m_events.render.stage.listen([](eRenderStage stage){
            if(stage!=RENDER_LAST_MOMENT || capturing || g_pHyprRenderer->m_bRenderingSnapshot)return;
            auto m=g_pHyprRenderer->m_renderData.pMonitor.lock();if(visible(m))g_pHyprRenderer->addPassElement(makeUnique<MinimizePass>(m));
        }));
        listeners.push_back(Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent e,Event::SCallbackInfo& info){
            if(e.state==WL_POINTER_BUTTON_STATE_RELEASED && consumedButtons.erase(e.button)){info.cancelled=true;return;}
            if(info.cancelled || e.button!=BTN_LEFT || e.state!=WL_POINTER_BUTTON_STATE_PRESSED)return;
            if(auto r=hit(Pointer::mgr()->position())){info.cancelled=true;consumedButtons.insert(e.button);enqueue(member(*r),false);}
        }));
        listeners.push_back(Event::bus()->m_events.input.mouse.axis.listen([](IPointer::SAxisEvent e,Event::SCallbackInfo& info){
            if(info.cancelled || e.axis!=WL_POINTER_AXIS_VERTICAL_SCROLL)return;
            if(auto r=hit(Pointer::mgr()->position())){auto m=r->monitor.lock();scroll[m->m_id]+=(e.delta>0?1:-1);column(m);damage();info.cancelled=true;}
        }));
        listeners.push_back(Event::bus()->m_events.window.active.listen([](PHLWINDOW w,Desktop::eFocusReason){
            if(auto r=recordFor(w);r && !r->restoring)enqueue(w,false);
        }));
        listeners.push_back(Event::bus()->m_events.window.close.listen([](PHLWINDOW){arm();}));
        listeners.push_back(Event::bus()->m_events.monitor.layoutChanged.listen([](){arm();}));
        // Restore before the core removes outputs, including the last one. Its
        // normal workspace migration then keeps every app reachable on return.
        listeners.push_back(Event::bus()->m_events.monitor.preRemoved.listen([](PHLMONITOR){restoreAll();}));
        HyprlandAPI::addDispatcherV2(handle,"xetalminimize:minimize",[](std::string){enqueue(Desktop::focusState()->window(),true);return SDispatchResult{};});
        HyprlandAPI::addDispatcherV2(handle,"xetalminimize:togglevisibility",[](std::string){toggleVisibility();return SDispatchResult{};});
        HyprlandAPI::addDispatcherV2(handle,"xetalminimize:restoreall",[](std::string){restoreAll();return SDispatchResult{};});
        HyprlandAPI::addDispatcherV2(handle,"xetalminimize:restore",[](std::string id){
            for(auto& r:records)if(id==std::to_string(r->id)){enqueue(member(*r),false);return SDispatchResult{};}
            return SDispatchResult{.success=false,.error="No minimized window with that ID"};
        });
        HyprlandAPI::addDispatcherV2(handle,"xetalminimize:reload",[](std::string){
            try{auto next=readSettings();if(!next.enabled)restoreAll();settings=next;damage();arm();return SDispatchResult{};}
            catch(const std::exception& e){return SDispatchResult{.success=false,.error=e.what()};}
        });
        statusCommand=HyprlandAPI::registerHyprCtlCommand(handle,{"xetal-minimize",true,[](eHyprCtlOutputFormat,std::string){
            std::string items;for(auto& r:records){auto b=slot(*r);if(!items.empty())items+=",";
                items+=std::format("{{\"id\":{},\"workspace\":{},\"restoring\":{},\"visible\":{},\"icon\":{},\"box\":[{},{},{},{}]}}",r->id,r->original?r->original->m_id:0,r->restoring,visible(r->monitor.lock()) && b.has_value(),bool(r->appIcon),b?b->x:0,b?b->y:0,b?b->w:0,b?b->h:0);
            }
            return std::format("{{\"enabled\":{},\"hidden\":{},\"effect\":\"{}\",\"edge\":\"{}\",\"order\":\"{}\",\"shape\":{},\"surface\":{},\"color\":[{},{},{}],\"active\":{},\"minimized\":{},\"restored\":{},\"draws\":{},\"windows\":[{}]}}",settings.enabled,effectsHidden,settings.effect,settings.rightEdge?"right":"left",settings.bottomToTop?"bottom-to-top":"top-to-bottom",settings.shape,settings.surface,settings.rgb[0],settings.rgb[1],settings.rgb[2],records.size(),requests,restored,draws,items);
        }});
    }catch(...){cleanup();throw;}
    return {"Xetal Minimize","Fireball and living Splat minimize effects","XetalEngine","1.2"};
}
APICALL EXPORT void PLUGIN_EXIT(){cleanup();}
