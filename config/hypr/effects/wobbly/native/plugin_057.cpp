#include "../../../runtime/native_057.hpp"
// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine. Compiz physics attribution: COPYING / NOTICE.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/desktop/view/window/Window.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/FadingOutState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/workspace/HLWorkspace.hpp>
#include <hyprland/src/state/MonitorState.hpp>
#include <hyprland/src/output/MonitorResources.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cerrno>
#include <hyprland/src/keybinds/Manager.hpp>
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
#include "mesh.hpp"
#include "import_hook_057.hpp"
#include <hyprland/src/render/transformer/TransformerList.hpp>
#include <hyprland/src/render/scene/SceneSelection.hpp>

#include "render_bounds.hpp"
#include "fullscreen_pass_057.hpp"
#include "../../../runtime/window_types_native_057.hpp"
// xcb-xkb's generated C header uses the C++ keyword as a field name.
#define explicit explicit_
#include <xcb/xkb.h>
#undef explicit
#include <xcb/xcbext.h>

namespace {
using Clock=std::chrono::steady_clock;
using Geo=Desktop::View::IGeometric;
HANDLE handle;
Wobbly::Settings settings;

SP<Fusion057::Command> statusCommand;
PHLMONITORREF renderingMonitor;
std::vector<CHyprSignalListener> listeners;
std::vector<CFunctionHook*> hooks;
bool stopping=false;
uint64_t started=0,finished=0,draws=0,steps=0,grabs=0,shivers=0,meshBuilds=0;
std::map<int64_t,uint64_t> outputSteps,outputCompositedFrames,outputCrossingFrames;
double damagePixels=0,monitorPixels=0;
std::string lastError;
xcb_connection_t* bellConnection=nullptr;
wl_event_source* bellSource=nullptr;
int bellEventBase=0;
enum class BellPhase { Waiting, Extension, Version, Selection, Ready, Failed };
BellPhase bellPhase=BellPhase::Waiting;
uint32_t bellReply=0,bellSelection=0;
using PollX11Event=xcb_generic_event_t*(*)(xcb_connection_t*);
PollX11Event originalPoll=nullptr;
Wobbly::ImportHook bellImport;
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
    return settings.enabled && *animations && w && w->mapped() && !w->isHidden() && w->m_monitor &&
        w->m_workspace && w->m_workspace->visible() && w->wlSurface() && w->wlSurface()->resource() &&
        !g_pSessionLockManager->isSessionLocked() && g_pCompositor->m_sessionActive &&
        Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_FULLSCREEN &&
        w->size(Geo::GEOMETRIC_CURRENT).x>1 && w->size(Geo::GEOMETRIC_CURRENT).y>1;
}
Wobbly::WindowInfo info(PHLWINDOW w){
    Wobbly::WindowInfo v;v.app=w->metadata().appID();v.title=w->metadata().title();v.floating=w->isFloating();v.xwayland=w->backend().isX11();
    auto mode=Fullscreen::controller()->getFullscreenModes(w).internal;
    v.state=mode==Fullscreen::FSMODE_MAXIMIZED?"maximized":mode==Fullscreen::FSMODE_FULLSCREEN?"fullscreen":"normal";
    if(auto s=Fusion057::x11(w)){
        v.role=s->m_role;v.xid=s->m_xID;v.overrideRedirect=s->m_overrideRedirect;
        const std::vector<std::pair<std::string,std::string>> names={{"NORMAL","Normal"},{"DIALOG","Dialog"},{"UTILITY","Utility"},{"TOOLBAR","Toolbar"},
            {"MENU","Menu"},{"SPLASH","Splash"},{"DROPDOWN_MENU","DropdownMenu"},{"POPUP_MENU","PopupMenu"},{"TOOLTIP","Tooltip"},
            {"NOTIFICATION","Notification"},{"COMBO","Combo"},{"DND","Dnd"},{"DOCK","Dock"},{"DESKTOP","Desktop"}};
        if(s->m_overrideRedirect)v.type="Unknown";
        for(auto& [atom,type]:names)if(std::ranges::find(s->m_atoms,HYPRATOMS["_NET_WM_WINDOW_TYPE_"+atom])!=s->m_atoms.end()){v.type=type;break;}
    }else if(Fusion057::xdg(w) && Fusion057::xdg(w)->m_toplevel && Fusion057::xdg(w)->m_toplevel->m_parent)v.type="Dialog";
    v.rgba=w->presentation().alphaTotal()<1.f;
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
    std::vector<SMeshRenderVertex> renderVertices;
    std::map<int64_t,CBox> lastDamage;
    bool meshDirty=true;
    Clock::time_point last=Clock::now();
    bool resize=false,settlePosition=false,hotkey=false,placementPending=false;
    Record(PHLWINDOW w):window(w),monitor(w->m_monitor),workspace(w->m_workspace),engine(box(w)){}
};
std::vector<std::shared_ptr<Record>> records;
auto record(PHLWINDOW w){auto it=std::find_if(records.begin(),records.end(),[&](auto& r){return r->window==w;});return it==records.end()?std::shared_ptr<Record>{}:*it;}
CBox bounds(const std::shared_ptr<Record>& r){
    const auto b=Wobbly::renderBounds(r->engine);return {b.x,b.y,b.w,b.h};
}

using Presentation=Desktop::View::CWindowPresentation;
using VisibleFn=bool(*)(Presentation*,PHLMONITOR);
VisibleFn originalVisible=nullptr;
bool visibleOnMonitor(Presentation* presentation,PHLMONITOR monitor){
    const bool original=originalVisible(presentation,monitor);
    if(original||stopping||!monitor||g_pHyprRenderer->context().m_renderingSnapshot)return original;
    for(const auto& r:records){
        auto w=r->window.lock();
        if(!w||&w->presentation()!=presentation||!usable(w))continue;
        const auto output=monitor->logicalBox();
        return Wobbly::overlaps(Wobbly::renderBounds(r->engine),{output.x,output.y,output.w,output.h});
    }
    return original;
}
using WorkspaceRenderFn=void(*)(Render::IHyprRenderer*,Render::CRenderContext&,PHLMONITOR,PHLWORKSPACE,const Time::steady_tp&,Render::eSceneMode);
WorkspaceRenderFn originalFullscreenWorkspace=nullptr;
bool crossingForeground(Render::IHyprRenderer* renderer,PHLWINDOW w,PHLMONITOR monitor,PHLWORKSPACE workspace){
    return workspace && !Fusion057::special(workspace) && usable(w) && w->isFloating() && !Fusion057::pinned(w) &&
        w->m_workspace!=workspace && !w->onSpecialWorkspace() && w->isAllowedOverFullscreen() &&
        !Fullscreen::controller()->isFullscreen(w) && renderer->shouldRenderWindow(w,monitor) &&
        w->presentation().alphaValue(Desktop::View::WINDOW_ALPHA_FADE)*w->presentation().alphaValue(Desktop::View::WINDOW_ALPHA_FULLSCREEN)>0.f;
}
void fullscreenWorkspace(Render::IHyprRenderer* renderer,Render::CRenderContext& ctx,PHLMONITOR monitor,PHLWORKSPACE workspace,const Time::steady_tp& time,Render::eSceneMode mode){
    if(mode!=Render::eSceneMode::MONITOR){originalFullscreenWorkspace(renderer,ctx,monitor,workspace,time,mode);return;}
    std::vector<PHLWINDOW> crossing;
    // Include settled floats as well: dropping the window across a seam must
    // not hide half of it when its last spring animation ends.
    if(!stopping && !renderer->context().m_renderingSnapshot)
        for(const auto& w:Desktop::windowState()->windows())
            if(crossingForeground(renderer,w,monitor,workspace))crossing.push_back(w);
    if(crossing.empty()){originalFullscreenWorkspace(renderer,ctx,monitor,workspace,time,mode);return;}
    ++outputCrossingFrames[monitor->m_id];
    Wobbly::renderFullscreenWorkspace(renderer,ctx,monitor,workspace,time,
        [&](PHLWINDOW w){return std::ranges::find(crossing,w)!=crossing.end();});
}
void preserveComposition(PHLMONITOR monitor){
    auto renderer=g_pHyprRenderer.get();
    if(stopping || !monitor || monitor->m_solitaryClient.expired() || renderer->context().m_renderingSnapshot)return;
    // The pinned compositor's solitary-fullscreen check only considers floats
    // on the fullscreen window's workspace. A dragged window changes workspace
    // at the monitor seam, while its lattice can still cover the old output.
    // That shortcut bypasses shouldRenderWindow AND every transformed pass.
    // preChecks runs after recheckSolitary, before tearing/direct scanout and
    // the single-window render path. Drop just this frame's shortcut when the
    // normal visibility policy (including Minimize's hook) admits our window.
    // No extra function hook: Cube already owns the solitary/scanout hooks.
    for(const auto& w:Desktop::windowState()->windows())if(
        (record(w) && usable(w) && renderer->shouldRenderWindow(w,monitor)) ||
        crossingForeground(renderer,w,monitor,monitor->m_activeWorkspace)){
        monitor->m_solitaryClient.reset();
        ++outputCompositedFrames[monitor->m_id];
        return;
    }
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

// The 0.57 renderer captures the complete source and deforms the blur matte
// through the same transformer. Supply Compiz's existing bicubic lattice;
// neither the native spring model nor its animation tick is used here.
class Transformer:public Render::IWindowTransformer {
  public:
    std::weak_ptr<Record> ref;
    explicit Transformer(std::shared_ptr<Record> r):ref(r){}
    bool active()const override{return !stopping&&!ref.expired();}
    bool blocksDirectScanout()const override{return active();}
    int priority()const override{return 10;}
    CBox transformedExtents(const CBox& current)const override{
        auto r=ref.lock();if(!r)return current;
        return bounds(r).translate(current.pos()-Vector2D{r->engine.box.x,r->engine.box.y});
    }
    CBox sourceBoxForOutput(const CBox&,const CBox& input)const override{return input;}
    void amendTransformedRenderData(Render::CRenderContext& ctx,const CBox&,SMotionBlurData* motion,
                                    const Render::SWindowRenderPresentation&)override{
        if(active()&&!ctx.m_renderingSnapshot)motion->enabled=false;
    }
    Render::SWindowTransformBuffer transform(Render::CRenderContext& ctx,const Render::SWindowTransformBuffer& in,
                                              const Render::SWindowTransformContext& context)override{
        auto r=ref.lock();auto monitor=context.monitor.lock();auto renderer=g_pHyprRenderer.get();
        if(stopping||!r||!monitor||!in.framebuffer||!usable(r->window.lock())||context.standalone||context.renderingSnapshot)return in;
        const double scale=monitor->m_scale;
        const auto canvas=Render::pixelBoxForLogical(context.outputBox.copy().expand(1.0/scale),scale);
        if(canvas.empty())return in;
        auto output=renderer->getWorkBuffer(ctx,canvas.size());
        if(!output)return {.framebuffer=in.framebuffer,.box=in.box,.success=false};
        const auto offset=context.currentBox.pos()-Vector2D{r->engine.box.x,r->engine.box.y};
        const auto viewport=canvas.copy().scale(1.0/scale).translate(-offset);
        const auto source=in.box.copy().scale(1.0/scale).translate(-offset);
        if(r->meshDirty||r->meshViewport!=viewport||r->meshSource!=source){
            r->mesh.update(r->engine,settings.grid_resolution,settings.min_grid_size,
                {viewport.x,viewport.y,viewport.w,viewport.h},{source.x,source.y,source.w,source.h});
            r->renderVertices.clear();r->renderVertices.reserve(r->mesh.vertices.size());
            for(const auto& v:r->mesh.vertices)r->renderVertices.push_back({v.x,v.y,v.u,v.v});
            r->meshRevision=++meshBuilds;r->meshDirty=false;r->meshViewport=viewport;r->meshSource=source;
        }
        auto state=ctx.saveDrawState();auto framebuffer=renderer->bindTempFB(ctx,output);
        ctx.m_data.damage=CRegion{0,0,int(canvas.w),int(canvas.h)};
        ctx.m_data.fbSize=canvas.size();ctx.m_data.renderModif={};ctx.m_data.transformDamage=false;
        renderer->setProjectionType(ctx,Render::RPT_EXPORT);
        renderer->draw(ctx,CClearPassElement::SClearData{CHyprColor(0,0,0,0)});
        renderer->glBackend()->renderTextureMesh(ctx,in.framebuffer->getTexture(),CBox{{},canvas.size()},r->renderVertices,
            {.damage=&ctx.m_data.damage,.a=1.F,.allowCustomUV=true});
        ++draws;
        return {.framebuffer=output,.box=canvas};
    }
};

void detach(const std::shared_ptr<Record>& r){
    if(auto w=r->window.lock()){
        auto& list=w->effects().transformers();
        if(auto effect=list->get<Transformer>();effect&&effect->ref.lock()==r)effect->ref.reset();
        list->removeInactive();
    }
    damage(r);
}
void clear(){for(auto& r:records)detach(r);records.clear();}
std::shared_ptr<Record> ensure(PHLWINDOW w){
    if(auto r=record(w))return r;
    if(!usable(w)||records.size()>=32)return {};
    auto r=std::make_shared<Record>(w);records.push_back(r);w->effects().transformers()->emplace<Transformer>(r);
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
// Use XWM's already established connection. A new synchronous X11 handshake
// can deadlock plugin loading while XWayland is waiting for the compositor.
// This member access is compiled only against the exact supported 0.57 ABI.
struct BellConnectionMember {
    using Type=UP<CXCBConnection> CXWM::*;
    friend Type connectionMember(BellConnectionMember);
};
template<typename Tag,typename Tag::Type Member> struct BellMemberAccess {
    friend typename Tag::Type connectionMember(Tag){return Member;}
};
template struct BellMemberAccess<BellConnectionMember,&CXWM::m_connection>;
xcb_connection_t* xwmBellConnection(){
    if(!g_pXWayland||!g_pXWayland->m_wm)return nullptr;
    const auto& owned=(*g_pXWayland->m_wm).*connectionMember(BellConnectionMember{});
    return owned?static_cast<xcb_connection_t*>(*owned):nullptr;
}
void resetX11Bell(){
    if(bellConnection&&bellConnection==xwmBellConnection()&&!xcb_connection_has_error(bellConnection)){
        if(bellReply)xcb_discard_reply(bellConnection,bellReply);
        if(bellSelection)xcb_discard_reply(bellConnection,bellSelection);
        if(bellPhase==BellPhase::Ready||bellPhase==BellPhase::Selection){
            xcb_xkb_select_events_aux(bellConnection,XCB_XKB_ID_USE_CORE_KBD,
                XCB_XKB_EVENT_TYPE_BELL_NOTIFY,XCB_XKB_EVENT_TYPE_BELL_NOTIFY,0,0,0,nullptr);
            xcb_flush(bellConnection);
        }
    }
    bellConnection=nullptr;bellReply=bellSelection=0;bellEventBase=0;bellPhase=BellPhase::Waiting;
}
void stopX11Bell(){
    if(bellSource){wl_event_source_remove(bellSource);bellSource=nullptr;}
    resetX11Bell();
}
void stopBell(){stopIPC();stopX11Bell();}
bool bellReplyReady(void*& value){
    xcb_generic_error_t* error=nullptr;
    if(!xcb_poll_for_reply(bellConnection,bellReply,&value,&error))return false;
    if(error||!value)bellPhase=BellPhase::Failed;
    std::free(error);bellReply=0;return true;
}
int prepareX11Bell(void*){
    auto connection=xwmBellConnection();
    if(connection!=bellConnection)resetX11Bell();
    if(connection&&!xcb_connection_has_error(connection)){
        bellConnection=connection;
        if(bellPhase==BellPhase::Waiting){
            xcb_prefetch_extension_data(connection,&xcb_xkb_id);
            // X11 processes requests in order. Polling this later reply proves
            // the prefetched extension response is already buffered by XCB.
            bellReply=xcb_get_input_focus(connection).sequence;
            bellPhase=BellPhase::Extension;xcb_flush(connection);
        }else if(bellReply){
            void* value=nullptr;
            if(bellReplyReady(value)){
                if(bellPhase==BellPhase::Extension){
                    auto ext=xcb_get_extension_data(connection,&xcb_xkb_id);
                    if(ext&&ext->present){
                        bellEventBase=ext->first_event;
                        bellReply=xcb_xkb_use_extension(connection,1,0).sequence;
                        bellPhase=BellPhase::Version;
                    }else bellPhase=BellPhase::Failed;
                }else if(bellPhase==BellPhase::Version){
                    auto reply=static_cast<xcb_xkb_use_extension_reply_t*>(value);
                    if(reply&&reply->supported){
                        bellSelection=xcb_xkb_select_events_aux_checked(connection,XCB_XKB_ID_USE_CORE_KBD,
                            XCB_XKB_EVENT_TYPE_BELL_NOTIFY,0,XCB_XKB_EVENT_TYPE_BELL_NOTIFY,0,0,nullptr).sequence;
                        bellReply=xcb_get_input_focus(connection).sequence;
                        bellPhase=BellPhase::Selection;
                    }else bellPhase=BellPhase::Failed;
                }else if(bellPhase==BellPhase::Selection){
                    // The later reply is present, so checking this earlier void
                    // request cannot introduce a synchronous server round trip.
                    auto error=xcb_request_check(connection,{bellSelection});
                    bellSelection=0;bellPhase=error?BellPhase::Failed:BellPhase::Ready;
                    std::free(error);
                }
                std::free(value);xcb_flush(connection);
            }
        }
    }else resetX11Bell();
    if(bellSource)wl_event_source_timer_update(bellSource,bellReply?20:500);
    return 0;
}
xcb_generic_event_t* pollX11Event(xcb_connection_t* connection){
    auto event=originalPoll(connection);
    if(event&&connection==bellConnection&&!stopping&&settings.enabled&&settings.shiver&&bellPhase==BellPhase::Ready&&
       (event->response_type&127)==bellEventBase){
        auto bell=reinterpret_cast<xcb_xkb_bell_notify_event_t*>(event);
        if(bell->xkbType==XCB_XKB_BELL_NOTIFY){
            auto w=Desktop::focusState()->window();
            if(bell->window)for(auto& candidate:Desktop::windowState()->windows())
                if(auto surface=Fusion057::x11(candidate);surface&&surface->m_xID==bell->window){w=candidate;break;}
            if(usable(w))shiver(w);
        }
    }
    // The caller still owns and processes every event. Never drain XWM's queue
    // from a second listener or discard clipboard/window-management events.
    return event;
}
void updateBell(){
    stopBell();if(!settings.enabled||!settings.shiver)return;
    startIPC();
    bellSource=wl_event_loop_add_timer(g_pCompositor->m_wlEventLoop,prepareX11Bell,nullptr);
    if(bellSource)wl_event_source_timer_update(bellSource,1);
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
            auto b=w->geometricBox(Geo::GEOMETRIC_CURRENT);auto ext=w->getFullWindowExtents();int border=w->presentation().borderSize();
            dst.attrib={int(b.x),int(b.y),int(b.w),int(b.h)};dst.width=b.w;dst.height=b.h;
            dst.output={int(ext.topLeft.x),int(ext.bottomRight.x),int(ext.topLeft.y),int(ext.bottomRight.y)};
            dst.input={border,border,border,border};
        };
        populate(engine.window,current);
        for(auto& w:Desktop::windowState()->windows())if(w!=current&&w->mapped()&&!w->isHidden()&&w->m_workspace&&w->m_workspace->visible()){
            if(w->m_workspace!=current->m_workspace&&!Fusion057::pinned(w)&&w->m_monitor==current->m_monitor)continue;
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
            if(r->placementPending&&!r->engine.grabbed){
                // Explicit KDE placement owns the final input rectangle. Let
                // the existing mesh settle towards it, including same-size
                // moves, without pulling the snapped window out of its slot.
                if(r->engine.snapping){world=std::make_unique<World>(w,r->engine);r->engine.snap(false);}
                r->engine.anchorPlacement();r->placementPending=false;
            }
            if(r->engine.grabbed&&!r->resize){
                auto mods=uint32_t(g_pInputManager->getModsFromAllKBs());
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
                if(r->settlePosition && WindowTypes::geometryManaged(w) && w->isFloating() && !max && w->windowTarget()){
                    auto b=w->geometricBox(Geo::GEOMETRIC_CURRENT);auto ext=w->getFullWindowExtents();
                    b.x=std::round(r->engine.model->topLeft.x+ext.topLeft.x);b.y=std::round(r->engine.model->topLeft.y+ext.topLeft.y);
                    g_layoutManager->setTargetGeom(b,w->windowTarget());w->positionAnimation()->warp();
                }
                detach(r);++finished;return true;
            }
        }catch(const std::exception& e){lastError=e.what();detach(r);return true;}
        return false;
    });
}

using Drag=Layout::Supplementary::CDragStateController;
using BeginFn=void(*)(Drag*,SP<Layout::ITarget>,eMouseBindMode,std::optional<Layout::eRectCorner>,bool);
using EndFn=bool(*)(Drag*);
using FullscreenFn=void(*)(Fullscreen::CFullscreenController*,PHLWINDOW,std::optional<Fullscreen::eFullscreenMode>,std::optional<Fullscreen::eFullscreenMode>,std::optional<bool>,Fullscreen::eFullscreenMutationContext);
using KeyFn=bool(*)(Keybinds::CKeybindManager*,std::any,SP<IKeyboard>);
using MouseStateFn=bool(*)(Layout::CLayoutManager*);
BeginFn originalBegin;EndFn originalEnd;FullscreenFn originalFullscreen;
KeyFn originalKey;MouseStateFn originalMouseState;
bool snapKeyEvent=false;
uint32_t modifierForKey(SP<IKeyboard> keyboard,uint32_t code){
    switch(xkb_state_key_get_one_sym(keyboard->m_xkbState,code)){
        case XKB_KEY_Shift_L:case XKB_KEY_Shift_R:return 1;
        case XKB_KEY_Caps_Lock:return 2;
        case XKB_KEY_Control_L:case XKB_KEY_Control_R:return 4;
        case XKB_KEY_Alt_L:case XKB_KEY_Alt_R:return 8;
        case XKB_KEY_Num_Lock:return 16;
        case XKB_KEY_Super_L:case XKB_KEY_Super_R:return 64;
        default:return 0;
    }
}
bool keyEvent(Keybinds::CKeybindManager* manager,std::any event,SP<IKeyboard> keyboard){
    auto target=g_layoutManager->dragController()->target();
    auto r=target?record(target->window()):nullptr;
    const auto key=std::any_cast<IKeyboard::SKeyEvent>(&event);
    // Hyprland normally ends a mouse drag on any key event. Compiz needs its
    // snapping modifier to be pressable/releasable during that same drag.
    snapKeyEvent=!stopping&&key&&r&&r->engine.grabbed&&!r->resize&&usable(r->window.lock())&&
        (modifierForKey(keyboard,key->keycode+8)&settings.snapModifiers);
    Hyprutils::Utils::CScopeGuard reset([]{snapKeyEvent=false;});
    return originalKey(manager,std::move(event),keyboard);
}
bool mouseState(Layout::CLayoutManager* manager){return snapKeyEvent?false:originalMouseState(manager);}
void begin(Drag* drag,SP<Layout::ITarget> target,eMouseBindMode mode,std::optional<Layout::eRectCorner> edge,bool exclusive){
    originalBegin(drag,target,mode,edge,exclusive);
    if(stopping||!target||drag->target()!=target)return;
    const bool hotkey=Config::Actions::state()->m_bindInvocationDepth>0;
    if(hotkey?!settings.hotkey_drag:!settings.normal_drag)return;
    auto w=target->window();if(!usable(w)||!settings.move_window_match.matches(info(w)))return;
    if(auto r=ensure(w)){
        auto p=Pointer::mgr()->position();r->resize=mode!=MBIND_MOVE;r->hotkey=hotkey;
        r->settlePosition=!r->resize;r->placementPending=false;r->engine.grab(p.x,p.y,settings.grab_window_match.matches(info(w)));++grabs;
    }
}
bool end(Drag* drag){
    auto target=drag->target();auto r=target?record(target->window()):nullptr;
    const bool ended=originalEnd(drag);
    if(ended&&r){r->engine.release(r->resize);damage(r);}
    return ended;
}
void fullscreen(Fullscreen::CFullscreenController* c,PHLWINDOW w,std::optional<Fullscreen::eFullscreenMode> internal,
                std::optional<Fullscreen::eFullscreenMode> client,std::optional<bool> aware,Fullscreen::eFullscreenMutationContext context){
    auto old=c->getFullscreenModes(w).internal;
    if(!stopping&&settings.maximize_effect&&usable(w)&&
       (old==Fullscreen::FSMODE_MAXIMIZED || internal==Fullscreen::FSMODE_MAXIMIZED || client==Fullscreen::FSMODE_MAXIMIZED)){
        if(auto r=ensure(w))r->engine.maximized=old==Fullscreen::FSMODE_MAXIMIZED;
    }
    originalFullscreen(c,w,internal,client,aware,context);
}
template<typename T>void hook(const std::string& name,const std::string& signature,const void* fn,T& original){
    for(auto& match:HyprlandAPI::findFunctionsByName(handle,name))if(Fusion057::symbolName(match).find(signature)!=std::string::npos){
        auto h=HyprlandAPI::createFunctionHook(handle,match.address,fn);if(!h||!h->hook())throw std::runtime_error("Cannot hook Wobbly: "+name);
        original=reinterpret_cast<T>(h->m_original);hooks.push_back(h);return;
    }throw std::runtime_error("Unsupported Wobbly API: "+name);
}
void cleanup(){
    stopping=true;listeners.clear();renderingMonitor.reset();clear();stopBell();
    bellImport.remove();
    for(auto h:std::views::reverse(hooks))h->unhook();
    hooks.clear();
    
}
}

APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h){
    handle=h;stopping=false;
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())throw std::runtime_error("Rebuild Wobbly for this Hyprland ABI");
    if(g_pHyprRenderer->type()!=Render::IHyprRenderer::RT_GL)throw std::runtime_error("Wobbly needs the OpenGL renderer");
    settings=Wobbly::readSettings(configPath());
    try{
        
        // The release compiler inlines XWM's selection-event handler. Observe
        // its stable libxcb boundary instead, filtering only our XWM connection.
        originalPoll=xcb_poll_for_event;
        if(!bellImport.install("xcb_poll_for_event",reinterpret_cast<void*>(originalPoll),
                               reinterpret_cast<void*>(pollX11Event)))
            throw std::runtime_error("Cannot observe X11 bell events");
        updateBell();
        hook("dragBegin","CDragStateController::dragBegin(",(void*)begin,originalBegin);
        hook("dragEnd","CDragStateController::dragEnd(",(void*)end,originalEnd);
        hook("setFullscreenMode","CFullscreenController::setFullscreenMode(",(void*)fullscreen,originalFullscreen);
        hook("onKeyEvent","CKeybindManager::onKeyEvent(",(void*)keyEvent,originalKey);
        hook("endDragTarget","CLayoutManager::endDragTarget(",(void*)mouseState,originalMouseState);
        hook("visibleOnMonitor","CWindowPresentation::visibleOnMonitor(",(void*)visibleOnMonitor,originalVisible);
        hook("renderWorkspaceWindowsFullscreen","Render::eSceneMode)",(void*)fullscreenWorkspace,originalFullscreenWorkspace);
        auto& events=Event::bus()->m_events;
        listeners.push_back(events.render.preChecks.listen([](PHLMONITOR m){preserveComposition(m);}));
        listeners.push_back(events.render.pre.listen([](PHLMONITOR m){renderingMonitor=m;frame(m);}));
        listeners.push_back(events.render.stage.listen([](const Event::SRenderStageEvent& event){
            if(event.stage!=RENDER_POST||g_pHyprRenderer->context().m_renderingSnapshot)return;
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
        Fusion057::addDispatcher(handle,"xetalwobbly:reload",[](std::string){
            try{auto next=Wobbly::readSettings(configPath());clear();settings=std::move(next);updateBell();lastError.clear();return SDispatchResult{};}
            catch(const std::exception& e){return SDispatchResult{.success=false,.error=e.what()};}
        });
        Fusion057::addDispatcher(handle,"xetalwobbly:shiver",[](std::string){
            auto w=Desktop::focusState()->window();if(!usable(w))return SDispatchResult{.success=false,.error="Enable Wobbly and focus a visible window"};
            shiver(w);return SDispatchResult{};
        });
        Fusion057::addDispatcher(handle,"xetalwobbly:anchorplacement",[](std::string id){
            if(id.empty()||id.size()>20||!std::ranges::all_of(id,[](char c){return c>='0'&&c<='9';}))
                return SDispatchResult{.success=false,.error="Invalid placement window ID"};
            for(const auto& r:records)if(auto w=r->window.lock();w&&id==std::to_string(w->metadata().stableID())){
                if(r->engine.grabbed)return SDispatchResult{.success=false,.error="Finish dragging before placing the window"};
                r->settlePosition=false;r->placementPending=true;damage(r);break;
            }
            return SDispatchResult{};
        });
        statusCommand=Fusion057::registerCommand(handle,{"xetal-wobbly",true,[](Fusion057::OutputFormat,std::string){
            std::string detail="[";
            for(auto& r:records){
                if(detail.size()>1)detail+=",";
                auto w=r->window.lock();auto& e=r->engine;double deviation=0;
                for(int i=0;i<16;++i)deviation=std::max(deviation,std::hypot(e.model->objects[i].position.x-e.box.x-(i%4)*e.box.w/3,e.model->objects[i].position.y-e.box.y-(i/4)*e.box.h/3));
                auto m=r->monitor.lock();
                const auto visual=Wobbly::renderBounds(e);
                detail+=std::format("{{\"grabbed\":{},\"hotkey\":{},\"monitor\":{},\"refresh_hz\":{},\"flags\":{},\"deviation\":{},\"snapping\":{},\"position_animating\":{},\"size_animating\":{},\"box\":[{},{},{},{}],\"render_bounds\":[{},{},{},{}]}}",
                    e.grabbed,r->hotkey,m?m->m_id:-1,m?m->m_refreshRate:0,e.active,deviation,e.snapping,w&&w->positionAnimation()->isBeingAnimated(),w&&w->sizeAnimation()->isBeingAnimated(),e.box.x,e.box.y,e.box.w,e.box.h,visual.x,visual.y,visual.w,visual.h);
            }
            detail+="]";
            std::string outputs="[";
            for(auto& m:State::monitorState()->monitors()){
                if(outputs.size()>1)outputs+=",";
                outputs+=std::format("{{\"id\":{},\"refresh_hz\":{},\"steps\":{},\"composited_frames\":{},\"crossing_frames\":{}}}",m->m_id,m->m_refreshRate,outputSteps[m->m_id],outputCompositedFrames[m->m_id],outputCrossingFrames[m->m_id]);
            }
            outputs+="]";
            auto error=json_object_new_string(lastError.c_str());std::string errorText=json_object_to_json_string_ext(error,JSON_C_TO_STRING_PLAIN);json_object_put(error);
            return std::format("{{\"enabled\":{},\"active\":{},\"started\":{},\"finished\":{},\"draws\":{},\"steps\":{},\"mesh_builds\":{},\"damage_ratio\":{},\"grabs\":{},\"shivers\":{},\"x11_bell\":{},\"wayland_bell\":{},\"error\":{},\"windows\":{},\"outputs\":{}}}",
                settings.enabled,records.size(),started,finished,draws,steps,meshBuilds,monitorPixels?damagePixels/monitorPixels:0,grabs,shivers,bellPhase==BellPhase::Ready,ipcSource!=nullptr,errorText,detail,outputs);
        }});
    }catch(...){cleanup();throw;}
    return {"Xetal Wobbly Windows","Original Compiz spring lattice, Bézier mesh and edge resistance","XetalEngine / David Reveman / Kristian Høgsberg","1.0"};
}
APICALL EXPORT void PLUGIN_EXIT(){cleanup();}
