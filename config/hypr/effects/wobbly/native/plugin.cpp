// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine. Compiz physics attribution: COPYING / NOTICE.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/state/MonitorState.hpp>
#include <hyprland/src/output/MonitorResources.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cerrno>
#include <hyprland/src/managers/KeybindManager.hpp>
#include <hyprland/src/devices/IKeyboard.hpp>
#include <hyprland/src/layout/LayoutManager.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/xwayland/XWayland.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <hyprland/src/config/ConfigValue.hpp>
#include "engine.hpp"
#include "settings.hpp"
#include "graphics.hpp"
#include "capture.hpp"
#include "../../../runtime/window_types_native.hpp"
// xcb-xkb's generated C header uses the C++ keyword as a field name.
#define explicit explicit_
#include <xcb/xkb.h>
#undef explicit

namespace {
using Clock=std::chrono::steady_clock;
using Geo=Desktop::View::IGeometric;
HANDLE handle;
Wobbly::Settings settings;
Wobbly::Graphics graphics;
SP<SHyprCtlCommand> statusCommand;
PHLMONITORREF renderingMonitor;
std::vector<CHyprSignalListener> listeners;
std::vector<CFunctionHook*> hooks;
bool stopping=false;
uint64_t started=0,finished=0,draws=0,steps=0,grabs=0,shivers=0,meshBuilds=0;
std::map<int64_t,uint64_t> outputSteps;
double damagePixels=0,monitorPixels=0;
std::string lastError;
xcb_connection_t* bellConnection=nullptr;
wl_event_source* bellSource=nullptr;
int bellEventBase=0;
int ipcFD=-1;
wl_event_source* ipcSource=nullptr;
std::string ipcBuffer;

std::filesystem::path configPath(){
    if(auto path=std::getenv("XETAL_WOBBLY_CONFIG"))return path;
    auto home=std::getenv("HOME");if(!home)throw std::runtime_error("Missing home for Wobbly settings");
    return std::filesystem::path(home)/".config/hypr/effects/wobbly/settings.json";
}
bool usable(PHLWINDOW w){
    static auto animations=CConfigValue<Config::INTEGER>("animations:enabled");
    return settings.enabled && *animations && w && w->m_isMapped && !w->isHidden() && w->m_monitor &&
        w->m_workspace && w->m_workspace->isVisible() && w->wlSurface() && w->wlSurface()->resource() &&
        !g_pSessionLockManager->isSessionLocked() && g_pCompositor->m_sessionActive &&
        Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_FULLSCREEN &&
        w->size(Geo::GEOMETRIC_CURRENT).x>1 && w->size(Geo::GEOMETRIC_CURRENT).y>1;
}
Wobbly::WindowInfo info(PHLWINDOW w){
    Wobbly::WindowInfo v;v.app=w->m_class;v.title=w->m_title;v.floating=w->m_isFloating;v.xwayland=w->m_isX11;
    auto mode=Fullscreen::controller()->getFullscreenModes(w).internal;
    v.state=mode==Fullscreen::FSMODE_MAXIMIZED?"maximized":mode==Fullscreen::FSMODE_FULLSCREEN?"fullscreen":"normal";
    if(auto s=w->m_xwaylandSurface){
        v.role=s->m_role;v.xid=s->m_xID;v.overrideRedirect=s->m_overrideRedirect;
        const std::vector<std::pair<std::string,std::string>> names={{"NORMAL","Normal"},{"DIALOG","Dialog"},{"UTILITY","Utility"},{"TOOLBAR","Toolbar"},
            {"MENU","Menu"},{"SPLASH","Splash"},{"DROPDOWN_MENU","DropdownMenu"},{"POPUP_MENU","PopupMenu"},{"TOOLTIP","Tooltip"},
            {"NOTIFICATION","Notification"},{"COMBO","Combo"},{"DND","Dnd"},{"DOCK","Dock"},{"DESKTOP","Desktop"}};
        if(s->m_overrideRedirect)v.type="Unknown";
        for(auto& [atom,type]:names)if(std::ranges::find(s->m_atoms,HYPRATOMS["_NET_WM_WINDOW_TYPE_"+atom])!=s->m_atoms.end()){v.type=type;break;}
    }else if(w->m_xdgSurface && w->m_xdgSurface->m_toplevel && w->m_xdgSurface->m_toplevel->m_parent)v.type="Dialog";
    v.rgba=w->effectiveAlpha()<1.f;
    return v;
}
Wobbly::Box box(PHLWINDOW w){auto b=w->geometricBox(Geo::GEOMETRIC_CURRENT);b.addExtents(w->getFullWindowExtents());return {b.x,b.y,b.w,b.h};}

struct Record {
    PHLWINDOWREF window;
    PHLMONITORREF monitor;
    PHLWORKSPACEREF workspace;
    Wobbly::Engine engine;
    Wobbly::Mesh mesh;
    uint64_t meshRevision=0;
    CBox meshViewport;
    CBox meshSource;
    std::map<int64_t,SP<Render::IFramebuffer>> sourceBuffers;
    std::map<int64_t,CBox> lastDamage;
    bool meshDirty=true;
    Clock::time_point last=Clock::now();
    bool resize=false,settlePosition=false,hotkey=false;
    Record(PHLWINDOW w):window(w),monitor(w->m_monitor),workspace(w->m_workspace),engine(box(w)){}
};
std::vector<std::shared_ptr<Record>> records;
auto record(PHLWINDOW w){auto it=std::find_if(records.begin(),records.end(),[&](auto& r){return r->window==w;});return it==records.end()?std::shared_ptr<Record>{}:*it;}
CBox bounds(const std::shared_ptr<Record>& r){
    auto b=r->engine.box;double left=b.x,top=b.y,right=b.x+b.w,bottom=b.y+b.h;
    for(auto p:r->engine.renderPoints()){left=std::min(left,double(p.x));top=std::min(top,double(p.y));right=std::max(right,double(p.x));bottom=std::max(bottom,double(p.y));}
    return CBox{std::floor(left)-3,std::floor(top)-3,std::ceil(right)-std::floor(left)+6,std::ceil(bottom)-std::floor(top)+6};
}
bool touches(const std::shared_ptr<Record>& r,PHLMONITOR m){
    if(!m)return false;
    CRegion region(bounds(r));
    if(auto w=r->window.lock())region.add(w->geometricBox(Geo::GEOMETRIC_CURRENT));
    if(auto it=r->lastDamage.find(m->m_id);it!=r->lastDamage.end())region.add(it->second);
    region.intersect(m->logicalBox());return !region.empty();
}
void damage(const std::shared_ptr<Record>& r,PHLMONITOR only=nullptr){
    const auto current=bounds(r);
    for(auto& m:State::monitorState()->monitors()){
        if(!m||!m->m_output||m->isMirror()||(only&&only!=m))continue;
        CRegion region(current);
        auto& previous=r->lastDamage[m->m_id];if(!previous.empty())region.add(previous);
        region.translate(-m->m_position).scale(m->m_scale);
        region.intersect(CBox{0,0,m->m_transformedSize.x,m->m_transformedSize.y});
        if(region.empty()){previous={};continue;}
        region.forEachRect([](const auto& b){damagePixels+=double(b.x2-b.x1)*(b.y2-b.y1);});
        monitorPixels+=m->m_transformedSize.x*m->m_transformedSize.y;
        m->addDamage(region);
        previous=current;
    }
}

class Transformer:public Render::IWindowTransformer {
  public:
    std::weak_ptr<Record> ref;
    explicit Transformer(std::shared_ptr<Record> r):ref(r){}
    void amendTransformedRenderData(const CBox&,SMotionBlurData* motion)override{
        // The lattice already follows the drag; do not smear a second affine
        // movement over it. Other windows keep their configured motion blur.
        if(!ref.expired() && !g_pHyprRenderer->m_bRenderingSnapshot)motion->enabled=false;
    }
    SP<Render::IFramebuffer> transform(SP<Render::IFramebuffer> in)override{
        auto r=ref.lock();auto renderer=g_pHyprRenderer.get();auto m=renderer->m_renderData.pMonitor.lock();
        if(stopping||!r||!m||!usable(r->window.lock())||renderer->m_bRenderingSnapshot)return in;
        auto out=m->resources()->getUnusedWorkBuffer();if(!out)return in;
        const auto viewport=m->logicalBox();
        if(r->meshDirty||r->meshViewport!=viewport||r->meshSource!=viewport){
            r->mesh.update(r->engine,settings.grid_resolution,settings.min_grid_size,{viewport.x,viewport.y,viewport.w,viewport.h});
            r->meshRevision=++meshBuilds;r->meshDirty=false;r->meshViewport=viewport;r->meshSource=viewport;
        }
        auto guard=renderer->bindTempFB(out);
        graphics.draw(m,in->getTexture(),r->mesh.vertices,r->meshRevision);++draws;
        return out;
    }
};

// Hyprland's normal transformer input is an output-sized image. Offscreen
// source pixels have already been lost there, even when the spring mesh bends
// them back onscreen. Capture the full window in its own coordinate system.
void drawElement(Render::IElementRenderer* elementRenderer,WP<IPassElement> element,const CRegion& damageRegion){
    if(Wobbly::captureContext){Wobbly::drawCaptured(elementRenderer,element,damageRegion);return;}
    auto renderer=g_pHyprRenderer.get();
    auto transformed=element?dynamic_cast<CTransformedWindowPassElement*>(element.get()):nullptr;
    auto r=transformed?record(transformed->m_data.window.lock()):nullptr;
    auto m=renderer->m_renderData.pMonitor.lock();
    if(stopping||!r||!m||!transformed->m_data.pass||renderer->m_bRenderingSnapshot||!usable(r->window.lock())){
        Wobbly::originalElementDraw(elementRenderer,element,damageRegion);return;
    }
    auto& input=transformed->m_data;
    const auto pixels=input.currentBox.copy().scale(m->m_scale);
    const CBox source{std::floor(pixels.x)-2,std::floor(pixels.y)-2,
        std::ceil(pixels.w)+5,std::ceil(pixels.h)+5};
    GLint limit=0;glGetIntegerv(GL_MAX_TEXTURE_SIZE,&limit);
    if(source.w<1||source.h<1||source.w>limit||source.h>limit){
        Wobbly::originalElementDraw(elementRenderer,element,damageRegion);return;
    }
    // Different output scales need distinct reusable allocations. Fractional
    // movement changes the origin, never the allocation's padded dimensions.
    auto& sourceFB=r->sourceBuffers[m->m_id];
    if(!sourceFB)sourceFB=renderer->createFB("Wobbly complete window");
    if(!sourceFB->alloc(source.w,source.h,renderer->m_renderData.currentFB->m_drmFormat)){
        Wobbly::originalElementDraw(elementRenderer,element,damageRegion);return;
    }
    sourceFB->setImageDescription(renderer->workBufferImageDescription());
    const CBox viewport=m->logicalBox();
    const CBox worldSource=source.copy().scale(1.0/m->m_scale).translate(m->m_position);
    if(r->meshDirty||r->meshViewport!=viewport||r->meshSource!=worldSource){
        r->mesh.update(r->engine,settings.grid_resolution,settings.min_grid_size,
            {viewport.x,viewport.y,viewport.w,viewport.h},{worldSource.x,worldSource.y,worldSource.w,worldSource.h});
        r->meshRevision=++meshBuilds;r->meshDirty=false;r->meshViewport=viewport;r->meshSource=worldSource;
    }
    const auto deform=[&]{
        auto out=m->resources()->getUnusedWorkBuffer();
        if(out){auto guard=renderer->bindTempFB(out);graphics.draw(m,sourceFB->getTexture(),r->mesh.vertices,r->meshRevision,true);++draws;}
        return out;
    };
    Wobbly::captureWindow(sourceFB,m,source,[&](auto& data){
        data.currentWindow=input.window;input.pass->render(CRegion{source});
    });
    auto color=deform();if(!color)return;
    SP<Render::IFramebuffer> matte;
    if(input.blur){
        Wobbly::captureWindow(sourceFB,m,source,[&](auto& data){
            // The same complete capture and mesh define the blur silhouette.
            renderer->draw(CRectPassElement::SRectData{.box=input.blurBox,.color=CHyprColor(1,1,1,1),
                .round=input.blurRound,.roundingPower=input.blurRoundingPower},CRegion{source});
        });
        matte=deform();
    }
    CTexPassElement::SRenderData output;
    output.tex=color->getTexture();output.box={0,0,m->m_transformedSize.x,m->m_transformedSize.y};output.a=1.F;
    if(input.blur&&matte){
        output.blur=true;output.forceBlurBlend=true;output.blockBlurOptimization=true;output.blurA=input.blurA;
        output.blurAlphaMatte=matte->getTexture();output.discardMode=0;
    }
    renderer->draw(output,damageRegion.copy().intersect(output.box));
}

void detach(const std::shared_ptr<Record>& r){
    if(auto w=r->window.lock())std::erase_if(w->m_transformers,[&](auto& t){auto p=dynamic_cast<Transformer*>(t.get());return p&&p->ref.lock()==r;});
    damage(r);
}
void clear(){for(auto& r:records)detach(r);records.clear();}
std::shared_ptr<Record> ensure(PHLWINDOW w){
    if(auto r=record(w))return r;
    if(!usable(w)||records.size()>=32)return {};
    auto r=std::make_shared<Record>(w);records.push_back(r);w->m_transformers.push_back(makeUnique<Transformer>(r));
    ++started;damage(r);return r;
}
void shiver(PHLWINDOW w){if(auto r=ensure(w)){r->engine.shiver();++shivers;damage(r);}}

void stopIPC(){
    if(ipcSource){wl_event_source_remove(ipcSource);ipcSource=nullptr;}
    if(ipcFD>=0){close(ipcFD);ipcFD=-1;}ipcBuffer.clear();
}
int ipcReady(int,uint32_t mask,void*){
    if(mask&(WL_EVENT_HANGUP|WL_EVENT_ERROR)){stopIPC();return 0;}
    char chunk[4096];ssize_t n;
    while((n=recv(ipcFD,chunk,sizeof(chunk),MSG_DONTWAIT))>0){
        ipcBuffer.append(chunk,n);
        size_t end;
        while((end=ipcBuffer.find('\n'))!=std::string::npos){
            auto line=ipcBuffer.substr(0,end);ipcBuffer.erase(0,end+1);
            if(!line.starts_with("bell>>")||!settings.shiver)continue;
            auto w=Desktop::focusState()->window();auto address=line.substr(6);
            if(!address.empty())for(auto& candidate:Desktop::windowState()->windows())
                if(std::format("{:x}",reinterpret_cast<uintptr_t>(candidate.get()))==address){w=candidate;break;}
            if(usable(w))shiver(w);
        }
        if(ipcBuffer.size()>65536){stopIPC();return 0;}
    }
    if(n==0||(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR))stopIPC();
    return 0;
}
void startIPC(){
    sockaddr_un address{};address.sun_family=AF_UNIX;
    auto path=g_pCompositor->m_instancePath+"/.socket2.sock";
    if(path.size()>=sizeof(address.sun_path))return;
    std::memcpy(address.sun_path,path.c_str(),path.size()+1);
    ipcFD=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(ipcFD<0)return;
    if(connect(ipcFD,reinterpret_cast<sockaddr*>(&address),sizeof(address))<0&&errno!=EINPROGRESS){stopIPC();return;}
    ipcSource=wl_event_loop_add_fd(g_pCompositor->m_wlEventLoop,ipcFD,WL_EVENT_READABLE,ipcReady,nullptr);
    if(!ipcSource)stopIPC();
}
void stopX11Bell(){
    if(bellSource){wl_event_source_remove(bellSource);bellSource=nullptr;}
    if(bellConnection){xcb_disconnect(bellConnection);bellConnection=nullptr;}
}
void stopBell(){stopIPC();stopX11Bell();}
int bellReady(int,uint32_t mask,void*){
    if(mask&(WL_EVENT_HANGUP|WL_EVENT_ERROR)){stopX11Bell();return 0;}
    while(auto raw=xcb_poll_for_event(bellConnection)){
        if((raw->response_type&127)==bellEventBase){
            auto bell=reinterpret_cast<xcb_xkb_bell_notify_event_t*>(raw);
            if(bell->xkbType==XCB_XKB_BELL_NOTIFY&&settings.shiver){
                auto w=Desktop::focusState()->window();
                if(bell->window)for(auto& candidate:Desktop::windowState()->windows())
                    if(candidate->m_xwaylandSurface&&candidate->m_xwaylandSurface->m_xID==bell->window){w=candidate;break;}
                if(usable(w))shiver(w);
            }
        }
        std::free(raw);
    }
    if(xcb_connection_has_error(bellConnection))stopX11Bell();
    return 0;
}
void updateBell(){
    stopBell();if(!settings.enabled||!settings.shiver)return;
    startIPC();if(!std::getenv("DISPLAY"))return;
    bellConnection=xcb_connect(nullptr,nullptr);
    if(!bellConnection||xcb_connection_has_error(bellConnection)){stopX11Bell();return;}
    auto ext=xcb_get_extension_data(bellConnection,&xcb_xkb_id);
    if(!ext||!ext->present){stopX11Bell();return;}bellEventBase=ext->first_event;
    auto reply=xcb_xkb_use_extension_reply(bellConnection,xcb_xkb_use_extension(bellConnection,1,0),nullptr);
    bool supported=reply&&reply->supported;std::free(reply);if(!supported){stopX11Bell();return;}
    auto cookie=xcb_xkb_select_events_aux_checked(bellConnection,XCB_XKB_ID_USE_CORE_KBD,
        XCB_XKB_EVENT_TYPE_BELL_NOTIFY,0,XCB_XKB_EVENT_TYPE_BELL_NOTIFY,0,0,nullptr);
    auto error=xcb_request_check(bellConnection,cookie);if(error){std::free(error);stopX11Bell();return;}
    bellSource=wl_event_loop_add_fd(g_pCompositor->m_wlEventLoop,xcb_get_file_descriptor(bellConnection),WL_EVENT_READABLE,bellReady,nullptr);
    if(!bellSource)stopX11Bell();
}

// Original edge queries consume a snapshot of visible windows and monitor work
// areas (exclusive zones already account for panels). There are no X11 requests
// or filesystem reads in the physics/rendering path.
struct World {
    Wobbly::Compiz::CompScreen screen;
    std::vector<Wobbly::Compiz::CompWindow> windows;
    explicit World(PHLWINDOW current,Wobbly::Engine& engine){
        for(auto& m:State::monitorState()->monitors())if(m && !m->isMirror()){
            auto area=m->logicalBoxMinusReserved();
            auto pos=area.pos();
            auto size=area.size();
            screen.outputDev.push_back({{int(pos.x),int(pos.y),int(size.x),int(size.y)}});
        }
        if(screen.outputDev.empty())screen.outputDev.push_back({{0,0,32767,32767}});
        auto populate=[](auto& dst,PHLWINDOW w){
            auto b=w->geometricBox(Geo::GEOMETRIC_CURRENT);auto ext=w->getFullWindowExtents();int border=w->getRealBorderSize();
            dst.attrib={int(b.x),int(b.y),int(b.w),int(b.h)};dst.width=b.w;dst.height=b.h;
            dst.output={int(ext.topLeft.x),int(ext.bottomRight.x),int(ext.topLeft.y),int(ext.bottomRight.y)};
            dst.input={border,border,border,border};
        };
        populate(engine.window,current);
        for(auto& w:Desktop::windowState()->windows())if(w!=current&&w->m_isMapped&&!w->isHidden()&&w->m_workspace&&w->m_workspace->isVisible()){
            if(w->m_workspace!=current->m_workspace&&!w->m_pinned&&w->m_monitor==current->m_monitor)continue;
            windows.emplace_back();populate(windows.back(),w);
        }
        for(size_t i=0;i<windows.size();++i)windows[i].next=i+1<windows.size()?&windows[i+1]:nullptr;
        screen.windows=windows.empty()?nullptr:&windows[0];engine.window.screen=&screen;
    }
};

void frame(PHLMONITOR monitor){
    if(stopping)return;
    auto now=Clock::now();const auto pointer=Pointer::mgr()->position();
    std::erase_if(records,[&](auto& r){
        auto w=r->window.lock();
        if(!usable(w)){detach(r);return true;}
        // Keep the lattice/clock across monitor and workspace transfers. Each
        // visible output samples it on its own presentation, even when a window
        // spans 60/144 Hz displays. One shared elapsed-time clock prevents the
        // second output from advancing the physics twice as fast.
        r->monitor=w->m_monitor;r->workspace=w->m_workspace;
        if(!touches(r,monitor))return false;
        try{
            // Edge queries are only needed while magnetic snapping is active.
            std::unique_ptr<World> world;
            bool max=Fullscreen::controller()->getFullscreenModes(w).internal==Fullscreen::FSMODE_MAXIMIZED;
            r->engine.geometry(box(w),settings.maximize_effect&&max,pointer.x,pointer.y);
            if(r->engine.grabbed&&!r->resize){
                auto mods=g_pInputManager->getModsFromAllKBs();
                bool held=settings.snapModifiers && (mods&settings.snapModifiers)==settings.snapModifiers;
                if(held!=settings.snap_inverted || r->engine.snapping)world=std::make_unique<World>(w,r->engine);
                r->engine.snap(held!=settings.snap_inverted);
            }
            if(r->engine.snapping&&!world)world=std::make_unique<World>(w,r->engine);
            const float ms=std::chrono::duration<float,std::milli>(now-r->last).count();r->last=now;
            bool moving=r->engine.step(ms,settings.friction,settings.spring_k);++steps;++outputSteps[monitor->m_id];r->meshDirty=true;damage(r,monitor);
            if(!moving&&!r->engine.grabbed&&!w->positionAnimation()->isBeingAnimated()&&!w->sizeAnimation()->isBeingAnimated()){
                // Compiz lets the released lattice come to rest, then moves the
                // real input rectangle to that resting point. Only floats move.
                if(r->settlePosition && WindowTypes::geometryManaged(w) && w->m_isFloating && !max && w->m_target){
                    auto b=w->geometricBox(Geo::GEOMETRIC_CURRENT);auto ext=w->getFullWindowExtents();
                    b.x=std::round(r->engine.model->topLeft.x+ext.topLeft.x);b.y=std::round(r->engine.model->topLeft.y+ext.topLeft.y);
                    g_layoutManager->setTargetGeom(b,w->m_target);w->positionAnimation()->warp();
                }
                detach(r);++finished;return true;
            }
        }catch(const std::exception& e){lastError=e.what();detach(r);return true;}
        return false;
    });
}

using Drag=Layout::Supplementary::CDragStateController;
using BeginFn=void(*)(Drag*,SP<Layout::ITarget>,eMouseBindMode,std::optional<Layout::eRectCorner>,bool);
using EndFn=void(*)(Drag*);
using FullscreenFn=void(*)(Fullscreen::CFullscreenController*,PHLWINDOW,std::optional<Fullscreen::eFullscreenMode>,std::optional<Fullscreen::eFullscreenMode>,std::optional<bool>);
using KeyFn=bool(*)(CKeybindManager*,std::any,SP<IKeyboard>);
using MouseStateFn=bool(*)(CKeybindManager*);
BeginFn originalBegin;EndFn originalEnd;FullscreenFn originalFullscreen;
KeyFn originalKey;MouseStateFn originalMouseState;
bool snapKeyEvent=false;
bool keyEvent(CKeybindManager* manager,std::any event,SP<IKeyboard> keyboard){
    auto target=g_layoutManager->dragController()->target();
    auto r=target?record(target->window()):nullptr;
    const auto key=std::any_cast<IKeyboard::SKeyEvent>(&event);
    // Hyprland normally ends a mouse drag on any key event. Compiz needs its
    // snapping modifier to be pressable/releasable during that same drag.
    snapKeyEvent=!stopping&&key&&r&&r->engine.grabbed&&!r->resize&&usable(r->window.lock())&&
        (manager->keycodeToModifier(key->keycode+8)&settings.snapModifiers);
    Hyprutils::Utils::CScopeGuard reset([]{snapKeyEvent=false;});
    return originalKey(manager,std::move(event),keyboard);
}
bool mouseState(CKeybindManager* manager){return snapKeyEvent?false:originalMouseState(manager);}
void begin(Drag* drag,SP<Layout::ITarget> target,eMouseBindMode mode,std::optional<Layout::eRectCorner> edge,bool exclusive){
    originalBegin(drag,target,mode,edge,exclusive);
    if(stopping||!target||drag->target()!=target)return;
    const bool hotkey=bool(g_pKeybindManager->m_currentKeybind);
    if(hotkey?!settings.hotkey_drag:!settings.normal_drag)return;
    auto w=target->window();if(!usable(w)||!settings.move_window_match.matches(info(w)))return;
    if(auto r=ensure(w)){
        auto p=Pointer::mgr()->position();r->resize=mode!=MBIND_MOVE;r->hotkey=hotkey;
        r->settlePosition=!r->resize;r->engine.grab(p.x,p.y,settings.grab_window_match.matches(info(w)));++grabs;
    }
}
void end(Drag* drag){
    auto target=drag->target();auto r=target?record(target->window()):nullptr;
    originalEnd(drag);if(r){r->engine.release();damage(r);}
}
void fullscreen(Fullscreen::CFullscreenController* c,PHLWINDOW w,std::optional<Fullscreen::eFullscreenMode> internal,
                std::optional<Fullscreen::eFullscreenMode> client,std::optional<bool> aware){
    auto old=c->getFullscreenModes(w).internal;
    if(!stopping&&settings.maximize_effect&&usable(w)&&
       (old==Fullscreen::FSMODE_MAXIMIZED || internal==Fullscreen::FSMODE_MAXIMIZED || client==Fullscreen::FSMODE_MAXIMIZED)){
        if(auto r=ensure(w))r->engine.maximized=old==Fullscreen::FSMODE_MAXIMIZED;
    }
    originalFullscreen(c,w,internal,client,aware);
}
template<typename T>void hook(const std::string& name,const std::string& signature,const void* fn,T& original){
    for(auto& match:HyprlandAPI::findFunctionsByName(handle,name))if(match.demangled.find(signature)!=std::string::npos){
        auto h=HyprlandAPI::createFunctionHook(handle,match.address,fn);if(!h||!h->hook())throw std::runtime_error("Cannot hook Wobbly: "+name);
        original=reinterpret_cast<T>(h->m_original);hooks.push_back(h);return;
    }throw std::runtime_error("Unsupported Wobbly API: "+name);
}
void cleanup(){
    stopping=true;listeners.clear();renderingMonitor.reset();clear();stopBell();
    for(auto h:std::views::reverse(hooks))h->unhook();
    hooks.clear();
    g_pHyprRenderer->glBackend()->makeEGLCurrent();graphics.release();
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h){
    handle=h;stopping=false;
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())throw std::runtime_error("Rebuild Wobbly for this Hyprland ABI");
    if(g_pHyprRenderer->type()!=Render::IHyprRenderer::RT_GL)throw std::runtime_error("Wobbly needs the OpenGL renderer");
    settings=Wobbly::readSettings(configPath());
    try{
        g_pHyprRenderer->glBackend()->makeEGLCurrent();graphics.init();
        updateBell();
        hook("dragBegin","CDragStateController::dragBegin(",(void*)begin,originalBegin);
        hook("dragEnd","CDragStateController::dragEnd(",(void*)end,originalEnd);
        hook("setFullscreenMode","CFullscreenController::setFullscreenMode(",(void*)fullscreen,originalFullscreen);
        hook("onKeyEvent","CKeybindManager::onKeyEvent(",(void*)keyEvent,originalKey);
        hook("ensureMouseBindState","CKeybindManager::ensureMouseBindState(",(void*)mouseState,originalMouseState);
        hook("drawElement","IElementRenderer::drawElement(",(void*)drawElement,Wobbly::originalElementDraw);
        auto& events=Event::bus()->m_events;
        listeners.push_back(events.render.pre.listen([](PHLMONITOR m){renderingMonitor=m;frame(m);}));
        listeners.push_back(events.render.stage.listen([](eRenderStage stage){
            if(stage!=RENDER_POST||g_pHyprRenderer->m_bRenderingSnapshot)return;
            // endRender clears the renderer's pMonitor before RENDER_POST.
            auto m=renderingMonitor.lock();renderingMonitor.reset();
            // Rearm this output only. A faster neighboring output has its own
            // presentation callback; neither forces the other's cadence.
            for(auto& r:records)if(touches(r,m))damage(r,m);
        }));
        listeners.push_back(events.monitor.preRemoved.listen([](PHLMONITOR m){
            std::erase_if(records,[&](auto& r){if(r->monitor!=m)return false;detach(r);return true;});
        }));
        listeners.push_back(events.window.openLate.listen([](PHLWINDOW w){if(settings.map_effect&&usable(w)&&settings.map_window_match.matches(info(w)))shiver(w);}));
        listeners.push_back(events.window.active.listen([](PHLWINDOW w,Desktop::eFocusReason){if(settings.focus_effect&&usable(w)&&settings.focus_window_match.matches(info(w)))shiver(w);}));
        listeners.push_back(events.window.close.listen([](PHLWINDOW w){if(auto r=record(w)){detach(r);std::erase(records,r);}}));
        listeners.push_back(events.config.reloaded.listen([]{clear();}));
        HyprlandAPI::addDispatcherV2(handle,"xetalwobbly:reload",[](std::string){
            try{auto next=Wobbly::readSettings(configPath());clear();settings=std::move(next);updateBell();lastError.clear();return SDispatchResult{};}
            catch(const std::exception& e){return SDispatchResult{.success=false,.error=e.what()};}
        });
        HyprlandAPI::addDispatcherV2(handle,"xetalwobbly:shiver",[](std::string){
            auto w=Desktop::focusState()->window();if(!usable(w))return SDispatchResult{.success=false,.error="Enable Wobbly and focus a visible window"};
            shiver(w);return SDispatchResult{};
        });
        statusCommand=HyprlandAPI::registerHyprCtlCommand(handle,{"xetal-wobbly",true,[](eHyprCtlOutputFormat,std::string){
            std::string detail="[";
            for(auto& r:records){
                if(detail.size()>1)detail+=",";
                auto w=r->window.lock();auto& e=r->engine;double deviation=0;
                for(int i=0;i<16;++i)deviation=std::max(deviation,std::hypot(e.model->objects[i].position.x-e.box.x-(i%4)*e.box.w/3,e.model->objects[i].position.y-e.box.y-(i/4)*e.box.h/3));
                auto m=r->monitor.lock();
                detail+=std::format("{{\"grabbed\":{},\"hotkey\":{},\"monitor\":{},\"refresh_hz\":{},\"flags\":{},\"deviation\":{},\"snapping\":{},\"position_animating\":{},\"size_animating\":{},\"box\":[{},{},{},{}]}}",
                    e.grabbed,r->hotkey,m?m->m_id:-1,m?m->m_refreshRate:0,e.active,deviation,e.snapping,w&&w->positionAnimation()->isBeingAnimated(),w&&w->sizeAnimation()->isBeingAnimated(),e.box.x,e.box.y,e.box.w,e.box.h);
            }
            detail+="]";
            std::string outputs="[";
            for(auto& m:State::monitorState()->monitors()){
                if(outputs.size()>1)outputs+=",";
                outputs+=std::format("{{\"id\":{},\"refresh_hz\":{},\"steps\":{}}}",m->m_id,m->m_refreshRate,outputSteps[m->m_id]);
            }
            outputs+="]";
            auto error=json_object_new_string(lastError.c_str());std::string errorText=json_object_to_json_string_ext(error,JSON_C_TO_STRING_PLAIN);json_object_put(error);
            return std::format("{{\"enabled\":{},\"active\":{},\"started\":{},\"finished\":{},\"draws\":{},\"steps\":{},\"mesh_builds\":{},\"damage_ratio\":{},\"grabs\":{},\"shivers\":{},\"x11_bell\":{},\"wayland_bell\":{},\"error\":{},\"windows\":{},\"outputs\":{}}}",
                settings.enabled,records.size(),started,finished,draws,steps,meshBuilds,monitorPixels?damagePixels/monitorPixels:0,grabs,shivers,bellSource!=nullptr,ipcSource!=nullptr,errorText,detail,outputs);
        }});
    }catch(...){cleanup();throw;}
    return {"Xetal Wobbly Windows","Original Compiz spring lattice, Bézier mesh and edge resistance","XetalEngine / David Reveman / Kristian Høgsberg","1.0"};
}
APICALL EXPORT void PLUGIN_EXIT(){cleanup();}
