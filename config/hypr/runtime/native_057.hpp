// SPDX-License-Identifier: GPL-2.0-or-later
// Hyprland 0.57 adapter boundary. The 0.56 adapters remain independently buildable.
#pragma once
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/desktop/view/window/Window.hpp>
#include <hyprland/src/desktop/view/window/WindowBackend.hpp>
#include <hyprland/src/desktop/view/window/WindowPresentation.hpp>
#include <hyprland/src/desktop/view/window/WindowFullscreenPolicy.hpp>
#include <hyprland/src/desktop/view/window/WindowGroupMembership.hpp>
#include <hyprland/src/desktop/view/window/WindowEffectsController.hpp>
#include <hyprland/src/workspace/HLWorkspace.hpp>
#include <hyprland/src/layout/target/WindowTarget.hpp>
#include <hyprland/src/ipc/s1/S1.hpp>
#include <hyprland/src/config/shared/actions/ConfigActions.hpp>
#include <hyprland/src/protocols/core/Compositor.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/xwayland/XWayland.hpp>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <dlfcn.h>
#include <array>
#include <functional>
#include <stdexcept>
#include <cxxabi.h>
extern "C" {
#include <lua.h>
#include <lauxlib.h>
}

namespace Fusion057 __attribute__((visibility("hidden"))) {
static_assert(std::string_view(GIT_COMMIT_HASH)=="11cbc6c577b84ffb1edf4df3fc5b6128c3ae6947",
              "The 0.57 adapter requires the tested compositor headers");
using Command = IPC::Socket1::SCommand;
using OutputFormat = IPC::Socket1::eOutputFormat;
inline std::string symbolName(const SFunctionMatch& symbol) {
    int status=-1;
    std::unique_ptr<char,decltype(&std::free)> name(
        abi::__cxa_demangle(symbol.signature.c_str(),nullptr,nullptr,&status),&std::free);
    return status==0&&name?name.get():std::string{};
}
struct CommandSpec {
    std::string name;
    bool exact;
    std::function<std::string(OutputFormat, std::string)> handler;
};
inline SP<Command> registerCommand(HANDLE handle, CommandSpec spec) {
    auto command = HyprlandAPI::registerHyprCtlCommand(handle, {
        .name = std::move(spec.name),
        .match = spec.exact ? IPC::Socket1::COMMAND_MATCH_EXACT : IPC::Socket1::COMMAND_MATCH_PREFIX,
        .handler = [fn=std::move(spec.handler)](const IPC::Socket1::SRequest& request) -> IPC::Socket1::SResponse {
            return fn(request.format, request.command);
        },
    });
    if (!command) throw std::runtime_error("Cannot register Hyper Fusion IPC command");
    return command;
}

// Keep function storage local to each shared object. The compositor removes
// its Lua registrations before unloading that object, including on init errors.
namespace {
std::array<std::function<SDispatchResult(std::string)>, 64> actions;
size_t actionCount = 0;
template<size_t N> int luaAction(lua_State* state) {
    size_t length=0;
    const auto arg=luaL_optlstring(state,1,"",&length);
    SDispatchResult result;
    try { result=actions[N](std::string(arg,length)); }
    catch(const std::exception& error) { result.success=false;result.error=error.what(); }
    lua_createtable(state,0,4);
    lua_pushboolean(state,result.success);lua_setfield(state,-2,"success");
    lua_pushboolean(state,result.passEvent);lua_setfield(state,-2,"pass_event");
    lua_pushboolean(state,result.requestRelease);lua_setfield(state,-2,"request_release");
    if(!result.success){lua_pushlstring(state,result.error.data(),result.error.size());lua_setfield(state,-2,"error");}
    return 1;
}
template<size_t... N> constexpr auto callbacks(std::index_sequence<N...>) {
    return std::array<PLUGIN_LUA_FN,sizeof...(N)>{luaAction<N>...};
}
}
inline void addDispatcher(HANDLE handle,const std::string& name,std::function<SDispatchResult(std::string)> fn) {
    const auto colon=name.find(':');
    if(colon==std::string::npos||!colon||colon+1==name.size()||actionCount==actions.size())
        throw std::runtime_error("Invalid Hyper Fusion plugin action: "+name);
    static constexpr auto functions=callbacks(std::make_index_sequence<64>{});
    actions[actionCount]=std::move(fn);
    if(!HyprlandAPI::addLuaFunction(handle,name.substr(0,colon),name.substr(colon+1),functions[actionCount]))
        throw std::runtime_error("Cannot register Hyper Fusion plugin action: "+name);
    ++actionCount;
}
inline SDispatchResult result(const Config::Actions::ActionResult& value) {
    if(!value)return {.success=false,.error=value.error().message};
    return {.passEvent=value->passEvent};
}
inline std::string luaString(const std::string& value){
    std::string out="\"";
    for(unsigned char c:value){
        if(c=='"'||c=='\\'){out+='\\';out+=c;}
        else if(c<32||c==127)out+=std::format("\\{:03}",c);
        else out+=c;
    }
    return out+'"';
}
inline SDispatchResult dispatchPlugin(const std::string& name,const std::string& args){
    const auto colon=name.find(':');
    if(colon==std::string::npos)return {.success=false,.error="Invalid plugin action"};
    const auto expression="function() local p=hl.plugin["+luaString(name.substr(0,colon))+"] "
        "local f=p and p["+luaString(name.substr(colon+1))+"] "
        "if not f then return {success=false,error='Hyper Fusion effect is unavailable'} end return f("+luaString(args)+") end";
    const auto reply=HyprlandAPI::invokeHyprctlCommand("dispatch",expression);
    return {.success=reply=="ok"||reply=="ok\n",.error=reply=="ok"||reply=="ok\n"?"":reply};
}
inline WP<CXDGSurfaceResource> xdg(PHLWINDOW window) {
    if(!window||window->backend().isX11())return {};
    auto surface=window->backend().surface();
    const auto role=surface?dynamicPointerCast<CXDGSurfaceRole>(surface->m_role):nullptr;
    return role?role->m_xdgSurface:WP<CXDGSurfaceResource>{};
}
inline WP<CXWaylandSurface> x11(PHLWINDOW window) {
    if(!window||!window->backend().isX11()||!g_pXWayland||!g_pXWayland->m_wm)return {};
    // Use the pinned compositor's lookup, without reading private object fields.
    using Lookup=SP<CXWaylandSurface>(*)(CXWM*,uint32_t);
    static const auto lookup=reinterpret_cast<Lookup>(dlsym(RTLD_DEFAULT,"_ZN4CXWM12windowForXIDEj"));
    if(!lookup)throw std::runtime_error("Unsupported Hyprland X11 surface lookup");
    return lookup(g_pXWayland->m_wm.get(),window->backend().clientID().id);
}
inline bool special(PHLWORKSPACE workspace){return workspace->type()==Workspace::eWorkspaceType::SPECIAL;}
inline int64_t numberedID(PHLWORKSPACE workspace){return workspace->numberedID().value_or(0);}
inline bool pinned(PHLWINDOW window){return bool(window->m_state&Desktop::View::WINDOW_STATE_PINNED);}
inline void setPinned(PHLWINDOW window,bool value){
    if(value)window->m_state|=Desktop::View::WINDOW_STATE_PINNED;
    else window->m_state&=~Desktop::View::WINDOW_STATE_PINNED;
}
}
