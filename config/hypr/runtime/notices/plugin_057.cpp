// SPDX-License-Identifier: GPL-2.0-or-later
// Always loaded by the managed session, independently of the Compiz setting.
#include "../native_057.hpp"
#include <hyprland/src/config/ConfigValue.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/render/transformer/WobbleTransformer.hpp>
#include <hyprland/src/render/transformer/TransformerList.hpp>

namespace {
CFunctionHook* nativeWobbleHook=nullptr;
CHyprSignalListener reloadListener;
bool refuseNativeWobble(PHLWINDOW){return false;}
void enforcePolicy(){
    CConfigValue<bool> enabled("decoration:wobble:enabled");
    *enabled.ptr()=false;
    for(const auto& window:Desktop::windowState()->windows())window->effects().resetWobble();
}
void cleanup(){
    reloadListener.reset();
    if(nativeWobbleHook){nativeWobbleHook->unhook();nativeWobbleHook=nullptr;}
}
}
APICALL EXPORT std::string PLUGIN_API_VERSION(){return HYPRLAND_API_VERSION;}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle){
    if(std::string(__hyprland_api_get_hash())!=__hyprland_api_get_client_hash())
        throw std::runtime_error("Hyper Fusion runtime policy needs rebuilding for this Hyprland ABI");
    try{
        for(const auto& match:HyprlandAPI::findFunctionsByName(handle,"shouldEnable")){
            if(!Fusion057::symbolName(match).starts_with("Render::CWobbleTransformer::shouldEnable("))continue;
            nativeWobbleHook=HyprlandAPI::createFunctionHook(handle,match.address,reinterpret_cast<void*>(refuseNativeWobble));
            break;
        }
        if(!nativeWobbleHook||!nativeWobbleHook->hook())
            throw std::runtime_error("Cannot enforce Hyper Fusion's Compiz-only wobble policy");
        reloadListener=Event::bus()->m_events.config.reloaded.listen(enforcePolicy);
        enforcePolicy();
        Fusion057::registerCommand(handle,{"xetal-runtime-policy",true,[](Fusion057::OutputFormat,std::string){
            size_t active=0;
            bool blocked=nativeWobbleHook!=nullptr;
            for(const auto& window:Desktop::windowState()->windows()){
                blocked=blocked&&!Render::CWobbleTransformer::shouldEnable(window);
                const auto& list=window->effects().transformers();
                const auto native=list?list->get<Render::CWobbleTransformer>():nullptr;
                if(native&&native->active())++active;
            }
            return std::format("{{\"native_wobble\":{},\"active_native_windows\":{},\"compiz_only\":true,\"enforced\":{}}}",
                               active!=0,active,blocked&&active==0);
        }});
    }catch(...){cleanup();throw;}
    return {"Hyper Fusion startup notices","Enforce the Compiz-only runtime policy","XetalEngine","2.0"};
}
APICALL EXPORT void PLUGIN_EXIT(){cleanup();}
