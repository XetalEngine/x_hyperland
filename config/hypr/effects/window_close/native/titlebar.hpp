// SPDX-License-Identifier: GPL-2.0-or-later
// Included inside the window-controls adapter's private namespace. Hyprland
// owns each decoration; this index contains no owning window references.
class Titlebar;
std::map<uint64_t,Titlebar*> titlebars;
PHLWINDOWREF titlebarPressed;
Action titlebarPressedAction=None;
bool titlebarDragging=false;
bool titlebarCaptured=false;
bool titlebarDragPending=false;
PHLWINDOWREF titlebarLastClick;
Vector2D titlebarPressPoint,titlebarClickPoint;
Clock::time_point titlebarClickTime{};

bool titlebarUncovered(PHLWINDOW w,Vector2D point){
    if(!w||w->hasPopupAt(point)||Desktop::viewState()->hitTest().windowAt(point,
        Desktop::View::ALLOW_FLOATING|Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS)!=w)return false;
    // Check the output under the pointer, which can differ from the window's
    // assigned output during a crossing. Panels/menus always keep their input.
    for(const auto& m:State::monitorState()->monitors())if(m->logicalBox().containsPoint(point)){
        Vector2D local;PHLLS layer;
        for(int i:{3,2})if(Desktop::viewState()->hitTest().layerSurfaceAt(point,&m->m_layerSurfaceLayers[i],&local,&layer))return false;
        if(Desktop::viewState()->hitTest().layerPopupSurfaceAt(point,m,&local,&layer))return false;
        return true;
    }
    return false;
}

class Titlebar final:public IHyprWindowDecoration {
    PHLWINDOWREF window;
    uint64_t id;
    int barHeight=0,hover=-1;
    WindowButtons::Rule rule;
    CBox assigned;
    SP<Render::ITexture> texture;
    std::string cacheKey;
    std::string lastTitle;
    bool lastActive=false;
    uint64_t lastPalette=0;
public:
    Titlebar(PHLWINDOW w,const WindowButtons::Rule& r):IHyprWindowDecoration(w),window(w),id(w->m_stableID),rule(r){}
    ~Titlebar()override {titlebars.erase(id);}
    PHLWINDOW owner()const{return window.lock();}
    bool active()const{return barHeight>0;}
    CBox box()const{
        auto w=owner();if(!w||!active())return {};
        auto result=assigned.copy().translate(g_pDecorationPositioner->getEdgeDefinedPoint(DECORATION_EDGE_TOP,window));
        if(w->m_workspace&&!w->m_pinned)result.translate(w->m_workspace->m_renderOffset->value());
        return result.translate(w->m_floatingOffset);
    }
    SDecorationPositioningInfo getPositioningInfo()override{
        SDecorationPositioningInfo info;
        info.policy=DECORATION_POSITION_STICKY;info.edges=DECORATION_EDGE_TOP;
        // Place the bar inside the normal border so that the border surrounds
        // both the app and bar. Shadows use PART_OF_MAIN_WINDOW below.
        info.priority=11000;info.reserved=true;info.desiredExtents={{0,barHeight},{0,0}};
        return info;
    }
    void onPositioningReply(const SDecorationPositioningReply& reply)override{assigned=reply.assignedGeometry;}
    eDecorationType getDecorationType()override{return DECORATION_CUSTOM;}
    eDecorationLayer getDecorationLayer()override{return DECORATION_LAYER_OVER;}
    uint64_t getDecorationFlags()override{return active()?DECORATION_ALLOWS_MOUSE_INPUT|DECORATION_PART_OF_MAIN_WINDOW:0;}
    std::string getDisplayName()override{return "Fusion KDE title bar";}
    void damageEntire()override{const auto b=box();if(!b.empty())g_pHyprRenderer->damageBox(b.copy().expand(2));}
    void updateWindow(PHLWINDOW)override{damageEntire();}
    Action actionAt(Vector2D point)const{
        const auto b=box();if(!b.containsPoint(point))return None;
        const int i=WindowButtons::Titlebar::hit(WindowButtons::Titlebar::layout(b.w,b.h,rule.size),point.x-b.x,point.y-b.y);
        constexpr std::array actions{Gear,Minimize,Maximize,Close};return i<0?None:actions[i];
    }
    std::string status()const{
        const auto b=box();std::string buttons="[";
        const auto layout=WindowButtons::Titlebar::layout(b.w,b.h,rule.size);
        for(const auto& r:layout.buttons){if(buttons.size()>1)buttons+=",";
            buttons+=std::format("[{},{},{},{}]",b.x+r.x,b.y+r.y,r.w,r.h);}
        return std::format("{{\"enabled\":{},\"box\":[{},{},{},{}],\"buttons\":{}]}}",active(),b.x,b.y,b.w,b.h,buttons);
    }
    void configure(const WindowButtons::Rule& next,bool enabled){
        auto w=owner();if(!w)return;
        const auto nextHeight=enabled?WindowButtons::Titlebar::height(next.size):0;
        const bool geometry=nextHeight!=barHeight;
        // Keep the entire mesh stable while the user is dragging or Wobbly is
        // settling; workspace crossings must not resize its source rectangle.
        if(geometry&&!settled(w)){waiting=true;return;}
        const bool style=next.size!=rule.size||next.background!=rule.background||next.backgroundColor!=rule.backgroundColor;
        const bool focused=Desktop::focusState()->isWindowActive(w);
        int nextHover=-1;
        if(enabled&&available()&&settled(w)){
            const auto point=Pointer::mgr()->position();
            if(box().containsPoint(point)&&titlebarUncovered(w,point)){
                const auto b=box();nextHover=WindowButtons::Titlebar::hit(WindowButtons::Titlebar::layout(b.w,b.h,next.size),point.x-b.x,point.y-b.y);
            }
        }
        const bool changed=geometry||style||nextHover!=hover||lastTitle!=w->m_title||lastActive!=focused||lastPalette!=paletteRevision;
        if(!changed)return;
        const bool grows=nextHeight>barHeight;
        damageEntire();barHeight=nextHeight;rule=next;hover=nextHover;
        lastTitle=w->m_title;lastActive=focused;lastPalette=paletteRevision;cacheKey.clear();
        if(geometry){
            g_pDecorationPositioner->repositionDeco(this);
            if(auto t=w->layoutTarget();t&&t->space()){
                if(Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_NONE)
                    t->space()->recalculate(Layout::RECALCULATE_REASON_TOGGLE_DEFAULT_HANDLED_FULLSCREEN);
                else if(grows&&t->floating()){
                    // Floating client content keeps its size. If a new/taller
                    // bar would be behind the panel, move just far enough down
                    // to expose it, without replaying any pointer movement.
                    auto geometry=t->position();const auto work=t->space()->workArea(true);
                    geometry.y=std::max(geometry.y,work.y+w->getFullWindowReservedArea().topLeft.y);
                    t->space()->algorithm()->floatingAlgo()->setTargetGeom(geometry,t);
                }else t->recalc();
            }
        }
        damageEntire();
    }
    void draw(PHLMONITOR monitor,float const& alpha)override{
        auto w=owner();if(!w||!active()||!monitor)return;
        auto b=box();if(b.w<1||b.h<1)return;
        const int width=std::clamp(int(std::ceil(b.w*monitor->m_scale)),1,16384);
        const int height=std::clamp(int(std::ceil(b.h*monitor->m_scale)),1,1024);
        const bool focused=Desktop::focusState()->isWindowActive(w),restore=restoring(w);
        const auto key=std::format("{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}",width,height,focused,restore,hover,
            w->rounding(),paletteRevision,rule.size,rule.background,rule.backgroundColor,w->m_title);
        if(!texture||key!=cacheKey){
            auto surface=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,width,height);
            auto cr=cairo_create(surface);cairo_scale(cr,width/b.w,height/b.h);
            auto palette=titlebarPalette;
            if(rule.background=="manual"){
                const auto rgb=std::stoul(rule.backgroundColor.substr(1),nullptr,16);
                palette.background={double((rgb>>16)&255)/255,double((rgb>>8)&255)/255,double(rgb&255)/255};
                const double brightness=palette.background[0]*.2126+palette.background[1]*.7152+palette.background[2]*.0722;
                palette.foreground=brightness>.55?WindowButtons::Titlebar::RGB{.06,.06,.06}:WindowButtons::Titlebar::RGB{.98,.98,.98};
            }
            WindowButtons::Titlebar::paint(cr,b.w,b.h,rule.size,w->m_title,palette,focused,restore,hover,w->rounding());
            cairo_destroy(cr);cairo_surface_flush(surface);
            g_pHyprRenderer->glBackend()->makeEGLCurrent();
            texture=g_pHyprRenderer->createTexture(DRM_FORMAT_ARGB8888,cairo_image_surface_get_data(surface),
                cairo_image_surface_get_stride(surface),Vector2D(width,height));
            cairo_surface_destroy(surface);cacheKey=key;
        }
        CTexPassElement::SRenderData data;data.tex=texture;data.a=alpha;
        data.box=b.translate(-monitor->m_position).scale(monitor->m_scale).round();
        // A normal decoration pass is captured by Wobbly, minimize snapshots,
        // workspace animation and every intersecting output, including while
        // the window is moving. Never gate rendering on available()/settled().
        g_pHyprRenderer->addPassElement(makeUnique<CTexPassElement>(data));
    }
    bool press(const Vector2D& point){
        auto w=owner();if(!w||!active()||!available()||!settled(w))return false;
        const auto mods=g_pInputManager->getModsFromAllKBs();
        if(mods)return false; // Let normal Super/Alt bindings keep ownership.
        titlebarPressed=w;titlebarPressedAction=actionAt(point);titlebarDragging=false;titlebarCaptured=true;titlebarDragPending=false;
        titlebarPressPoint=point;
        Desktop::focusState()->fullWindowFocus(w,Desktop::FOCUS_REASON_CLICK);Desktop::windowState()->raise(w);
        if(titlebarPressedAction==None){
            if(titlebarLastClick.lock()==w&&Clock::now()-titlebarClickTime<std::chrono::milliseconds(400)&&
               std::hypot(point.x-titlebarClickPoint.x,point.y-titlebarClickPoint.y)<5){
                pending=w;pendingAction=Maximize;titlebarLastClick.reset();arm();return true;
            }
            // A click only focuses. In particular, don't unmaximize a window
            // until movement proves it is a drag (or a second click toggles it).
            titlebarDragPending=true;
        }
        arm();return true;
    }
};

bool titlebarActive(PHLWINDOW w){
    if(!w)return false;
    auto it=titlebars.find(w->m_stableID);return it!=titlebars.end()&&it->second->active();
}
std::string titlebarStatus(PHLWINDOW w){
    const auto it=titlebars.find(w->m_stableID);
    return it==titlebars.end()?"{\"enabled\":false,\"box\":[0,0,0,0],\"buttons\":[]}":it->second->status();
}
void syncTitlebars(){
    for(const auto& w:Desktop::windowState()->windows()){
        if(!w->m_isMapped||w->isHidden()||!WindowTypes::geometryManaged(w)||w->m_class=="fusion-window-buttons"||!w->layoutTarget())continue;
        const auto preview=previewFor(w);
        const auto rule=preview?preview->rule:ruleFor(w);
        const bool enabled=kdeMode(w)&&rule.titlebar.value_or(true)&&!w->m_X11DoesntWantBorders&&
            w->m_ruleApplicator->decorate().valueOrDefault()&&
            Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_FULLSCREEN;
        auto it=titlebars.find(w->m_stableID);
        if(it==titlebars.end()){
            if(!enabled)continue;
            auto bar=makeUnique<Titlebar>(w,rule);auto* ptr=bar.get();
            if(HyprlandAPI::addWindowDecoration(handle,w,std::move(bar)))titlebars.emplace(w->m_stableID,ptr);
            it=titlebars.find(w->m_stableID);
        }
        if(it!=titlebars.end())it->second->configure(rule,enabled);
    }
}
void titlebarMotion(){
    if(!titlebarCaptured||!titlebarDragPending)return;
    const auto point=Pointer::mgr()->position();
    if(std::hypot(point.x-titlebarPressPoint.x,point.y-titlebarPressPoint.y)<3)return;
    titlebarDragPending=false;titlebarLastClick.reset();
    auto w=titlebarPressed.lock();
    if(!w||!w->m_isMapped||w->isHidden()||!available()||!settled(w)||!titlebarActive(w))return;
    if(auto t=w->layoutTarget();t&&t->space()){
        // Native pointer-rate motion starts at the *current* position: no
        // replay of the press-to-threshold displacement, hence no initial jump.
        g_layoutManager->beginDragTarget(t,MBIND_MOVE,std::nullopt,true);
        titlebarDragging=g_layoutManager->dragController()->target()==t;
    }
}
bool titlebarPointer(IPointer::SButtonEvent event,Event::SCallbackInfo& info){
    // Capture both halves at the same stage as the existing overlay buttons.
    // Mixing onInputOnDeco presses with cancelled raw releases would leave
    // Hyprland's held-button bookkeeping stuck after a drag.
    if(event.state==WL_POINTER_BUTTON_STATE_PRESSED){
        if(info.cancelled||!available())return false;
        const auto point=Pointer::mgr()->position();
        const auto w=Desktop::viewState()->hitTest().windowAt(point,
            Desktop::View::ALLOW_FLOATING|Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
        if(!titlebarActive(w)||!titlebarUncovered(w,point))return false;
        auto bar=titlebars.at(w->m_stableID);
        if(!bar->box().containsPoint(point)||!bar->press(point))return false;
        info.cancelled=true;return true;
    }
    if(!titlebarCaptured)return false;
    auto w=titlebarPressed.lock();info.cancelled=true;
    if(titlebarDragPending&&w&&available()&&titlebarUncovered(w,Pointer::mgr()->position())){
        titlebarLastClick=w;titlebarClickPoint=Pointer::mgr()->position();titlebarClickTime=Clock::now();
    }
    if(titlebarDragging){
        titlebarLastClick.reset();
        auto t=g_layoutManager->dragController()->target();
        if(t&&t->window()==w)g_layoutManager->dragController()->dragEnd();
    }else if(w&&w->m_isMapped&&available()&&settled(w)&&titlebarActive(w)){
        const auto point=Pointer::mgr()->position();
        if(titlebarPressedAction!=None&&titlebars.at(w->m_stableID)->actionAt(point)==titlebarPressedAction&&
           titlebarUncovered(w,point)){
            pending=w;pendingAction=titlebarPressedAction;
        }
    }
    titlebarPressed.reset();titlebarPressedAction=None;titlebarDragging=false;titlebarCaptured=false;titlebarDragPending=false;arm();return true;
}
void cleanupTitlebars(){
    if(auto w=titlebarPressed.lock();w&&titlebarDragging){
        auto t=g_layoutManager->dragController()->target();if(t&&t->window()==w)g_layoutManager->dragController()->dragEnd();
    }
    titlebarPressed.reset();titlebarDragging=false;titlebarCaptured=false;titlebarDragPending=false;titlebarLastClick.reset();
    // Removal can destroy a decoration immediately (and erase its index).
    const auto copy=titlebars;
    for(const auto& [id,bar]:copy){
        auto w=bar->owner();
        HyprlandAPI::removeWindowDecoration(handle,bar);
        if(!w)continue;
        // In the pinned compositor removeWindowDeco defers hidden/unmapped
        // windows. Those objects must not retain this module's vtable after
        // dlclose, e.g. a minimized window restored after unloading a plugin.
        if(std::ranges::any_of(w->m_windowDecorations,[&](const auto& d){return d.get()==bar;})){
            g_pDecorationPositioner->uncacheDecoration(bar);
            std::erase(w->m_decosToRemove,bar);
            std::erase_if(w->m_windowDecorations,[&](const auto& d){return d.get()==bar;});
            g_pDecorationPositioner->forceRecalcFor(w);
        }
    }
    titlebars.clear();
}
