// Exercise the actual pass-ordering implementation with a recording renderer.
// No display, GL context or running compositor is needed for these assertions.
#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <memory>
#include <vector>

struct Monitor {};
struct Workspace;
struct Window;
using PHLMONITOR=std::shared_ptr<Monitor>;
using PHLWORKSPACE=std::shared_ptr<Workspace>;
using PHLWINDOW=std::shared_ptr<Window>;
namespace Time {using steady_tp=std::chrono::steady_clock::time_point;}
enum {RENDER_PRE_WINDOWS};
namespace Render {enum {RENDER_PASS_ALL};}
struct Animation {bool active=false;bool isBeingAnimated()const{return active;}};
struct Workspace {
    int id,mode=0;
    bool m_isSpecialWorkspace=false,m_forceRendering=false;
    PHLMONITOR m_monitor;
    std::shared_ptr<Animation> m_renderOffset=std::make_shared<Animation>(),m_alpha=std::make_shared<Animation>();
};
struct Window {
    int id;
    PHLWORKSPACE m_workspace;
    PHLMONITOR m_monitor;
    bool m_isFloating=true,m_isMapped=true,fullscreen=false,over=true,fading=false,renderable=true,hidden=false;
    float alpha=1;
    int workspaceID()const{return m_workspace->id;}
    bool onSpecialWorkspace()const{return m_workspace->m_isSpecialWorkspace;}
    float alphaValue(int)const{return alpha;}
    bool isFadingOutUnderFullscreen()const{return fading;}
    bool shouldRenderOverFullscreen()const{return over;}
};
namespace Desktop {
namespace View {enum {WINDOW_ALPHA_FADE,WINDOW_ALPHA_FULLSCREEN};}
enum {FADEOUT_PLANE_WINDOW_TILED=-1,FADEOUT_PLANE_WINDOW_FLOATING=-2,FADEOUT_PLANE_WINDOW_OVER_FULLSCREEN=-3};
struct State {std::vector<PHLWINDOW> list;auto& windows(){return list;}};
State* windowState(){static State state;return &state;}
}
namespace Event {
struct Stage {int count=0;void emit(int){++count;}};
struct Bus {struct {struct {Stage stage;} render;} m_events;};
Bus* bus(){static Bus bus;return &bus;}
}
namespace Fullscreen {
enum {FSMODE_MAXIMIZED=1,FSMODE_FULLSCREEN=2};
struct Modes {int internal;};
struct Controller {
    bool isFullscreen(PHLWINDOW w){return w->fullscreen;}
    Modes getFullscreenModes(PHLWORKSPACE ws){return {ws->mode};}
};
Controller* controller(){static Controller controller;return &controller;}
}
namespace Render {
struct IHyprRenderer {
    std::vector<int> draws;
    bool backgroundDecorated=true;
    bool shouldRenderWindow(PHLWINDOW w,PHLMONITOR){return w->renderable && w->m_isMapped && !w->hidden;}
  protected:
    void renderWindow(PHLWINDOW w,PHLMONITOR,const Time::steady_tp&,bool decorate,int mode,bool ignorePosition,bool standalone){
        assert(!ignorePosition && !standalone);
        assert(mode==RENDER_PASS_ALL); // child popups stay with their window
        if(!w->m_isMapped || w->hidden)return;
        if(w->fullscreen)backgroundDecorated=decorate;
        draws.push_back(w->id);
    }
  public:
    void renderFadeouts(PHLMONITOR,int plane,PHLWORKSPACE){draws.push_back(plane);}
};
}
#include "fullscreen_pass.hpp"

int main(){
    const auto left=std::make_shared<Monitor>(),right=std::make_shared<Monitor>();
    const auto a=std::make_shared<Workspace>(Workspace{.id=2,.m_monitor=left});
    const auto b=std::make_shared<Workspace>(Workspace{.id=3,.m_monitor=right});
    auto add=[&](int id,PHLWORKSPACE ws){
        auto w=std::make_shared<Window>(Window{.id=id,.m_workspace=ws,.m_monitor=ws->m_monitor});
        Desktop::windowState()->list.push_back(w);return w;
    };
    auto under=add(1,a);under->over=false;
    auto background=add(2,a);background->fullscreen=true;
    auto lowerCrossing=add(3,b);
    auto localOverlay=add(4,a);
    auto upperCrossing=add(5,b);
    auto hidden=add(6,b);hidden->hidden=true;hidden->renderable=false;
    auto minimized=add(7,b);minimized->renderable=false;
    const Time::steady_tp now{};
    auto position=[](const auto& draws,int id){return std::ranges::find(draws,id)-draws.begin();};
    // The same scene fails at either seam, with maximized AND fullscreen
    // backgrounds. Swap monitors/workspaces to exercise both directions.
    for(int mode:{Fullscreen::FSMODE_MAXIMIZED,Fullscreen::FSMODE_FULLSCREEN})for(bool reverse:{false,true}){
        a->mode=mode;
        a->m_monitor=reverse?right:left;b->m_monitor=reverse?left:right;
        for(auto w:Desktop::windowState()->list)w->m_monitor=w->m_workspace->m_monitor;
        Render::IHyprRenderer old;
        Wobbly::renderFullscreenWorkspace(&old,a->m_monitor,a,now,[](PHLWINDOW){return false;});
        // Old policy paints the crossing once, then covers it with the
        // maximized/fullscreen background because its workspace differs.
        assert(position(old.draws,3)<position(old.draws,2));
        assert(position(old.draws,5)<position(old.draws,2));
        Render::IHyprRenderer fixed;
        // Reverse admission order: record creation order must not set Z order.
        const std::vector<PHLWINDOW> admitted{upperCrossing,lowerCrossing};
        auto crossing=[&](PHLWINDOW w){return std::ranges::find(admitted,w)!=admitted.end();};
        Wobbly::renderFullscreenWorkspace(&fixed,a->m_monitor,a,now,crossing);
        assert(std::ranges::count(fixed.draws,3)==1 && std::ranges::count(fixed.draws,5)==1);
        auto lastBackground=position(fixed.draws,2);
        auto foreground=std::vector<int>(fixed.draws.begin()+lastBackground+1,fixed.draws.end());
        assert((foreground==std::vector<int>{3,4,5,Desktop::FADEOUT_PLANE_WINDOW_OVER_FULLSCREEN}));
        assert(position(fixed.draws,1)<lastBackground);
        assert(std::ranges::count(fixed.draws,6)==0 && std::ranges::count(fixed.draws,7)==0);
        assert(fixed.backgroundDecorated==(mode==Fullscreen::FSMODE_MAXIMIZED));
        // Once the mesh departs, using the untouched policy restores exactly
        // the original stack; no persistent raise or workspace mutation.
        Render::IHyprRenderer settled;
        Wobbly::renderFullscreenWorkspace(&settled,a->m_monitor,a,now,[](PHLWINDOW){return false;});
        assert(settled.draws==old.draws);
        assert(lowerCrossing->m_workspace==b && upperCrossing->m_workspace==b);
    }
    // If a render listener removes the background, deferred windows still draw.
    background->fullscreen=false;
    Render::IHyprRenderer removed;
    Wobbly::renderFullscreenWorkspace(&removed,a->m_monitor,a,now,[&](PHLWINDOW w){return w==upperCrossing;});
    assert(std::ranges::count(removed.draws,5)==1);
    std::cout<<"Fullscreen and maximized crossing render order passed\n";
}
