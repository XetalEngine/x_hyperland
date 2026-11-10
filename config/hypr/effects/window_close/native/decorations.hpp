// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <hyprland/src/protocols/WaylandProtocol.hpp>
#include <hyprland/protocols/xdg-decoration-unstable-v1.hpp>
#include <hyprland/protocols/kde-server-decoration.hpp>
#include <hyprland/src/protocols/XDGShell.hpp>
#include <hyprland/src/xwayland/XDataSource.hpp>
#include <hyprland/src/xwayland/Dnd.hpp>
#include <xcb/res.h>
#include <xcb/xfixes.h>
#include <xcb/composite.h>
#include <xcb/xcb_errors.h>
#include <hyprutils/os/FileDescriptor.hpp>
#include <cinttypes>
#include <hyprland/src/xwayland/XSurface.hpp>
#include <xcb/xcbext.h>
#include <unordered_map>
#include <vector>
#include <cstring>
// This read-only adapter is pinned by build.py to Hyprland 0.56.2. The
// protocol exposes no public lookup by window. Do not modify negotiation,
// resources, callbacks or the client buffers to discover decorations.
#define private public
#include <hyprland/src/xwayland/XWM.hpp>
#include <hyprland/src/protocols/XDGDecoration.hpp>
#include <hyprland/src/protocols/ServerDecorationKDE.hpp>
#undef private
#include <hyprland/src/xwayland/XWayland.hpp>

namespace WindowButtons {
enum class Decoration { Pending, Client, Server };
inline const char* decorationName(Decoration d){
    return d==Decoration::Client?"client":d==Decoration::Server?"server":"pending";
}

// X11 queries are asynchronous on the compositor's existing connection.
// Never wait for an X client or start a helper from the render/input path.
class Decorations {
    struct Probe {uint32_t xid=0,frame=0,motif=0;bool client=false;Decoration result=Decoration::Pending;
                  std::chrono::steady_clock::time_point next{};};
    std::map<uint64_t,Probe> probes;
    xcb_connection_t* connection=nullptr;
    uint32_t frameAtom=0,motifAtom=0,frameRequest=0,motifRequest=0;
    static bool reply(xcb_connection_t* c,uint32_t& sequence,void*& result){
        if(!sequence)return true;
        xcb_generic_error_t* error=nullptr;
        if(!xcb_poll_for_reply(c,sequence,&result,&error))return false;
        free(error);sequence=0;return true;
    }
    bool atoms(xcb_connection_t* c){
        if(c!=connection){
            probes.clear();connection=c;frameAtom=motifAtom=0;
            const char *frame="_GTK_FRAME_EXTENTS",*motif="_MOTIF_WM_HINTS";
            frameRequest=xcb_intern_atom(c,0,strlen(frame),frame).sequence;
            motifRequest=xcb_intern_atom(c,0,strlen(motif),motif).sequence;
            xcb_flush(c);
        }
        void* value=nullptr;
        if(reply(c,frameRequest,value)&&value){frameAtom=((xcb_intern_atom_reply_t*)value)->atom;free(value);}
        value=nullptr;
        if(reply(c,motifRequest,value)&&value){motifAtom=((xcb_intern_atom_reply_t*)value)->atom;free(value);}
        return frameAtom&&motifAtom;
    }
    Decoration x11(PHLWINDOW w){
        if(!g_pXWayland||!g_pXWayland->m_wm||!w->m_xwaylandSurface)return Decoration::Pending;
        auto c=g_pXWayland->m_wm->getConnection();if(!c||!atoms(c))return Decoration::Pending;
        auto& p=probes[w->m_stableID];const auto now=std::chrono::steady_clock::now();
        if(!p.frame&&!p.motif&&now>=p.next){
            p.xid=w->m_xwaylandSurface->m_xID;p.client=false;
            p.frame=xcb_get_property(c,0,p.xid,frameAtom,XCB_GET_PROPERTY_TYPE_ANY,0,4).sequence;
            p.motif=xcb_get_property(c,0,p.xid,motifAtom,XCB_GET_PROPERTY_TYPE_ANY,0,5).sequence;
            p.next=now+std::chrono::seconds(2);xcb_flush(c);
        }
        if(p.frame){
            void* value=nullptr;
            if(reply(c,p.frame,value)&&value){
                auto r=static_cast<xcb_get_property_reply_t*>(value);
                p.client|=r->format==32&&r->value_len==4;free(value);
            }
        }
        if(p.motif){
            void* value=nullptr;
            if(reply(c,p.motif,value)&&value){
                auto r=static_cast<xcb_get_property_reply_t*>(value);
                if(r->format==32&&r->value_len>=3){
                    auto v=static_cast<const uint32_t*>(xcb_get_property_value(r));
                    // Decorations explicitly disabled: client owns its frame.
                    p.client|=(v[0]&2)&&v[2]==0;
                }
                free(value);
            }
        }
        if(!p.frame&&!p.motif)p.result=p.client?Decoration::Client:Decoration::Server;
        return p.result;
    }
  public:
    Decoration get(PHLWINDOW w){
        if(w->m_isX11)return x11(w);
        if(!w->m_xdgSurface)return Decoration::Pending;
        if(PROTO::xdgDecoration)for(const auto& [resource,deco]:PROTO::xdgDecoration->m_decorations){
            auto top=CXDGToplevelResource::fromResource(resource);
            if(top&&top->m_window.lock()==w)
                return deco->mostRecentlyRequested==1?Decoration::Client:Decoration::Server;
        }
        if(PROTO::serverDecorationKDE)for(const auto& deco:PROTO::serverDecorationKDE->m_decos)
            if(deco->m_surf==w->m_xdgSurface->m_surface.lock())
                return deco->m_mostRecentlyRequested==1?Decoration::Client:Decoration::Server;
        // Without decoration negotiation Wayland clients own their frame.
        // A frameless client may not provide buttons: the gear's Always/Off
        // overrides deliberately remain available for this ambiguous case.
        return Decoration::Client;
    }
    void erase(uint64_t id){
        auto it=probes.find(id);if(it==probes.end())return;
        if(g_pXWayland&&g_pXWayland->m_wm&&connection==g_pXWayland->m_wm->getConnection())
            for(auto sequence:{it->second.frame,it->second.motif})if(sequence)xcb_discard_reply(connection,sequence);
        probes.erase(it);
    }
    void clear(){
        while(!probes.empty())erase(probes.begin()->first);
        if(g_pXWayland&&g_pXWayland->m_wm&&connection==g_pXWayland->m_wm->getConnection())
            for(auto sequence:{frameRequest,motifRequest})if(sequence)xcb_discard_reply(connection,sequence);
        connection=nullptr;frameAtom=motifAtom=frameRequest=motifRequest=0;
    }
};
}
