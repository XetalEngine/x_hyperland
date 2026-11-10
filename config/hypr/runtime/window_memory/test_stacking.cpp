// Exercise the production adapter against a small model of the pinned core's
// distinct input stack and floating-over-fullscreen rendering plane.
#include <algorithm>
#include <cassert>
#include <map>
#include <memory>
#include <ranges>
#include <string>
#include <vector>
struct Window;
struct Workspace;
using PHLWINDOW=std::shared_ptr<Window>;
using PHLWORKSPACE=std::shared_ptr<Workspace>;
struct Monitor {int rechecks=0;void recheckSolitary(){++rechecks;}};
struct Workspace {int m_id=1;std::weak_ptr<Monitor> m_monitor;PHLWINDOW fullscreen;};
struct Alpha {
    float current=1,desired=1;
    float value()const{return current;}
    float goal()const{return desired;}
    void setValueAndWarp(float n){current=desired=n;}
};
struct Window {
    PHLWORKSPACE m_workspace;
    bool m_isMapped=true,hidden=false,m_isFloating=true,m_pinned=false,managed=true;
    bool m_allowedOverFullscreen=true,blocked=false,otherInputBlock=false;
    int geometry=42;
    std::shared_ptr<Alpha> opacity=std::make_shared<Alpha>();
    bool isHidden()const{return hidden;}
    bool isBlockedByFullscreen()const{return m_workspace->fullscreen && m_workspace->fullscreen.get()!=this && !m_pinned && !m_allowedOverFullscreen;}
    void updateFullscreenInputState(){blocked=isBlockedByFullscreen();}
    auto& alpha(int){return opacity;}
};
namespace Desktop {
namespace View {constexpr int WINDOW_ALPHA_FULLSCREEN=0;}
struct CWindowState {std::vector<PHLWINDOW> items;const auto& windows(){return items;}} state;
auto windowState(){return &state;}
}
namespace WindowTypes {bool geometryManaged(PHLWINDOW w){return w->managed;}}
namespace Fullscreen {
struct Controller {auto getFullscreenWindow(PHLWORKSPACE ws){return ws->fullscreen;}} instance;
auto controller(){return &instance;}
}
namespace WorkspaceRules {
struct Policy {std::string layout="off";};
bool floats(const Policy& p){return p.layout=="floating"||p.layout=="kde";}
auto forWorkspace(const std::map<int,Policy>& p,int id){auto i=p.find(id);return i==p.end()?Policy{}:i->second;}
}
std::map<int,WorkspaceRules::Policy> workspaceRules;
struct Renderer {
    int windows=0,monitors=0;
    void damageWindow(PHLWINDOW,bool full){assert(full);++windows;}
    void damageMonitor(std::shared_ptr<Monitor>){++monitors;}
} renderer;
auto g_pHyprRenderer=&renderer;
#include "stacking.hpp"

void nativeMove(Desktop::CWindowState* state,PHLWINDOW w,bool top) {
    if(!w||!w->m_isMapped)return;
    w->m_allowedOverFullscreen=top;w->updateFullscreenInputState();
    w->opacity->setValueAndWarp(w->isBlockedByFullscreen()?0:1);
    std::erase(state->items,w);
    state->items.insert(top?state->items.end():state->items.begin(),w);
}
PHLWINDOW input(PHLWORKSPACE ws) {
    for(const auto& w:std::views::reverse(Desktop::state.items))
        if(w->m_workspace==ws&&!w->blocked&&!w->otherInputBlock)return w;
    return nullptr;
}
PHLWINDOW drawn(PHLWORKSPACE ws) {
    auto top=ws->fullscreen;
    for(const auto& w:Desktop::state.items)
        if(w->m_workspace==ws&&w!=ws->fullscreen&&w->m_allowedOverFullscreen&&w->opacity->value()>0)top=w;
    return top;
}
int main() {
    WorkspaceStack::originalMove=nativeMove;
    for(const auto& mode:{"floating","kde"}) {
        auto monitor=std::make_shared<Monitor>();
        auto ws=std::make_shared<Workspace>();ws->m_monitor=monitor;
        auto chrome=std::make_shared<Window>(),media=std::make_shared<Window>();
        chrome->m_workspace=media->m_workspace=ws;ws->fullscreen=chrome;
        workspaceRules={{1,{mode}}};Desktop::state.items={chrome,media};renderer={};
        // Reproduce the reported ghost: core raises Chrome for input, but Media
        // retains its separate rendering permission. No app names in the fix.
        nativeMove(&Desktop::state,chrome,true);
        assert(input(ws)==chrome&&drawn(ws)==media);
        WorkspaceStack::move(&Desktop::state,chrome,true);
        assert(input(ws)==chrome&&drawn(ws)==chrome&&media->blocked);
        assert(media->opacity->value()==0&&renderer.windows==1&&monitor->rechecks==1);
        assert(chrome->geometry==42&&media->geometry==42&&ws->fullscreen==chrome);
        const auto damage=renderer.windows;
        WorkspaceStack::move(&Desktop::state,chrome,true);
        assert(renderer.windows==damage); // an already reconciled click is idle
        WorkspaceStack::move(&Desktop::state,media,true);
        assert(input(ws)==media&&drawn(ws)==media&&!media->blocked&&media->opacity->value()==1);
        WorkspaceStack::move(&Desktop::state,media,false);
        assert(input(ws)==chrome&&drawn(ws)==chrome&&media->opacity->value()==0);
        WorkspaceStack::move(&Desktop::state,chrome,false);
        assert(input(ws)==media&&drawn(ws)==media&&!media->blocked);
        // Repair a stale in-flight fade as well as a stale permission flag.
        media->opacity->current=.4;media->opacity->desired=0;media->otherInputBlock=true;
        WorkspaceStack::reconcile(ws);
        assert(media->opacity->value()==1&&media->otherInputBlock);
        // Other workspaces and protocol-owned menus must not be modified.
        auto other=std::make_shared<Window>();other->m_workspace=std::make_shared<Workspace>();other->m_workspace->m_id=2;
        auto menu=std::make_shared<Window>();menu->m_workspace=ws;menu->managed=false;
        auto pinned=std::make_shared<Window>();pinned->m_workspace=ws;pinned->m_pinned=true;
        auto hidden=std::make_shared<Window>();hidden->m_workspace=ws;hidden->hidden=true;
        auto unmapped=std::make_shared<Window>();unmapped->m_workspace=ws;unmapped->m_isMapped=false;
        auto tiled=std::make_shared<Window>();tiled->m_workspace=ws;tiled->m_isFloating=false;
        Desktop::state.items={other,menu,pinned,hidden,unmapped,tiled,media,chrome};
        WorkspaceStack::reconcile(ws);
        for(auto w:{other,menu,pinned,hidden,unmapped,tiled})assert(w->m_allowedOverFullscreen&&w->opacity->value()==1&&!w->blocked);
        assert(!media->m_allowedOverFullscreen&&media->opacity->value()==0);
        // With no maximized/fullscreen owner, ordinary floating order suffices.
        ws->fullscreen.reset();media->opacity->setValueAndWarp(1);media->blocked=false;
        renderer={};WorkspaceStack::reconcile(ws);assert(renderer.windows==0);
        ws->fullscreen=chrome;
        for(const auto& individual:{"off","tile"}) {
            workspaceRules[1].layout=individual;media->m_allowedOverFullscreen=true;
            WorkspaceStack::move(&Desktop::state,chrome,true);
            assert(media->m_allowedOverFullscreen&&media->opacity->value()==1);
        }
        ws->fullscreen.reset(); // break the test-only shared ownership cycle
    }
    WorkspaceStack::reconcile(nullptr);
    WorkspaceStack::move(&Desktop::state,nullptr,true);
}
