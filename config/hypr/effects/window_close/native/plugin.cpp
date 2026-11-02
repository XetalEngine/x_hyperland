// SPDX-License-Identifier: GPL-2.0-or-later
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/layout/LayoutManager.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/protocols/InputCapture.hpp>
#include <hyprland/src/protocols/core/DataDevice.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/render/pass/TexPassElement.hpp>
#include <hyprland/src/render/OpenGL.hpp>
#include <cairo/cairo.h>
#include <drm_fourcc.h>
#include <linux/input-event-codes.h>
#include <array>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <set>
#include <sstream>

namespace {
using Clock = std::chrono::steady_clock;
HANDLE handle;
struct Settings { bool enabled=true, pulse=true; int modifier=64, size=34, inset=8; } settings;
std::array<double,3> accent{.224,.663,1};
std::vector<CHyprSignalListener> listeners;
SP<CEventLoopTimer> timer;
SP<SHyprCtlCommand> status;
SP<Render::ITexture> texture;
PHLWINDOWREF target, pressed, pending;
CBox button;
bool held=false, captured=false, stopping=false;
uint64_t closed=0, draws=0;
const auto epoch=Clock::now();

std::filesystem::path root() {
    const char* home=std::getenv("HOME");
    if(!home)throw std::runtime_error("No home directory for window close settings");
    return std::filesystem::path(home)/".config/hypr";
}
Settings readSettings() {
    std::ifstream file(root()/"effects/window_close/settings.conf");
    if(!file)throw std::runtime_error("Cannot read window close settings");
    Settings next;std::string line;std::set<std::string> seen;
    while(std::getline(file,line)) {
        if(line.empty() || line[0]=='#')continue;
        const auto pos=line.find('=');if(pos==std::string::npos)throw std::runtime_error("Invalid window close setting");
        const auto key=line.substr(0,pos),value=line.substr(pos+1);
        if(!seen.insert(key).second)throw std::runtime_error("Duplicate window close setting");
        if(key=="modifier") {
            if(value=="SUPER")next.modifier=64;
            else if(value=="ALT")next.modifier=8;
            else if(value=="SUPER+SHIFT")next.modifier=65;
            else throw std::runtime_error("Unknown close modifier");
            continue;
        }
        size_t used;int n=std::stoi(value,&used);if(used!=value.size())throw std::runtime_error("Invalid close value");
        if(key=="enabled" && (n==0 || n==1))next.enabled=n;
        else if(key=="pulse" && (n==0 || n==1))next.pulse=n;
        else if(key=="size" && n>=24 && n<=64)next.size=n;
        else if(key=="inset" && n>=4 && n<=32)next.inset=n;
        else throw std::runtime_error("Unknown or out-of-range close setting");
    }
    if(seen!=std::set<std::string>{"enabled","modifier","size","inset","pulse"})
        throw std::runtime_error("Incomplete window close settings");
    return next;
}
void readAccent() {
    std::ifstream colors(root()/"theme/current.colors");std::string line;bool window=false;
    while(std::getline(colors,line)) {
        if(line.starts_with('[')){window=line=="[Colors:Window]";continue;}
        if(!window || !line.starts_with("DecorationFocus="))continue;
        std::istringstream stream(line.substr(16));int r,g,b;char c,d;
        if(stream>>r>>c>>g>>d>>b && c==',' && d==',' && r>=0 && r<=255 && g>=0 && g<=255 && b>=0 && b<=255)
            accent={r/255.,g/255.,b/255.};
    }
}
void damage() {if(!button.empty())g_pHyprRenderer->damageBox(CBox(button).expand(button.width));}
bool available() {
    return !stopping && settings.enabled && g_pCompositor->m_sessionActive &&
        !g_pSessionLockManager->isSessionLocked() && !PROTO::inputCapture->isCaptured() && !PROTO::data->dndActive() &&
        !g_layoutManager->dragController()->target();
}
void refresh() {
    damage();
    held=available() && g_pInputManager->getModsFromAllKBs()==uint32_t(settings.modifier);
    target.reset();button={};if(!held)return;
    const auto point=Pointer::mgr()->position();
    auto window=Desktop::viewState()->hitTest().windowAt(point,Desktop::View::ALLOW_FLOATING);
    if(!window || !window->m_isMapped || window->isHidden())return;
    const auto monitor=window->m_monitor.lock();if(!monitor)return;
    Vector2D local;PHLLS layer;
    // Panels, menus, and lock surfaces must never activate a window below them.
    for(int i:{3,2})if(Desktop::viewState()->hitTest().layerSurfaceAt(point,&monitor->m_layerSurfaceLayers[i],&local,&layer))return;
    if(Desktop::viewState()->hitTest().layerPopupSurfaceAt(point,monitor,&local,&layer))return;
    auto box=window->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
    if(box.width<settings.size+settings.inset*2 || box.height<settings.size+settings.inset*2)return;
    button={box.x+box.width-settings.size-settings.inset,box.y+settings.inset,double(settings.size),double(settings.size)};
    target=window;damage();
}
void arm(){if(timer)timer->updateTimeout(std::chrono::milliseconds(1));}
void createTexture() {
    readAccent();
    constexpr int side=192;
    auto surface=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,side,side);
    auto cr=cairo_create(surface);cairo_scale(cr,3,3);
    // Soft accent halo, dark glass center, bright outline, and a clear cross.
    auto halo=cairo_pattern_create_radial(32,32,12,32,32,32);
    cairo_pattern_add_color_stop_rgba(halo,0,accent[0],accent[1],accent[2],.65);
    cairo_pattern_add_color_stop_rgba(halo,1,accent[0],accent[1],accent[2],0);
    cairo_set_source(cr,halo);cairo_paint(cr);cairo_pattern_destroy(halo);
    auto round=[&]{double r=9; cairo_new_sub_path(cr);cairo_arc(cr,46-r,18+r,r,-M_PI/2,0);
        cairo_arc(cr,46-r,46-r,r,0,M_PI/2);cairo_arc(cr,18+r,46-r,r,M_PI/2,M_PI);
        cairo_arc(cr,18+r,18+r,r,M_PI,3*M_PI/2);cairo_close_path(cr);};
    round();cairo_set_source_rgba(cr,.025,.035,.05,.95);cairo_fill_preserve(cr);
    cairo_set_source_rgba(cr,accent[0],accent[1],accent[2],.97);cairo_set_line_width(cr,1.5);cairo_stroke(cr);
    cairo_move_to(cr,27,27);cairo_line_to(cr,37,37);cairo_move_to(cr,37,27);cairo_line_to(cr,27,37);
    cairo_set_line_cap(cr,CAIRO_LINE_CAP_ROUND);cairo_set_line_width(cr,2.5);
    cairo_set_source_rgb(cr,.96,.98,1);cairo_stroke(cr);cairo_destroy(cr);cairo_surface_flush(surface);
    g_pHyprRenderer->glBackend()->makeEGLCurrent();
    texture=g_pHyprRenderer->createTexture(DRM_FORMAT_ARGB8888,cairo_image_surface_get_data(surface),
                                         cairo_image_surface_get_stride(surface),Vector2D(side,side));
    cairo_surface_destroy(surface);
}
class ClosePass:public IPassElement {
    PHLMONITORREF monitor;
public:
    explicit ClosePass(PHLMONITOR m):monitor(m){}
    bool needsLiveBlur()override{return false;}
    bool needsPrecomputeBlur()override{return false;}
    const char* passName()override{return "FusionWindowClose";}
    ePassElementType type()override{return EK_CUSTOM;}
    bool disableSimplification()override{return true;}
    std::vector<UP<IPassElement>> draw()override {
        auto m=monitor.lock();auto w=target.lock();
        if(!m || !w || !held || !available() || button.empty())return {};
        if(!texture)createTexture();
        const double elapsed=std::chrono::duration<double>(Clock::now()-epoch).count();
        const bool hover=button.containsPoint(Pointer::mgr()->position());
        CTexPassElement::SRenderData data;data.tex=texture;
        // Artwork's central 28/64 is the full hit area; halo sits outside it.
        const double margin=button.width*18/28.;
        data.box=CBox(button).expand(margin).translate(-m->m_position).scale(m->m_scale);
        data.a=hover?1.F:settings.pulse?float(.82+.18*std::sin(elapsed*4.5)):.9F;
        g_pHyprRenderer->draw(data,g_pHyprRenderer->m_renderData.damage);++draws;return {};
    }
};
void tick(SP<CEventLoopTimer> self,void*) {
    refresh();
    if(auto w=pending.lock();w && w->m_isMapped && available()){pending.reset();w->sendClose();++closed;}
    else pending.reset();
    if(held || captured)self->updateTimeout(std::chrono::milliseconds(25));
}
void cleanup() {
    stopping=true;damage();listeners.clear();target.reset();pressed.reset();pending.reset();
    if(timer){timer->cancel();g_pEventLoopManager->removeTimer(timer);timer.reset();}
    g_pHyprRenderer->m_renderPass.removeAllOfType("FusionWindowClose");texture.reset();
}
}
APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle=h;stopping=false;
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())throw std::runtime_error("Rebuild window close for this compositor ABI");
    if(g_pHyprRenderer->type()!=Render::IHyprRenderer::RT_GL)throw std::runtime_error("Window close needs the OpenGL renderer");
    settings=readSettings();
    try {
        timer=makeShared<CEventLoopTimer>(std::nullopt,tick,nullptr);g_pEventLoopManager->addTimer(timer);
        listeners.push_back(Event::bus()->m_events.input.keyboard.key.listen([](IKeyboard::SKeyEvent,Event::SCallbackInfo&){arm();}));
        listeners.push_back(Event::bus()->m_events.input.mouse.move.listen([](Vector2D,Event::SCallbackInfo&){arm();}));
        listeners.push_back(Event::bus()->m_events.window.close.listen([](PHLWINDOW){arm();}));
        listeners.push_back(Event::bus()->m_events.monitor.layoutChanged.listen([](){arm();}));
        listeners.push_back(Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent event,Event::SCallbackInfo& info){
            // Recheck after the drag controller sees this press/release. This
            // also restores the button after a drag with Super still held.
            arm();
            if(event.button!=BTN_LEFT)return;
            if(event.state==WL_POINTER_BUTTON_STATE_RELEASED && captured){
                captured=false;info.cancelled=true;refresh();
                if(held && pressed.lock()==target.lock() && button.containsPoint(Pointer::mgr()->position()))pending=pressed;
                pressed.reset();arm();return;
            }
            if(info.cancelled || event.state!=WL_POINTER_BUTTON_STATE_PRESSED)return;
            refresh();if(target.lock() && button.containsPoint(Pointer::mgr()->position())){
                captured=true;pressed=target;info.cancelled=true;
            }
        }));
        listeners.push_back(Event::bus()->m_events.render.stage.listen([](eRenderStage stage){
            if(stage!=RENDER_LAST_MOMENT || !held || !available() || g_pHyprRenderer->m_bRenderingSnapshot)return;
            auto w=target.lock();auto m=g_pHyprRenderer->m_renderData.pMonitor.lock();
            if(w && m && w->m_monitor.lock()==m)g_pHyprRenderer->addPassElement(makeUnique<ClosePass>(m));
        }));
        HyprlandAPI::addDispatcherV2(handle,"xetalwindowclose:reload",[](std::string){
            try{settings=readSettings();texture.reset();refresh();arm();return SDispatchResult{};}
            catch(const std::exception& error){return SDispatchResult{.success=false,.error=error.what()};}
        });
        status=HyprlandAPI::registerHyprCtlCommand(handle,{"xetal-windowclose",true,[](eHyprCtlOutputFormat,std::string){
            return std::format("{{\"enabled\":{},\"held\":{},\"visible\":{},\"closed\":{},\"draws\":{},\"box\":[{},{},{},{}],\"color\":[{},{},{}]}}",
                settings.enabled,held,available()&&bool(target.lock()),closed,draws,button.x,button.y,button.width,button.height,accent[0],accent[1],accent[2]);
        }});
    }catch(...){cleanup();throw;}
    return {"Xetal Window Close","Theme-aware modifier-held close buttons","XetalEngine","1.0"};
}
APICALL EXPORT void PLUGIN_EXIT(){cleanup();}
