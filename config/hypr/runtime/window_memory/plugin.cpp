// SPDX-License-Identifier: GPL-2.0-or-later
// Typed window memory, launch intent and client-decoration geometry.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/protocols/core/Subcompositor.hpp>
#include <hyprland/src/desktop/view/Subsurface.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/desktop/view/Popup.hpp>
#include <hyprland/src/desktop/view/WLSurface.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/state/FloatState.hpp>
#include <hyprland/src/layout/LayoutManager.hpp>
#include <hyprland/src/layout/target/Target.hpp>
#include <hyprland/src/layout/space/Space.hpp>
#include <hyprland/src/layout/algorithm/Algorithm.hpp>
#include <hyprland/src/layout/algorithm/FloatingAlgorithm.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include "../../workspaces/native.hpp"
#include "../window_types_native.hpp"
#include "inspector.hpp"
#include "../../effects/window_close/native/geometry.hpp"
#include "initial_memory.hpp"
#include <sstream>

namespace {
SP<SHyprCtlCommand> metadataCommand, stateCommand, inspectorCommand, memorySourceCommand;
std::filesystem::path memorySource;
std::map<uint64_t, InitialMemory::Plan> initialPlans;
CHyprSignalListener mappedListener;
std::vector<CHyprSignalListener> policyListeners;
WorkspaceRules::Policies workspaceRules;
SP<CEventLoopTimer> policyTimer;
std::vector<PHLWINDOWREF> pendingPolicies;
std::vector<CFunctionHook*> hooks;
void cleanup(){
    initialPlans.clear();
    mappedListener.reset();
    policyListeners.clear();pendingPolicies.clear();
    if(policyTimer){policyTimer->cancel();g_pEventLoopManager->removeTimer(policyTimer);policyTimer.reset();}
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
WorkspaceRules::Policy workspacePolicy(PHLWINDOW w){
    if(!WindowTypes::geometryManaged(w)||!w->m_workspace||w->m_class=="fusion-window-buttons")return {};
    return WorkspaceRules::forWorkspace(workspaceRules,w->m_workspace->m_id);
}
#include "stacking.hpp"
using FloatingFn=void (*)(Layout::CLayoutManager*,SP<Layout::ITarget>);
FloatingFn originalFloating;
void queuePolicy(PHLWINDOW w);
void floatingHook(Layout::CLayoutManager* manager,SP<Layout::ITarget> target){
    const auto policy=workspacePolicy(target?target->window():nullptr);
    // Native tiled dragging temporarily floats the target to reorder it. Let
    // that gesture finish, then enforce the destination workspace's policy.
    if(policy.layout=="tile"&&g_layoutManager->dragController()->target()==target){
        originalFloating(manager,target);queuePolicy(target->window());return;
    }
    // Refuse contradictory requests before the layout changes. A later polling
    // correction would visibly bounce between tiled and floating geometry.
    if(policy.layout!="off"&&target->floating()==WorkspaceRules::floats(policy))return;
    originalFloating(manager,target);
}
void enforcePolicy(PHLWINDOW w,bool initial=false){
    if(!w||!w->m_isMapped||w->isHidden())return;
    const auto policy=workspacePolicy(w);if(policy.layout=="off")return;
    auto target=w->layoutTarget();if(!target||!target->space())return;
    if(g_layoutManager->dragController()->target()==target){
        queuePolicy(w);policyTimer->updateTimeout(std::chrono::milliseconds(25));return;
    }
    const bool floating=WorkspaceRules::floats(policy),wasTiled=!target->floating();
    auto saved=target->lastFloatingSize();const auto before=target->position();
    // Clear startup maximization only when applying/entering a forced layout.
    // Subsequent native maximize/restore requests remain functional.
    Fullscreen::controller()->setFullscreenMode(w,Fullscreen::FSMODE_NONE,Fullscreen::FSMODE_NONE);
    if(floating!=target->floating())g_layoutManager->changeFloatingMode(target);
    if(floating&&target->floating()){
        if(const auto cached=Desktop::floatState()->get(w);cached&&(!WindowButtons::valid({saved.x,saved.y})||initial))saved=*cached;
        auto work=target->space()->workArea(true);const auto ext=w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
        work.x+=ext.topLeft.x;work.y+=ext.topLeft.y;work.w-=ext.topLeft.x+ext.bottomRight.x;work.h-=ext.topLeft.y+ext.bottomRight.y;
        work.expand(-std::min({16.,work.w*.04,work.h*.04}));
        if(work.w>1&&work.h>1){
            const auto minimum=target->minSize().value_or(Vector2D{}),maximum=target->maxSize().value_or(Vector2D{});
            const auto fit=WindowButtons::restore({work.x,work.y,work.w,work.h},{before.x,before.y,before.w,before.h},
                {saved.x,saved.y},{minimum.x,minimum.y},{maximum.x,maximum.y},wasTiled);
            target->space()->algorithm()->floatingAlgo()->setTargetGeom(CBox{fit.x,fit.y,fit.w,fit.h},target);
            target->rememberFloatingSize({fit.w,fit.h});
        }
    }
    if(initial)target->warpPositionSize();
    WorkspaceStack::reconcile(w->m_workspace);
}
void queuePolicy(PHLWINDOW w){
    if(workspacePolicy(w).layout=="off")return;
    if(!std::ranges::any_of(pendingPolicies,[&](auto weak){return weak.lock()==w;}))pendingPolicies.push_back(w);
    if(policyTimer)policyTimer->updateTimeout(std::chrono::milliseconds(1));
}
using SurfaceAtFn=SP<CWLSurfaceResource> (*)(const Desktop::CViewHitTester*,const Vector2D&,PHLWINDOW,Vector2D&);
using SurfaceBoxFn=std::optional<CBox> (*)(const Desktop::View::CWLSurface*);
using SurfaceDamageFn=CRegion (*)(const Desktop::View::CWLSurface*);
using SubsurfaceCoordsFn=Vector2D (*)(const Desktop::View::CSubsurface*);
SurfaceAtFn originalSurfaceAt;
SurfaceBoxFn originalSurfaceBox;
SurfaceDamageFn originalSurfaceDamage;
SubsurfaceCoordsFn originalSubsurfaceCoords;
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
CRegion surfaceDamageHook(const Desktop::View::CWLSurface* surface){
    const auto w=Desktop::View::CWindow::fromView(surface->view());
    const auto offset=contentOffset(w);
    if(!w||w->m_isX11||w->wlSurface().get()!=surface||offset==Vector2D{})
        return originalSurfaceDamage(surface);
    auto& state=surface->resource()->m_current;
    if(!state.texture||state.bufferSize.x<=0||state.bufferSize.y<=0||state.size.x<=0||state.size.y<=0)return {};
    // Match the pinned core's buffer/viewport normalization, but postpone its
    // window-size clip until after removing the padding. Translating core's
    // already-clipped result loses right/bottom updates. Its internal bounds
    // lookup is inlined, so the input-origin hook cannot change that ordering.
    CRegion damage=state.accumulateBufferDamage();
    damage.transform(Math::wlTransformToHyprutils(state.transform),state.bufferSize.x,state.bufferSize.y);
    if(state.viewport.hasSource)damage.intersect(state.viewport.source);
    const auto sourceSize=state.viewport.hasSource?state.viewport.source.size()*state.scale:state.bufferSize;
    if(sourceSize.x<=0||sourceSize.y<=0)return {};
    damage.scale(state.bufferSize/sourceSize);
    damage.translate(surface->correctSmallVecBuf());
    damage.scale(state.size/state.bufferSize);
    // The renderer UV-crops the main surface to xdg geometry. Typing damages
    // only small rectangles, which must reach that same visible origin. Full
    // repaints (including screen capture) otherwise conceal the stale pixels.
    damage.intersect(w->m_xdgSurface->m_current.geometry).translate(-offset);
    if(const auto box=originalSurfaceBox(surface))damage.intersect(CBox{{},box->size()});
    return damage;
}
Vector2D subsurfaceCoordsHook(const Desktop::View::CSubsurface* subsurface){
    auto coords=originalSubsurfaceCoords(subsurface);
    auto resource=subsurface->wlSurface()?subsurface->wlSurface()->resource():nullptr;
    for(int depth=0;resource&&depth<32;++depth) {
        const auto role=dynamicPointerCast<CSubsurfaceRole>(resource->m_role);
        if(!role)break;
        const auto sub=role->m_subsurface.lock();
        resource=sub?sub->m_parent.lock():nullptr;
    }
    const auto parent=Desktop::View::CWLSurface::fromResource(resource);
    // Root-window children share the main surface's geometry offset. Correct
    // both damage and held-pointer motion, which use these global coordinates.
    // Popup children already inherit their popup's corrected global position.
    const auto w=parent?Desktop::View::CWindow::fromView(parent->view()):nullptr;
    return coords-contentOffset(w);
}

uint64_t hash(const std::string& value) {
    uint64_t result = 14695981039346656037ULL;
    for (unsigned char byte : value) { result ^= byte; result *= 1099511628211ULL; }
    return result;
}
struct MemoryFacts {
    bool dialog = false, fixed = false, picker = false, transfer = false;
    std::string role, app;
};
MemoryFacts memoryFacts(PHLWINDOW w) {
    const auto xdg = w->m_xdgSurface.lock();
    const auto top = xdg ? xdg->m_toplevel.lock() : nullptr;
    const auto x11 = w->m_xwaylandSurface.lock();
    MemoryFacts facts;
    facts.dialog = w->parent() || (top && top->m_dialog.lock());
    facts.fixed = top && top->m_current.minSize.x > 0 && top->m_current.minSize.y > 0 &&
                  top->m_current.minSize == top->m_current.maxSize;
    facts.role = std::format("{:016x}", hash(x11 && !x11->m_role.empty() ? x11->m_role : facts.dialog ? w->m_initialTitle : "main"));
    facts.app = w->m_initialClass.empty() ? w->m_class : w->m_initialClass;
    if (facts.app.empty()) {
        std::error_code error;
        facts.app = std::filesystem::read_symlink(std::format("/proc/{}/exe", w->getPID()), error).string();
    }
    facts.picker = w->m_class.starts_with("xetal-file-picker");
    facts.transfer = (w->m_class == "xetal-files" || w->m_class == "xetal-files-external") &&
                     (w->m_initialTitle.empty() ? w->m_title : w->m_initialTitle) == "Transfer queue — Fusion Files";
    return facts;
}
bool explicitMemoryMode(PHLWINDOW w, const MemoryFacts& facts) {
    if (workspacePolicy(w).layout != "off" || facts.picker || facts.transfer ||
        ((w->m_class == "xetal-files" || w->m_class == "xetal-files-external") && !facts.dialog)) return true;
    for (const auto& value : w->m_ruleApplicator->m_tagKeeper.getTags()) {
        std::string_view tag(value);
        if (tag.ends_with('*')) tag.remove_suffix(1);
        if (tag == "fusion-managed-rule" || tag.starts_with("xetal-float-") || tag.starts_with("xetal-tile-")) return true;
    }
    return false;
}
InitialMemory::Rect memoryRectangle(PHLWINDOW w, const InitialMemory::Record& saved) {
    auto target = w->layoutTarget();
    const auto work = w->m_workspace->m_space->workArea(true);
    auto current = target->position();
    // Before the target joins a layout, use the client's requested normal size.
    if (!target->space()) {
        const auto desired = target->desiredGeometry();
        const auto size = desired ? desired->size : Vector2D{saved.normalSize->w, saved.normalSize->h};
        current = CBox{desired && desired->pos ? *desired->pos : work.middle() - size / 2, size};
    }
    const auto minimum = target->minSize().value_or(Vector2D{}), maximum = target->maxSize().value_or(Vector2D{});
    const auto ext = w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS | Desktop::View::INPUT_EXTENTS);
    return InitialMemory::fit(saved, {work.x, work.y, work.w, work.h},
        {current.x, current.y, current.w, current.h}, {minimum.x, minimum.y}, {maximum.x, maximum.y},
        memoryFacts(w).fixed, {ext.topLeft.x, ext.topLeft.y, ext.bottomRight.x, ext.bottomRight.y});
}
void prepareInitialMemory(PHLWINDOW w) {
    if (!WindowTypes::geometryManaged(w) || !w->m_workspace || !w->m_workspace->m_space ||
        !w->layoutTarget() || workspacePolicy(w).layout == "tile") return;
    const auto facts = memoryFacts(w);
    const auto key = InitialMemory::identity(facts.app, facts.role, facts.dialog, facts.picker, facts.transfer);
    const auto saved = InitialMemory::read(memorySource, key);
    if (!saved) return;
    const auto plan = InitialMemory::plan(*saved, explicitMemoryMode(w, facts), w->m_isFloating);
    initialPlans[w->m_stableID] = plan;
    // The pinned core emits openEarly immediately before newTarget(). Set its
    // first layout choice here, not through an IPC move after the window opens.
    if (plan.restoreMode) w->layoutTarget()->setFloating(plan.floating);
    if (!plan.floating || !saved->normalSize) return;
    const auto rect = memoryRectangle(w, *saved);
    if (!facts.fixed)
        w->m_ruleApplicator->static_.size = Math::SExpressionVec2{std::to_string(rect.w), std::to_string(rect.h)};
    const auto monitor = w->m_monitor.lock();
    if (monitor) {
        const auto origin = monitor->logicalBox().pos();
        w->m_ruleApplicator->static_.position = Math::SExpressionVec2{std::to_string(rect.x - origin.x), std::to_string(rect.y - origin.y)};
        w->m_ruleApplicator->static_.center = false;
    }
    w->layoutTarget()->rememberFloatingSize({rect.w, rect.h});
}
void finishInitialMemory(PHLWINDOW w) {
    const auto found = initialPlans.find(w->m_stableID);
    if (found == initialPlans.end()) return;
    const auto plan = found->second; initialPlans.erase(found);
    if (!w->m_isMapped || !WindowTypes::geometryManaged(w) || !w->layoutTarget() ||
        !w->layoutTarget()->space() || workspacePolicy(w).layout == "tile") return;
    const bool mode = plan.restoreMode && !explicitMemoryMode(w, memoryFacts(w));
    if (mode) Fullscreen::controller()->setFullscreenMode(w, Fullscreen::FSMODE_NONE, Fullscreen::FSMODE_NONE);
    const auto fullscreen = Fullscreen::controller()->getFullscreenModes(w);
    // openLate is still inside mapWindow(), before any frame. Final decoration
    // extents and forced-layout constraints are now available. No timer/retry.
    if (plan.floating && w->layoutTarget()->floating() && plan.saved.normalSize &&
        fullscreen.internal == Fullscreen::FSMODE_NONE && fullscreen.client == Fullscreen::FSMODE_NONE) {
        const auto rect = memoryRectangle(w, plan.saved);
        auto target = w->layoutTarget();
        target->space()->algorithm()->floatingAlgo()->setTargetGeom(CBox{rect.x, rect.y, rect.w, rect.h}, target);
        target->rememberFloatingSize({rect.w, rect.h});
    }
    if (mode)
        Fullscreen::controller()->setFullscreenMode(w, static_cast<Fullscreen::eFullscreenMode>(plan.saved.fullscreen),
                                                    static_cast<Fullscreen::eFullscreenMode>(plan.saved.clientFullscreen));
    w->layoutTarget()->warpPositionSize();
}
std::string metadata() {
    std::string result = "{";
    for (const auto& window : Desktop::windowState()->windows()) {
        if (!window->m_isMapped) continue;
        const auto facts = memoryFacts(window);
        if (result.size() > 1) result += ',';
        result += std::format("\"0x{:x}\":{{\"dialog\":{},\"fixed\":{},\"role\":\"{}\",\"workspace_layout\":\"{}\",\"initial_memory\":true,\"geometry_managed\":{},\"stableId\":\"{:x}\"}}",
                              reinterpret_cast<uintptr_t>(window.get()), facts.dialog, facts.fixed, facts.role,workspacePolicy(window).layout,
                              WindowTypes::geometryManaged(window), window->m_stableID);
    }
    return result + '}';
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Rebuild window memory for this compositor ABI");
    memorySource = std::filesystem::path(std::getenv("HOME")) / ".config/hypr/runtime/window_memory/state/windows.json";
    memorySourceCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-memory-source", false,
        [](eHyprCtlOutputFormat, std::string input) {
            const auto separator = input.find(' ');
            if (separator == std::string::npos) return std::string("missing memory path");
            const auto path = input.substr(separator + 1);
            if (path.empty() || path.size() > 4096 || path.find_first_of("\r\n") != std::string::npos || !std::filesystem::path(path).is_absolute())
                return std::string("invalid memory path");
            memorySource = path;
            return std::string("ok");
        }});
    metadataCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-windows", true,
        [](eHyprCtlOutputFormat, std::string) { return metadata(); }});
    inspectorCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-inspector-surfaces", true,
        [](eHyprCtlOutputFormat, std::string) { return WindowInspector::surfaces(); }});
    stateCommand = HyprlandAPI::registerHyprCtlCommand(handle, {"xetal-window-state", false,
        [](eHyprCtlOutputFormat, std::string input) {
            std::istringstream args(input);
            std::string command, address, extra;
            int internal = -1, client = -1;
            args >> command >> address >> internal >> client;
            if (args.fail() || (args >> extra) || internal < 0 || internal > 2 || client < 0 || client > 2)
                return std::string("invalid state");
            for (const auto& window : Desktop::windowState()->windows()) {
                if (!window->m_isMapped || !WindowTypes::geometryManaged(window) ||
                    address != std::format("0x{:x}", reinterpret_cast<uintptr_t>(window.get()))) continue;
                Fullscreen::controller()->setFullscreenMode(window, static_cast<Fullscreen::eFullscreenMode>(internal),
                                                            static_cast<Fullscreen::eFullscreenMode>(client));
                return std::string("ok");
            }
            return std::string("window not found");
        }});
    try{
        workspaceRules=WorkspaceRules::read();
        policyTimer=makeShared<CEventLoopTimer>(std::nullopt,[](SP<CEventLoopTimer>,void*){
            auto work=std::move(pendingPolicies);pendingPolicies.clear();
            for(auto weak:work)enforcePolicy(weak.lock());
        },nullptr);g_pEventLoopManager->addTimer(policyTimer);
        hook(handle,"changeFloatingMode","CLayoutManager::changeFloatingMode(",(void*)floatingHook,originalFloating);
        hook(handle,"moveToZ","CWindowState::moveToZ(",(void*)WorkspaceStack::move,WorkspaceStack::originalMove);
        hook(handle,"windowSurfaceAt","CViewHitTester::windowSurfaceAt(",(void*)surfaceAtHook,originalSurfaceAt);
        hook(handle,"getSurfaceBoxGlobal","CWLSurface::getSurfaceBoxGlobal(",(void*)surfaceBoxHook,originalSurfaceBox);
        hook(handle,"computeDamage","CWLSurface::computeDamage(",(void*)surfaceDamageHook,originalSurfaceDamage);
        hook(handle,"coordsGlobal","CSubsurface::coordsGlobal(",(void*)subsurfaceCoordsHook,originalSubsurfaceCoords);
        policyListeners.push_back(Event::bus()->m_events.window.openEarly.listen([](PHLWINDOW w){
            const auto policy=workspacePolicy(w);
            if(policy.layout!="off") {
                if(auto target=w->layoutTarget())target->setFloating(WorkspaceRules::floats(policy));
                else w->m_isFloating=WorkspaceRules::floats(policy);
            }
            try { prepareInitialMemory(w); }
            catch (const std::exception& error) { initialPlans.erase(w->m_stableID); }
        }));
        policyListeners.push_back(Event::bus()->m_events.window.moveToWorkspace.listen([](PHLWINDOW w,PHLWORKSPACE){queuePolicy(w);}));
        policyListeners.push_back(Event::bus()->m_events.window.fullscreen.listen([](PHLWINDOW w){
            if(w)WorkspaceStack::reconcile(w->m_workspace);
        }));
        HyprlandAPI::addDispatcherV2(handle,"xetalworkspaces:reload",[](std::string){
            try{
                auto next=WorkspaceRules::read();auto previous=std::move(workspaceRules);workspaceRules=std::move(next);
                for(const auto& w:Desktop::windowState()->windows())if(w->m_workspace&&
                    WorkspaceRules::forWorkspace(previous,w->m_workspace->m_id).layout!=workspacePolicy(w).layout)enforcePolicy(w);
                return SDispatchResult{};
            }catch(const std::exception& error){return SDispatchResult{.success=false,.error=error.what()};}
        });
        mappedListener = Event::bus()->m_events.window.openLate.listen([](PHLWINDOW w){
            if (w && (!w->m_isMapped || !WindowTypes::geometryManaged(w))) initialPlans.erase(w->m_stableID);
            if(w&&w->m_isMapped&&WindowTypes::geometryManaged(w)){
                enforcePolicy(w,true);
                try { finishInitialMemory(w); }
                catch (const std::exception& error) { initialPlans.erase(w->m_stableID); }
                const auto& tags=w->m_ruleApplicator->m_tagKeeper.getTags();
                const bool launched=std::ranges::any_of(tags,[](const auto& tag){return tag.starts_with("xetal-tile-")||tag.starts_with("xetal-float-");});
                if(launched&&w->m_ruleApplicator->static_.fullscreenStateInternal==0&&w->m_ruleApplicator->static_.fullscreenStateClient==0)
                    // fullscreen_state is only our initial choice. Core turns
                    // sync off for that rule; restore it so later native
                    // maximize/restore buttons remain fully functional.
                    w->m_ruleApplicator->syncFullscreenOverride(Desktop::Types::COverridableVar(true,Desktop::Types::PRIORITY_WINDOW_RULE));
            }
        });
        // Loading an updated adapter must not unmaximize or resize windows
        // which already obey their workspace policy.
        for(const auto& w:Desktop::windowState()->windows()){
            const auto policy=workspacePolicy(w);auto target=w->layoutTarget();
            if(policy.layout!="off"&&target&&target->floating()!=WorkspaceRules::floats(policy))enforcePolicy(w);
        }
        std::set<WORKSPACEID> reconciled;
        for(const auto& w:Desktop::windowState()->windows())if(w->m_workspace&&reconciled.insert(w->m_workspace->m_id).second)
            WorkspaceStack::reconcile(w->m_workspace);
    }catch(...){cleanup();throw;}
    return {"Xetal Window Memory", "Initial placement, workspace policies and decoration input", "XetalEngine", "1.6"};
}
APICALL EXPORT void PLUGIN_EXIT() { cleanup(); }
