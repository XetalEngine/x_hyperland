// Observe real partial-damage regions without screencopy or forcing a repaint.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/view/WLSurface.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/render/Renderer.hpp>

namespace {
std::vector<CFunctionHook*> hooks;
SP<SHyprCtlCommand> command;
using DamageFn=void (*)(Render::IHyprRenderer*,SP<CWLSurfaceResource>,double,double,double);
DamageFn originalDamage;
int commits=0;
CBox lastDamage;
bool fixture(PHLWINDOW w){return w&&w->m_class=="fusion-text-damage-fixture";}
void damage(Render::IHyprRenderer* renderer,SP<CWLSurfaceResource> resource,double x,double y,double scale){
    const auto surface=Desktop::View::CWLSurface::fromResource(resource);
    const auto w=surface?Desktop::View::CWindow::fromView(surface->view()):nullptr;
    if(fixture(w)&&w->wlSurface()==surface){++commits;lastDamage=surface->computeDamage().getExtents();}
    originalDamage(renderer,resource,x,y,scale);
}
template<typename T> void hook(HANDLE handle,const std::string& name,const std::string& signature,const void* replacement,T& original){
    for(const auto& match:HyprlandAPI::findFunctionsByName(handle,name)){
        if(match.demangled.find(signature)==std::string::npos)continue;
        auto h=HyprlandAPI::createFunctionHook(handle,match.address,replacement);
        if(!h||!h->hook())throw std::runtime_error("Probe hook failed: "+name);
        original=reinterpret_cast<T>(h->m_original);hooks.push_back(h);return;
    }
    throw std::runtime_error("Probe API missing: "+name);
}
}
APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle){
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())throw std::runtime_error("Probe ABI mismatch");
    hook(handle,"damageSurface","IHyprRenderer::damageSurface(",(void*)damage,originalDamage);
    command=HyprlandAPI::registerHyprCtlCommand(handle,{"fusion-text-damage",true,[](eHyprCtlOutputFormat,std::string){
        return std::format("{{\"commits\":{},\"damage\":[{},{},{},{}]}}",
            commits,lastDamage.x,lastDamage.y,lastDamage.w,lastDamage.h);
    }});
    return {"Text damage test probe","Observe partial repaints without screencopy","XetalEngine","1.0"};
}
APICALL EXPORT void PLUGIN_EXIT(){for(auto h:std::views::reverse(hooks))h->unhook();hooks.clear();command.reset();}
