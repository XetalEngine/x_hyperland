// SPDX-License-Identifier: GPL-2.0-or-later
// Included in the controls plugin. No FBOs, input overlays, or polling IPC.
namespace KDESnap {
using namespace SnapGeometry;
using Drag=Layout::Supplementary::CDragStateController;
struct Saved {PHLWINDOWREF window;Box normal,snapped;};
std::map<uint64_t,Saved> saved;
struct Gesture {
    PHLWINDOWREF window;PHLMONITORREF monitor;
    Box normal,preview,panel;Zone zone=NoSnap;Clock::time_point entered;
    bool palette=false,released=false,cancelled=false,threshold=false,armed=false;
} gesture;
bool enabled=true;
bool ready=false;
std::vector<CFunctionHook*> hooks;
using BeginFn=void(*)(Layout::CLayoutManager*,SP<Layout::ITarget>,eMouseBindMode,std::optional<Layout::eRectCorner>,bool);
using UpdateFn=bool(*)(Drag*);
BeginFn originalBegin=nullptr;UpdateFn originalUpdate=nullptr;
Box box(CBox b){return {b.x,b.y,b.w,b.h};}
CBox native(Box b){return {b.x,b.y,b.w,b.h};}
bool usable(PHLWINDOW w){
    if(!ready||!enabled||stopping||!g_pCompositor->m_sessionActive||g_pSessionLockManager->isSessionLocked()||PROTO::inputCapture->isCaptured()||PROTO::data->dndActive()||
       !w||!w->mapped()||w->isHidden()||!w->isFloating()||Fusion057::pinned(w)||w->grouping().group()||!kdeMode(w)||!WindowTypes::geometryManaged(w))return false;
    // Dialogs and authentication prompts keep the application's placement.
    if(auto xdg=Fusion057::xdg(w).lock();xdg&&xdg->m_toplevel&&xdg->m_toplevel->m_parent.lock())return false;
    if(auto x11=Fusion057::x11(w).lock();x11&&x11->m_parent.lock())return false;
    return Fullscreen::controller()->getFullscreenModes(w).internal==Fullscreen::FSMODE_NONE;
}
void damage(){
    if(valid(gesture.preview))g_pHyprRenderer->damageBox(native(gesture.preview).expand(3));
    if(valid(gesture.panel))g_pHyprRenderer->damageBox(native(gesture.panel).expand(3));
}
void clear(){damage();gesture={};}
void load(){
    std::ifstream file(root()/"effects/window_close/snap-settings.json");
    if(!file){enabled=true;return;}
    std::string text((std::istreambuf_iterator<char>(file)),{});
    if(text.size()>1024)throw std::runtime_error("Snap settings are too large");
    auto doc=WindowButtons::parseJson(text);
    if(json_object_object_length(doc.get())!=1)throw std::runtime_error("Invalid snap settings");
    enabled=json_object_get_boolean(WindowButtons::field(doc.get(),"enabled",json_type_boolean));
    if(!enabled)clear();
}
std::optional<Box> fit(PHLWINDOW w,Box outer){
    auto t=w->layoutTarget();if(!t)return std::nullopt;
    const auto extents=w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
    const auto low=t->minSize().value_or(Vector2D{}),high=t->maxSize().value_or(Vector2D{});
    return client(outer,{extents.topLeft.x,extents.topLeft.y},{extents.bottomRight.x,extents.bottomRight.y},{low.x,low.y},{high.x,high.y});
}
void sample(bool releasing=false);
void motion();
bool update(Drag* drag){
    auto t=drag->target();auto w=t?t->window():nullptr;
    if(w&&drag->mode()==MBIND_MOVE&&drag->dragThresholdReached()&&usable(w)&&t->space()){
        auto it=saved.find(w->metadata().stableID());
        if(it!=saved.end()){
            const auto memory=it->second;saved.erase(it);
            if(memory.window.lock()==w&&same(memory.snapped,box(t->position()))){
                const auto p=Pointer::mgr()->position();
                const auto extents=w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
                auto work=client(box(t->space()->workArea(true)),{extents.topLeft.x,extents.topLeft.y},{extents.bottomRight.x,extents.bottomRight.y},{},{});
                if(work){
                    auto restored=restore(memory.normal,memory.snapped,*work,{p.x,p.y});
                    const auto minimum=t->minSize().value_or(Vector2D{}),maximum=t->maxSize().value_or(Vector2D{});
                    if(client(restored,{},{},{minimum.x,minimum.y},{maximum.x,maximum.y})){
                        t->space()->algorithm()->floatingAlgo()->setTargetGeom(native(restored),t);
                        t->warpPositionSize();t->rememberFloatingSize({restored.w,restored.h});gesture.normal=restored;
                    }
                }
            }
        }
    }
    // This initializes the native grab AFTER restoring. Wobbly's separate
    // dragBegin hook then grabs the restored geometry in either load order.
    const bool rejected=originalUpdate(drag);
    if(!rejected)motion();
    return rejected;
}
void begin(Layout::CLayoutManager* manager,SP<Layout::ITarget> t,eMouseBindMode mode,std::optional<Layout::eRectCorner> edge,bool exclusive){
    clear();auto w=t?t->window():nullptr;
    if(usable(w)&&mode==MBIND_MOVE){gesture.window=w;gesture.normal=box(t->position());}
    else if(w)saved.erase(w->metadata().stableID());
    originalBegin(manager,t,mode,edge,exclusive);
    if(g_layoutManager->dragController()->target()!=t)clear();
    else motion();
    arm();
}
// Native/client-side drags can become usable only after the compositor has
// initialized the grab. Adopt that first motion as well as beginDragTarget.
void motion(){
    auto* drag=g_layoutManager->dragController().get();auto t=drag->target();auto w=t?t->window():nullptr;
    if(!gesture.window.lock()&&drag->mode()==MBIND_MOVE&&usable(w)){
        clear();
        gesture.window=w;gesture.normal=box(t->position());
    }
    sample();arm();
}
void sample(bool releasing){
    auto w=gesture.window.lock();auto* drag=g_layoutManager->dragController().get();
    if(!w||gesture.cancelled||gesture.released)return;
    // Some input paths finish the native grab before delivering button release.
    // Keep its last threshold state and hit-test the release point in that case.
    if(!usable(w)||(drag->target()&&(drag->target()->window()!=w||drag->mode()!=MBIND_MOVE))||(!releasing&&!drag->target())){clear();return;}
    if(drag->target())gesture.threshold=drag->dragThresholdReached();
    const auto point=Pointer::mgr()->position();auto m=State::monitorState()->query().vec(point).run();
    auto ws=m?m->m_activeWorkspace:nullptr;
    if(!m||!ws||m->m_activeSpecialWorkspace||WorkspaceRules::forWorkspace(workspaceRules,Fusion057::numberedID(ws)).layout!="kde"||!ws->space()){
        damage();gesture.preview={};gesture.panel={};gesture.palette=false;gesture.zone=NoSnap;return;
    }
    const auto work=box(ws->space()->workArea(true));const auto monitor=box(m->logicalBox());
    if(!contains(monitor,{point.x,point.y})){
        damage();gesture.preview={};gesture.panel={};gesture.palette=false;gesture.zone=NoSnap;return;
    }
    damage();
    if(gesture.monitor.lock()!=m){gesture.palette=false;gesture.zone=NoSnap;gesture.preview={};}
    gesture.monitor=m;
    const auto panel=palette(work);
    Zone next=edge(monitor,work,{point.x,point.y});
    const bool bypass=(uint32_t(g_pInputManager->getModsFromAllKBs())&4)!=0; // Ctrl held before the drag bypasses layout snapping.
    if(!bypass&&gesture.threshold){
        if(next==SnapGeometry::Maximize)gesture.palette=true;
        if(gesture.palette){
            Box vicinity{panel.x-30,monitor.y,panel.w+60,panel.y+panel.h+24-monitor.y};
            if(!contains(vicinity,{point.x,point.y}))gesture.palette=false;
        }
        if(gesture.palette)for(const auto& cell:cells(panel))if(contains(cell.box,{point.x,point.y})){next=cell.zone;break;}
    }else {next=NoSnap;gesture.palette=false;}
    gesture.panel=gesture.palette?panel:Box{};
    const auto outer=region(work,next);
    auto preview=fit(w,outer);if(!preview)next=NoSnap;
    const Box rect=next==NoSnap?Box{}:outer;
    if(next!=gesture.zone||!same(rect,gesture.preview)){gesture.entered=Clock::now();gesture.zone=next;}
    gesture.preview=rect;damage();
}
void layoutChanged(){
    // Output initialization/hotplug must not discard a grab already in flight.
    damage();gesture.monitor.reset();gesture.preview={};gesture.panel={};gesture.palette=false;gesture.zone=NoSnap;
    sample();
}
std::string status(){
    const auto& g=gesture;
    return std::format("\"snap_gesture\":{{\"active\":{},\"threshold\":{},\"zone\":{},\"preview\":[{},{},{},{}],\"panel\":[{},{},{},{}]}},",
        bool(g.window.lock()),g.threshold,int(g.zone),g.preview.x,g.preview.y,g.preview.w,g.preview.h,g.panel.x,g.panel.y,g.panel.w,g.panel.h);
}
void release(IPointer::SButtonEvent event){
    if(event.button!=BTN_LEFT||event.state!=WL_POINTER_BUTTON_STATE_RELEASED||!gesture.window.lock())return;
    sample(true);gesture.armed=gesture.zone!=NoSnap&&Clock::now()-gesture.entered>=std::chrono::milliseconds(180);
    gesture.released=true;arm();
}
void tick(){
    auto w=gesture.window.lock();if(!w)return;
    auto* drag=g_layoutManager->dragController().get();
    if(drag->target()&&drag->target()->window()==w){sample();return;}
    const auto finished=gesture;clear();
    if(!finished.released||finished.cancelled||!finished.threshold||!finished.armed||!usable(w))return;
    auto m=finished.monitor.lock();auto ws=m?m->m_activeWorkspace:nullptr;
    if(!ws||m->m_activeSpecialWorkspace||WorkspaceRules::forWorkspace(workspaceRules,Fusion057::numberedID(ws)).layout!="kde"||!ws->space())return;
    const auto normal=finished.normal;
    if(!valid(normal))return;
    if(w->m_workspace!=ws)Desktop::globalWindowController()->moveWindowToWorkspace(w,ws);
    auto t=w->layoutTarget();if(!usable(w)||!t||!t->floating()||!t->space())return;
    // Recompute after monitor/workspace handoff and decoration recalculation.
    auto result=fit(w,region(box(t->space()->workArea(true)),finished.zone));if(!result)return;
    if(finished.zone==SnapGeometry::Maximize){
        // Maximize through the regular window state so restore/title-bar buttons
        // behave normally. Preserve the pre-drag rectangle, not the edge grab.
        saved.erase(w->metadata().stableID());
        const auto work=box(t->space()->workArea(true));
        const auto extents=w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
        const auto available=client(work,{extents.topLeft.x,extents.topLeft.y},{extents.bottomRight.x,extents.bottomRight.y},{},{});
        if(!available)return;
        const Box restored{std::clamp(normal.x,available->x,available->x+std::max(0.,available->w-normal.w)),
                           std::clamp(normal.y,available->y,available->y+std::max(0.,available->h-normal.h)),normal.w,normal.h};
        t->space()->algorithm()->floatingAlgo()->setTargetGeom(native(restored),t);
        t->warpPositionSize();maximizeOrRestore(w);
    }else{
        t->space()->algorithm()->floatingAlgo()->setTargetGeom(native(*result),t);
        t->rememberFloatingSize({normal.w,normal.h});
        saved.insert_or_assign(w->metadata().stableID(),Saved{w,normal,*result});
    }
    Fusion057::dispatchPlugin("xetalwobbly:anchorplacement",std::to_string(w->metadata().stableID()));
    Desktop::windowState()->raise(w);g_pHyprRenderer->damageWindow(w,true);
}
class Pass:public IPassElement {
    PHLMONITORREF monitor;Gesture state;
public:
    Pass(PHLMONITOR m):monitor(m),state(gesture){}
    bool needsLiveBlur(Render::CRenderContext& ctx)override{return false;}
    bool needsPrecomputeBlur(Render::CRenderContext& ctx)override{return false;}
    bool disableSimplification(Render::CRenderContext& ctx)override{return true;}
    ePassElementType type()override{return EK_CUSTOM;}
    const char* passName()override{return "FusionKDESnap";}
    std::vector<UP<IPassElement>> draw(Render::CRenderContext& ctx)override{
        auto m=monitor.lock();if(!m||!usable(state.window.lock())||state.cancelled)return {};
        auto rect=[&](Box b,CHyprColor color,int rounding){
            if(!valid(b))return;
            CRectPassElement::SRectData data;data.box=native(b).translate(-m->m_position).scale(m->m_scale);
            data.color=color;data.round=std::round(rounding*m->m_scale);g_pHyprRenderer->draw(ctx,data,ctx.m_data.damage);
        };
        if(valid(state.preview)){
            const auto b=state.preview;rect(b,CHyprColor(accent[0],accent[1],accent[2],.18F),6);
            for(const auto line:std::array<Box,4>{{{b.x,b.y,b.w,2},{b.x,b.y+b.h-2,b.w,2},{b.x,b.y,2,b.h},{b.x+b.w-2,b.y,2,b.h}}})
                rect(line,CHyprColor(accent[0],accent[1],accent[2],.85F),0);
        }
        if(valid(state.panel)){
            auto bg=titlebarPalette.background;rect(state.panel,CHyprColor(bg[0],bg[1],bg[2],.97F),8);
            for(auto cell:cells(state.panel))rect(cell.box,CHyprColor(accent[0],accent[1],accent[2],cell.zone==state.zone?.85F:.32F),3);
        }
        return {};
    }
};
template<typename T>void hook(const char* name,const char* signature,const void* replacement,T& original){
    for(auto& match:HyprlandAPI::findFunctionsByName(handle,name))if(Fusion057::symbolName(match).find(signature)!=std::string::npos){
        auto h=HyprlandAPI::createFunctionHook(handle,match.address,replacement);
        if(!h||!h->hook())throw std::runtime_error("Cannot attach KDE snapping: "+std::string(name));
        original=reinterpret_cast<T>(h->m_original);hooks.push_back(h);return;
    }
    throw std::runtime_error("Unsupported KDE snapping API: "+std::string(name));
}
void cleanup(){clear();ready=false;saved.clear();for(auto it=hooks.rbegin();it!=hooks.rend();++it)(*it)->unhook();hooks.clear();g_pHyprRenderer->context().m_pass.removeAllOfType("FusionKDESnap");}
void init(){
    try{
        load();hook("beginDragTarget","CLayoutManager::beginDragTarget(",reinterpret_cast<void*>(begin),originalBegin);
        hook("updateDragWindow","CDragStateController::updateDragWindow(",reinterpret_cast<void*>(update),originalUpdate);ready=true;
    }catch(const std::exception& error){
        // An unavailable optional hook must not take away working controls or
        // title bars. Remove partial hooks and leave native dragging untouched.
        cleanup();
        HyprlandAPI::addNotification(handle,"KDE snap layouts unavailable: "+std::string(error.what()),CHyprColor(accent[0],accent[1],accent[2],1),6000);
    }
}
}
