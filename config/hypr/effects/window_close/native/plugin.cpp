// SPDX-License-Identifier: GPL-2.0-or-later
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/FloatState.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/managers/KeybindManager.hpp>
#include <hyprland/src/managers/fullscreen/FullscreenController.hpp>
#include <hyprland/src/layout/LayoutManager.hpp>
#include <hyprland/src/layout/space/Space.hpp>
#include <hyprland/src/layout/target/Target.hpp>
#include <hyprland/src/layout/algorithm/Algorithm.hpp>
#include <hyprland/src/layout/algorithm/FloatingAlgorithm.hpp>
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
#include <csignal>
#include <cerrno>
#include <limits>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <set>
#include <sstream>
#include "geometry.hpp"
#include "policies.hpp"
#include "background.hpp"

namespace {
using Clock = std::chrono::steady_clock;
HANDLE handle;
struct Settings { bool enabled=true, pulse=true; int modifier=64, size=34, inset=8; } settings;
std::array<double,3> accent{.224,.663,1};
std::vector<CHyprSignalListener> listeners;
SP<CEventLoopTimer> timer;
SP<SHyprCtlCommand> status,windowStatus;
enum Action { Minimize, Maximize, Close, Tile, Gear, None };
std::array<SP<Render::ITexture>,6> textures;
PHLWINDOWREF target, pressed, pending;
std::vector<PHLWINDOWREF> neverFloated;
std::array<CBox,5> buttons;
struct Row {PHLWINDOWREF window;std::array<CBox,5> boxes;WindowButtons::Rule rule;bool preview=false;};
std::vector<Row> rows;
WindowButtons::Rules appRules,windowRules;
WindowButtons::Backgrounds backgrounds;
struct Preview {PHLWINDOWREF window;WindowButtons::Rule rule;pid_t owner;std::string token;Clock::time_point expires;};
std::map<std::string,Preview> previews;
Action pressedAction=None,pendingAction=None;
bool held=false, superHeld=false,captured=false, stopping=false,waiting=false;
uint64_t closed=0, minimized=0, maximized=0, restored=0, floated=0, tiled=0, draws=0,openedSettings=0;
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
        else if(key=="size" && n>=10 && n<=64)next.size=n;
        else if(key=="inset" && n>=4 && n<=32)next.inset=n;
        else throw std::runtime_error("Unknown or out-of-range close setting");
    }
    if(seen!=std::set<std::string>{"enabled","modifier","size","inset","pulse"})
        throw std::runtime_error("Incomplete window close settings");
    return next;
}
std::filesystem::path sessionRulesPath(){
    const char* runtime=std::getenv("XDG_RUNTIME_DIR"),*instance=std::getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if(!runtime||!instance||std::string(instance).find('/')!=std::string::npos)throw std::runtime_error("Missing compositor session");
    return std::filesystem::path(runtime)/"hypr"/instance/"xetal-windowbuttons-rules.json";
}
void load(){
    auto next=readSettings();auto apps=WindowButtons::readRules(root()/"effects/window_close/rules.json","apps");
    auto windows=WindowButtons::readRules(sessionRulesPath(),"windows");
    settings=next;appRules=std::move(apps);windowRules=std::move(windows);
}
std::string appId(PHLWINDOW w){return w->m_initialClass.empty()?w->m_class:w->m_initialClass;}
WindowButtons::Rule ruleFor(PHLWINDOW w){
    if(auto it=windowRules.find(std::to_string(w->m_stableID));it!=windowRules.end())return it->second;
    if(auto it=appRules.find(appId(w));it!=appRules.end())return it->second;
    WindowButtons::Rule r;r.size=settings.size;r.x=r.y=settings.inset;return r;
}
Preview* previewFor(PHLWINDOW w){
    if(!w)return nullptr;
    auto it=previews.find(std::to_string(w->m_stableID));return it==previews.end()?nullptr:&it->second;
}
void prunePreviews(){
    std::erase_if(previews,[](const auto& item){
        const auto& preview=item.second;auto window=preview.window.lock();
        return !window||!window->m_isMapped||Clock::now()>=preview.expires||(kill(preview.owner,0)<0&&errno==ESRCH);
    });
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
void damage() {for(const auto& row:rows)for(const auto& button:row.boxes)if(!button.empty())g_pHyprRenderer->damageBox(CBox(button).expand(button.width));}
Action hit(Vector2D point){for(int i=0;i<5;++i)if(!buttons[i].empty()&&buttons[i].containsPoint(point))return Action(i);return None;}
bool restoring(PHLWINDOW w){return w&&(!w->m_isFloating||Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_NONE);}
bool available() {
    return !stopping && settings.enabled && g_pCompositor->m_sessionActive &&
        !g_pSessionLockManager->isSessionLocked() && !PROTO::inputCapture->isCaptured() && !PROTO::data->dndActive() &&
        !g_layoutManager->dragController()->target();
}
bool settled(PHLWINDOW w) {
    // Wobbly keeps its transformer attached after mouse release until the
    // lattice settles and the final input rectangle has been placed. Also
    // wait for native geometry/motion blur so these untransformed controls
    // never appear at a different position from the window they're acting on.
    return w && w->m_transformers.empty() && !w->positionAnimation()->isBeingAnimated() && !w->sizeAnimation()->isBeingAnimated() &&
        (!w->m_workspace||(!w->m_workspace->m_renderOffset->isBeingAnimated()&&!w->m_workspace->m_alpha->isBeingAnimated()));
}
void refresh() {
    damage();
    prunePreviews();
    const auto mods=g_pInputManager->getModsFromAllKBs();
    waiting=false;
    superHeld=available()&&mods==64;
    held=available() && (mods==uint32_t(settings.modifier)||superHeld);
    target.reset();buttons={};rows.clear();
    if(!available()){
        waiting=settings.enabled&&g_pCompositor->m_sessionActive&&!g_pSessionLockManager->isSessionLocked()&&
            bool(g_layoutManager->dragController()->target())&&(!appRules.empty()||!windowRules.empty()||!previews.empty());
        return;
    }
    const auto point=Pointer::mgr()->position();
    auto hovered=Desktop::viewState()->hitTest().windowAt(point,Desktop::View::ALLOW_FLOATING);
    if(hovered&&hovered->hasPopupAt(point))hovered.reset();
    if(hovered){
        Vector2D local;PHLLS layer;auto monitor=hovered->m_monitor.lock();
        if(monitor){
            for(int i:{3,2})if(Desktop::viewState()->hitTest().layerSurfaceAt(point,&monitor->m_layerSurfaceLayers[i],&local,&layer))hovered.reset();
            if(Desktop::viewState()->hitTest().layerPopupSurfaceAt(point,monitor,&local,&layer))hovered.reset();
        }
    }
    for(const auto& window:Desktop::windowState()->windows()){
        if(!window->m_isMapped||window->isHidden()||window->isX11OverrideRedirect()||window->m_class=="fusion-window-buttons")continue;
        const auto monitor=window->m_monitor.lock();
        if(!monitor||!g_pHyprRenderer->shouldRenderWindow(window,monitor))continue;
        const auto preview=previewFor(window);const bool isPreview=preview!=nullptr;
        auto rule=preview?preview->rule:ruleFor(window);const bool isHovered=hovered==window;
        if(!isPreview&&rule.mode!="always"&&!isHovered)continue;
        if(!settled(window)){waiting|=isPreview||rule.mode=="always"||(isHovered&&(held||rule.mode=="nearby"));continue;}
        if(window->popupsCount()>0){if(isPreview||rule.mode=="always")rows.push_back({window,{},rule,isPreview});continue;}
        auto box=window->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT).intersection(monitor->logicalBox());
        const double gap=std::max(2,rule.size/6);
        const double size=std::min({double(rule.size),(box.w-8-4*gap)/5.,box.h-8});
        if(size<10)continue;
        const double width=5*size+4*gap;
        const double x=std::clamp(rule.anchor.ends_with("right")?box.x+box.w-width-rule.x:
            rule.anchor.ends_with("center")?box.x+(box.w-width)/2+rule.x-8:box.x+rule.x,box.x+4,box.x+box.w-width-4);
        const double y=std::clamp(rule.anchor.starts_with("bottom")?box.y+box.h-size-rule.y:box.y+rule.y,box.y+4,box.y+box.h-size-4);
        Row row{window,{},rule,isPreview};
        const bool nearby=isHovered&&CBox{x,y,width,size}.expand(rule.proximity).containsPoint(point);
        if(isPreview||(rule.mode!="off"&&((held&&isHovered)||rule.mode=="always"||(rule.mode=="nearby"&&nearby)))){
            for(int i=0;i<3;++i)row.boxes[i]={x+(i+2)*(size+gap),y,size,size};
            row.boxes[Tile]={x+size+gap,y,size,size};
        }
        if(isPreview||(superHeld&&isHovered))row.boxes[Gear]={x+size*.08,y+size*.08,size*.84,size*.84};
        if(std::ranges::all_of(row.boxes,[](const CBox& b){return b.empty();}))continue;
        if(isHovered){target=window;buttons=row.boxes;}
        rows.push_back(row);
    }
    damage();
}
void arm(){if(timer)timer->updateTimeout(std::chrono::milliseconds(1));}
void createTexture(int glyph) {
    readAccent();
    constexpr int side=192;
    auto surface=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,side,side);
    auto cr=cairo_create(surface);cairo_scale(cr,3,3);
    // Shared glass buttons, with distinct minimize/maximize/restore/close art.
    auto halo=cairo_pattern_create_radial(32,32,12,32,32,32);
    cairo_pattern_add_color_stop_rgba(halo,0,accent[0],accent[1],accent[2],.65);
    cairo_pattern_add_color_stop_rgba(halo,1,accent[0],accent[1],accent[2],0);
    cairo_set_source(cr,halo);cairo_paint(cr);cairo_pattern_destroy(halo);
    auto round=[&]{double r=9; cairo_new_sub_path(cr);cairo_arc(cr,46-r,18+r,r,-M_PI/2,0);
        cairo_arc(cr,46-r,46-r,r,0,M_PI/2);cairo_arc(cr,18+r,46-r,r,M_PI/2,M_PI);
        cairo_arc(cr,18+r,18+r,r,M_PI,3*M_PI/2);cairo_close_path(cr);};
    round();cairo_set_source_rgba(cr,.025,.035,.05,.95);cairo_fill_preserve(cr);
    cairo_set_source_rgba(cr,accent[0],accent[1],accent[2],.97);cairo_set_line_width(cr,1.5);cairo_stroke(cr);
    if(glyph==0){cairo_move_to(cr,26,36);cairo_line_to(cr,38,36);}
    else if(glyph==1)cairo_rectangle(cr,26.5,26.5,11,11);
    else if(glyph==2){cairo_move_to(cr,29,28);cairo_line_to(cr,29,24.5);cairo_line_to(cr,39.5,24.5);cairo_line_to(cr,39.5,35);cairo_line_to(cr,36,35);cairo_rectangle(cr,24.5,28,11.5,11.5);}
    else if(glyph==3){cairo_move_to(cr,27,27);cairo_line_to(cr,37,37);cairo_move_to(cr,37,27);cairo_line_to(cr,27,37);}
    else if(glyph==5){
        cairo_rectangle(cr,24,25,16,14);cairo_move_to(cr,31,25);cairo_line_to(cr,31,39);
        cairo_move_to(cr,31,32);cairo_line_to(cr,40,32);
    } else {
        for(int i=0;i<=32;++i){const double a=i*M_PI/16.,r=(i%4==0||i%4==3)?9.:7.;
            if(i==0)cairo_move_to(cr,32+r*std::cos(a),32+r*std::sin(a));else cairo_line_to(cr,32+r*std::cos(a),32+r*std::sin(a));}
        cairo_close_path(cr);cairo_new_sub_path(cr);cairo_arc(cr,32,32,3.2,0,2*M_PI);
    }
    cairo_set_line_cap(cr,CAIRO_LINE_CAP_ROUND);cairo_set_line_width(cr,2.5);
    cairo_set_source_rgb(cr,.96,.98,1);cairo_stroke(cr);cairo_destroy(cr);cairo_surface_flush(surface);
    g_pHyprRenderer->glBackend()->makeEGLCurrent();
    textures[glyph]=g_pHyprRenderer->createTexture(DRM_FORMAT_ARGB8888,cairo_image_surface_get_data(surface),
                                         cairo_image_surface_get_stride(surface),Vector2D(side,side));
    cairo_surface_destroy(surface);
}
class ClosePass:public IPassElement {
    PHLMONITORREF monitor;
    Row row;
public:
    explicit ClosePass(PHLMONITOR m,const Row& r):monitor(m),row(r){}
    bool needsLiveBlur()override{return false;}
    bool needsPrecomputeBlur()override{return false;}
    const char* passName()override{return "FusionWindowClose";}
    ePassElementType type()override{return EK_CUSTOM;}
    bool disableSimplification()override{return true;}
    std::vector<UP<IPassElement>> draw()override {
        auto m=monitor.lock();auto w=row.window.lock();
        if(!m || !w || !available() || !settled(w))return {};
        CBox panel;
        for(int i=0;i<5;++i){
            const auto& button=row.boxes[i];if(button.empty()||(i==Gear&&!superHeld&&!row.preview))continue;
            if(panel.empty())panel=button;
            else {const double right=std::max(panel.x+panel.w,button.x+button.w),bottom=std::max(panel.y+panel.h,button.y+button.h);
                panel.x=std::min(panel.x,button.x);panel.y=std::min(panel.y,button.y);panel.w=right-panel.x;panel.h=bottom-panel.y;}
        }
        if(panel.empty())return {};
        panel=panel.expand(4).intersection(w->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT));
        panel=panel.intersection(m->logicalBox()).translate(-m->m_position).scale(m->m_scale);
        CHyprColor color;
        if(row.rule.background=="manual"){
            const auto rgb=std::stoul(row.rule.backgroundColor.substr(1),nullptr,16);
            color=CHyprColor{((rgb>>16)&255)/255.F,((rgb>>8)&255)/255.F,(rgb&255)/255.F,1};
        }else color=backgrounds.sample(w->m_stableID,m,panel);
        // The backing is solid, including the gaps. Only the artwork pulses;
        // fading the backing would expose the native toolbar underneath again.
        CRectPassElement::SRectData backing;backing.box=panel;backing.color=color;
        backing.round=std::round(std::min(10.,row.rule.size*.25)*m->m_scale);
        g_pHyprRenderer->draw(backing,g_pHyprRenderer->m_renderData.damage);
        const double elapsed=std::chrono::duration<double>(Clock::now()-epoch).count();
        for(int i=0;i<5;++i){
            const auto& button=row.boxes[i];if(button.empty()||(i==Gear&&!superHeld&&!row.preview))continue;
            const int glyph=i==Gear?4:i==Tile?5:i==Close?3:i==Maximize&&restoring(w)?2:i;
            if(!textures[glyph])createTexture(glyph);
            const bool hover=button.containsPoint(Pointer::mgr()->position());
            CTexPassElement::SRenderData data;data.tex=textures[glyph];
            // Artwork's central 28/64 is the full hit area; halo sits outside it.
            const double margin=button.width*18/28.;
            data.box=CBox(button).expand(margin).translate(-m->m_position).scale(m->m_scale);
            data.a=(hover?1.F:settings.pulse?float(.82+.18*std::sin(elapsed*4.5)):.9F)*w->effectiveAlpha();
            g_pHyprRenderer->draw(data,g_pHyprRenderer->m_renderData.damage);
        }
        ++draws;return {};
    }
};
void maximizeOrRestore(PHLWINDOW w){
    auto t=w->layoutTarget();if(!t||!t->space())return;
    const auto mode=Fullscreen::controller()->getFullscreenModes(w).internal;
    const bool wasTiled=!t->floating();
    if(!wasTiled&&mode==Fullscreen::FSMODE_NONE){
        t->rememberFloatingSize(t->position().size());
        Fullscreen::controller()->setFullscreenMode(w,Fullscreen::FSMODE_MAXIMIZED,Fullscreen::FSMODE_MAXIMIZED);
        ++maximized;return;
    }
    auto saved=t->lastFloatingSize();
    // A newly tiled target starts with the app's requested size, which may be
    // its fullscreen configure. That is not a previous floating size.
    if(wasTiled&&std::ranges::any_of(neverFloated,[&](const auto& weak){return weak.lock()==w;}))saved={};
    if(mode!=Fullscreen::FSMODE_NONE){
        Fullscreen::controller()->setFullscreenMode(w,Fullscreen::FSMODE_NONE,Fullscreen::FSMODE_NONE);
        // The fullscreen handler retains normal geometry, including resizes
        // made through native application decorations before maximizing.
        if(!wasTiled)saved=t->position().size();
    }
    const auto before=t->position();
    if(!WindowButtons::valid({saved.x,saved.y}))
        if(const auto cached=Desktop::floatState()->get(w))saved=*cached;
    if(!t->floating())g_layoutManager->changeFloatingMode(t);
    if(!t->floating()||!t->space())return;
    auto work=t->space()->workArea(true);
    const auto extents=w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
    work.x+=extents.topLeft.x;work.y+=extents.topLeft.y;
    work.w-=extents.topLeft.x+extents.bottomRight.x;work.h-=extents.topLeft.y+extents.bottomRight.y;
    const double margin=std::min({16.,work.w*.04,work.h*.04});work.expand(-margin);
    if(work.w<1||work.h<1)return;
    const auto minimum=t->minSize().value_or(Vector2D{}),maximum=t->maxSize().value_or(Vector2D{});
    const auto fit=WindowButtons::restore({work.x,work.y,work.w,work.h},{before.x,before.y,before.w,before.h},
        {saved.x,saved.y},{minimum.x,minimum.y},{maximum.x,maximum.y},wasTiled);
    // Update the floating layout's normal rectangle too; writing only the
    // target leaves maximize/restore pointing at the old pre-restore size.
    t->space()->algorithm()->floatingAlgo()->setTargetGeom(CBox{fit.x,fit.y,fit.w,fit.h},t);
    t->rememberFloatingSize({fit.w,fit.h});
    if(wasTiled)++floated;else ++restored;
}
void perform(PHLWINDOW w,Action action){
    if(action==Gear){
        if(auto preview=previewFor(w)){
            for(const auto& editor:Desktop::windowState()->windows())
                if(editor->m_isMapped&&!editor->isHidden()&&editor->m_class=="fusion-window-buttons"&&editor->getPID()==preview->owner){
                    Desktop::focusState()->fullWindowFocus(editor,Desktop::FOCUS_REASON_CLICK);Desktop::windowState()->raise(editor);break;
                }
            return;
        }
        if(!superHeld)return;
        std::string path=(root()/"effects/window_close/window_settings.py").string(),quoted="'";
        for(char c:path)quoted+=c=='\''?"'\\''":std::string(1,c);
        quoted+="'";
        auto result=g_pKeybindManager->m_dispatchers.at("exec")("[float; size 640 790; center] python3 "+quoted+" --window-id "+std::to_string(w->m_stableID));
        if(result.success)++openedSettings;
        return;
    }
    if(action==Close){w->sendClose();++closed;return;}
    if(action==Minimize){
        const auto it=g_pKeybindManager->m_dispatchers.find("xetalminimize:minimize");
        if(it!=g_pKeybindManager->m_dispatchers.end()){
            const auto result=it->second(std::format("address:0x{:x}",reinterpret_cast<uintptr_t>(w.get())));
            if(result.success){++minimized;return;}
        }
        HyprlandAPI::addNotification(handle,"Enable Minimize in Theme → Window effects to use this button.",CHyprColor(accent[0],accent[1],accent[2],1),4000);
        return;
    }
    Desktop::focusState()->fullWindowFocus(w,Desktop::FOCUS_REASON_CLICK);
    if(action==Tile){
        // Tiling is a layout operation, separate from maximizing. Leave the
        // normal floating rectangle intact for the next Restore action.
        Fullscreen::controller()->setFullscreenMode(w,Fullscreen::FSMODE_NONE,Fullscreen::FSMODE_NONE);
        if(auto t=w->layoutTarget();t&&t->floating()){
            t->rememberFloatingSize(t->position().size());
            g_layoutManager->changeFloatingMode(t);
        }
        ++tiled;
    }else maximizeOrRestore(w);
    Desktop::windowState()->raise(w);
}
void tick(SP<CEventLoopTimer> self,void*) {
    refresh();
    const auto w=pending.lock();const auto action=pendingAction;pending.reset();pendingAction=None;
    if(w && w->m_isMapped && !w->isHidden() && available() && settled(w)){perform(w,action);refresh();}
    if(held || captured || waiting || !rows.empty() || !previews.empty())self->updateTimeout(std::chrono::milliseconds(25));
}
void cleanup() {
    stopping=true;damage();listeners.clear();target.reset();pressed.reset();pending.reset();neverFloated.clear();
    if(timer){timer->cancel();g_pEventLoopManager->removeTimer(timer);timer.reset();}
    g_pHyprRenderer->m_renderPass.removeAllOfType("FusionWindowClose");
    g_pHyprRenderer->glBackend()->makeEGLCurrent();backgrounds.clear();textures={};buttons={};rows.clear();previews.clear();
}
}
APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle=h;stopping=false;
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())throw std::runtime_error("Rebuild window close for this compositor ABI");
    if(g_pHyprRenderer->type()!=Render::IHyprRenderer::RT_GL)throw std::runtime_error("Window close needs the OpenGL renderer");
    load();
    try {
        timer=makeShared<CEventLoopTimer>(std::nullopt,tick,nullptr);g_pEventLoopManager->addTimer(timer);
        listeners.push_back(Event::bus()->m_events.input.keyboard.key.listen([](IKeyboard::SKeyEvent,Event::SCallbackInfo&){arm();}));
        listeners.push_back(Event::bus()->m_events.input.mouse.move.listen([](Vector2D,Event::SCallbackInfo&){arm();}));
        listeners.push_back(Event::bus()->m_events.window.openLate.listen([](PHLWINDOW w){if(!w->m_isFloating)neverFloated.emplace_back(w);arm();}));
        listeners.push_back(Event::bus()->m_events.window.floating.listen([](PHLWINDOW w){
            if(w->m_isFloating)std::erase_if(neverFloated,[&](const auto& weak){return !weak.lock()||weak.lock()==w;});
        }));
        listeners.push_back(Event::bus()->m_events.window.close.listen([](PHLWINDOW w){
            g_pHyprRenderer->glBackend()->makeEGLCurrent();backgrounds.erase(w->m_stableID);
            std::erase_if(neverFloated,[&](const auto& weak){return !weak.lock()||weak.lock()==w;});windowRules.erase(std::to_string(w->m_stableID));
            // Closing either the edited window or its editor ends the preview.
            std::erase_if(previews,[&](const auto& p){return p.second.window.lock()==w||(w->m_class=="fusion-window-buttons"&&p.second.owner==w->getPID());});arm();
        }));
        listeners.push_back(Event::bus()->m_events.monitor.layoutChanged.listen([](){arm();}));
        listeners.push_back(Event::bus()->m_events.workspace.active.listen([](PHLWORKSPACE){arm();}));
        listeners.push_back(Event::bus()->m_events.workspace.specialActive.listen([](PHLWORKSPACE,PHLMONITOR){arm();}));
        listeners.push_back(Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent event,Event::SCallbackInfo& info){
            // Recheck after the drag controller sees this press/release. This
            // also restores the button after a drag with Super still held.
            arm();
            if(event.button!=BTN_LEFT)return;
            if(event.state==WL_POINTER_BUTTON_STATE_RELEASED && captured){
                captured=false;info.cancelled=true;refresh();
                if(pressed.lock()==target.lock() && hit(Pointer::mgr()->position())==pressedAction){pending=pressed;pendingAction=pressedAction;}
                pressed.reset();pressedAction=None;arm();return;
            }
            if(info.cancelled || event.state!=WL_POINTER_BUTTON_STATE_PRESSED)return;
            refresh();const auto action=hit(Pointer::mgr()->position());if(target.lock() && action!=None){
                captured=true;pressed=target;pressedAction=action;info.cancelled=true;
            }
        }));
        listeners.push_back(Event::bus()->m_events.render.stage.listen([](eRenderStage stage){
            if(stage!=RENDER_POST_WINDOW || !available() || g_pHyprRenderer->m_bRenderingSnapshot)return;
            auto w=g_pHyprRenderer->m_renderData.currentWindow.lock();auto m=g_pHyprRenderer->m_renderData.pMonitor.lock();
            // Draw in the owning window's stack, so another window or panel
            // naturally covers its buttons. Never draw a desktop-wide overlay.
            if(w&&m&&settled(w)&&w->m_monitor.lock()==m)
                for(const auto& row:rows)if(row.window.lock()==w)g_pHyprRenderer->addPassElement(makeUnique<ClosePass>(m,row));
        }));
        HyprlandAPI::addDispatcherV2(handle,"xetalwindowclose:reload",[](std::string){
            try{load();textures={};refresh();arm();return SDispatchResult{};}
            catch(const std::exception& error){return SDispatchResult{.success=false,.error=error.what()};}
        });
        HyprlandAPI::addDispatcherV2(handle,"xetalwindowclose:preview",[](std::string input){
            try{
                if(input.size()>4096)throw std::runtime_error("Window preview is too large");
                auto doc=WindowButtons::parseJson(input);
                auto string=[&](const char* name){return std::string(json_object_get_string(WindowButtons::field(doc.get(),name,json_type_string)));};
                const auto id=string("id"),token=string("token"),action=string("action");
                if(id.empty()||id.size()>20||!std::ranges::all_of(id,[](char c){return c>='0'&&c<='9';})||
                   token.size()!=32||!std::ranges::all_of(token,[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))throw std::runtime_error("Invalid preview identity");
                damage();prunePreviews();auto existing=previews.find(id);
                if(action=="end"){
                    if(existing!=previews.end()&&existing->second.token==token)previews.erase(existing);
                }else if(action=="update"){
                    auto owner=json_object_get_int64(WindowButtons::field(doc.get(),"owner",json_type_int));
                    if(owner<1||owner>std::numeric_limits<pid_t>::max()||(kill(pid_t(owner),0)<0&&errno==ESRCH))throw std::runtime_error("The window editor has closed");
                    if(existing!=previews.end()&&(existing->second.token!=token||existing->second.owner!=owner))throw std::runtime_error("This window is already being previewed in another editor");
                    auto rule=WindowButtons::readRule(WindowButtons::field(doc.get(),"rule",json_type_object));
                    PHLWINDOW window;
                    for(const auto& w:Desktop::windowState()->windows())if(w->m_isMapped&&id==std::to_string(w->m_stableID)&&w->m_class!="fusion-window-buttons"){window=w;break;}
                    if(!window)throw std::runtime_error("This window has closed");
                    if(existing==previews.end()&&previews.size()>=64)throw std::runtime_error("Too many window previews");
                    previews.insert_or_assign(id,Preview{window,rule,pid_t(owner),token,Clock::now()+std::chrono::seconds(4)});
                }else throw std::runtime_error("Unknown preview action");
                refresh();arm();return SDispatchResult{};
            }catch(const std::exception& error){return SDispatchResult{.success=false,.error=error.what()};}
        });
        status=HyprlandAPI::registerHyprCtlCommand(handle,{"xetal-windowclose",true,[](eHyprCtlOutputFormat,std::string){
            const auto& button=buttons[Close];std::string items;
            for(int i=0;i<4;++i){const auto& b=buttons[i];if(i)items+=",";
                const auto name=i==Tile?"tile":i==Close?"close":i==Minimize?"minimize":restoring(target.lock())?"restore":"maximize";
                items+=std::format("{{\"action\":\"{}\",\"box\":[{},{},{},{}]}}",name,b.x,b.y,b.w,b.h);
            }
            const auto& gear=buttons[Gear];
            return std::format("{{\"enabled\":{},\"held\":{},\"visible\":{},\"closed\":{},\"draws\":{},\"box\":[{},{},{},{}],\"color\":[{},{},{}],\"buttons\":[{}],\"minimized\":{},\"maximized\":{},\"restored\":{},\"floated\":{},\"gear\":[{},{},{},{}],\"gear_visible\":{},\"settings_opened\":{},\"tiled\":{}}}",
                settings.enabled,held,available()&&settled(target.lock())&&!button.empty(),closed,draws,button.x,button.y,button.width,button.height,accent[0],accent[1],accent[2],items,minimized,maximized,restored,floated,
                gear.x,gear.y,gear.w,gear.h,available()&&!gear.empty()&&settled(target.lock()),openedSettings,tiled);
        }});
        windowStatus=HyprlandAPI::registerHyprCtlCommand(handle,{"xetal-windowbuttons",false,[](eHyprCtlOutputFormat,std::string input){
            std::istringstream stream(input);std::string command,id,extra;stream>>command>>id;
            if(id.empty()){
                std::string ids;for(const auto& w:Desktop::windowState()->windows())if(w->m_isMapped){if(!ids.empty())ids+=",";ids+=WindowButtons::quoted(std::to_string(w->m_stableID));}
                return "{\"windows\":["+ids+"]}";
            }
            if(!(stream>>extra))for(const auto& w:Desktop::windowState()->windows())if(w->m_isMapped&&id==std::to_string(w->m_stableID)){
                auto rule=WindowButtons::ruleJson(ruleFor(w));
                auto preview=previewFor(w);auto previewRule=WindowButtons::ruleJson(preview?preview->rule:ruleFor(w));std::string boxes="[]";
                for(const auto& row:rows)if(row.preview&&row.window.lock()==w){
                    boxes="[";for(const auto& b:row.boxes){if(boxes.size()>1)boxes+=",";boxes+=std::format("[{},{},{},{}]",b.x,b.y,b.w,b.h);}boxes+="]";break;
                }
                const auto box=w->geometricBox(Desktop::View::IGeometric::GEOMETRIC_CURRENT);
                const auto sampled=std::format("{{\"ready\":{},\"color\":\"#{:06x}\"}}",backgrounds.ready(w->m_stableID),backgrounds.last(w->m_stableID).getAsHex()&0xffffff);
                return std::format("{{\"id\":\"{}\",\"app\":{},\"address\":\"0x{:x}\",\"rule\":{},\"window_override\":{},\"app_override\":{},\"size\":[{},{}],\"preview\":{},\"preview_rule\":{},\"preview_boxes\":{},\"auto_background\":{}}}",
                    id,WindowButtons::quoted(appId(w)),reinterpret_cast<uintptr_t>(w.get()),json_object_to_json_string_ext(rule.get(),JSON_C_TO_STRING_PLAIN),windowRules.contains(id),appRules.contains(appId(w)),
                    box.w,box.h,bool(preview),json_object_to_json_string_ext(previewRule.get(),JSON_C_TO_STRING_PLAIN),boxes,sampled);
            }
            return std::string("{\"error\":\"This window has closed.\"}");
        }});
        arm();
    }catch(...){cleanup();throw;}
    return {"Xetal Window Close","Theme-aware window controls with live per-window previews","XetalEngine","1.5"};
}
APICALL EXPORT void PLUGIN_EXIT(){cleanup();}
