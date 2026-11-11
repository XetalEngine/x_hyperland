// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2022-2026, vaxerski. See ../NOTICE for the license.
// Adapted from pinned Hyprland 0.56.2 Renderer.cpp. Keep its passes and policy
// checks; defer only admitted crossing windows to the existing foreground pass.
// Included after the native compositor types, also exercised by a fake renderer.
#pragma once

namespace Wobbly {
struct FullscreenRenderAccess:Render::IHyprRenderer {
    static void paint(Render::IHyprRenderer* renderer,PHLWINDOW w,PHLMONITOR monitor,const Time::steady_tp& time,bool decorate){
        // The pinned renderWindow API is protected. Form its inherited member
        // pointer here and invoke it on the real base object, without downcasts
        // or changing the compositor's headers/access specifiers.
        constexpr auto method=&FullscreenRenderAccess::renderWindow;
        (renderer->*method)(w,monitor,time,decorate,Render::RENDER_PASS_ALL,false,false);
    }
};
template<class IsCrossing>
void renderFullscreenWorkspace(Render::IHyprRenderer* renderer,PHLMONITOR pMonitor,
                               PHLWORKSPACE pWorkspace,const Time::steady_tp& time,IsCrossing crossing){
    PHLWINDOW pWorkspaceWindow=nullptr;
    Event::bus()->m_events.render.stage.emit(RENDER_PRE_WINDOWS);
    std::vector<PHLWINDOW> windows;
    for(const auto& w:Desktop::windowState()->windows()){
        if(!renderer->shouldRenderWindow(w,pMonitor))continue;
        if(w->alphaValue(Desktop::View::WINDOW_ALPHA_FADE)*w->alphaValue(Desktop::View::WINDOW_ALPHA_FULLSCREEN)==0.f)continue;
        if(Fullscreen::controller()->isFullscreen(w))continue;
        windows.emplace_back(w);
    }
    for(const auto& w:windows){
        if(w->m_isFloating || pWorkspace->m_isSpecialWorkspace!=w->onSpecialWorkspace())continue;
        FullscreenRenderAccess::paint(renderer,w,pMonitor,time,true);
    }
    renderer->renderFadeouts(pMonitor,Desktop::FADEOUT_PLANE_WINDOW_TILED,pWorkspace);
    for(const auto& w:windows){
        if(!w->m_isFloating)continue;
        if(w->m_monitor==pWorkspace->m_monitor && pWorkspace->m_isSpecialWorkspace!=w->onSpecialWorkspace())continue;
        if(pWorkspace->m_isSpecialWorkspace && w->m_monitor!=pWorkspace->m_monitor)continue;
        // A crossing float must be painted once, above the background, even
        // after its owning workspace changes to the neighboring monitor.
        if(w->isFadingOutUnderFullscreen() || crossing(w))continue;
        FullscreenRenderAccess::paint(renderer,w,pMonitor,time,true);
    }
    renderer->renderFadeouts(pMonitor,Desktop::FADEOUT_PLANE_WINDOW_FLOATING,pWorkspace);
    for(const auto& w:Desktop::windowState()->windows()){
        const auto PWORKSPACE=w->m_workspace;
        if(w->m_workspace!=pWorkspace || !Fullscreen::controller()->isFullscreen(w)){
            if(!(PWORKSPACE && (PWORKSPACE->m_renderOffset->isBeingAnimated() ||
                 PWORKSPACE->m_alpha->isBeingAnimated() || PWORKSPACE->m_forceRendering)))continue;
            if(w->m_monitor!=pMonitor)continue;
        }
        if(!Fullscreen::controller()->isFullscreen(w))continue;
        if(w->m_monitor==pWorkspace->m_monitor && pWorkspace->m_isSpecialWorkspace!=w->onSpecialWorkspace())continue;
        if(renderer->shouldRenderWindow(w,pMonitor))
            FullscreenRenderAccess::paint(renderer,w,pMonitor,time,
                Fullscreen::controller()->getFullscreenModes(pWorkspace).internal!=Fullscreen::FSMODE_FULLSCREEN);
        if(w->m_workspace==pWorkspace)pWorkspaceWindow=w;
    }
    if(!pWorkspaceWindow){
        // A render listener may have removed the background since admission.
        // Do not lose windows deferred from the ordinary floating pass.
        for(const auto& w:windows)if(crossing(w))FullscreenRenderAccess::paint(renderer,w,pMonitor,time,true);
        return;
    }
    // Use the compositor's global stack, not record/creation order. Keep other
    // foreground windows, popups and fading overlays in their existing planes.
    for(const auto& w:Desktop::windowState()->windows()){
        const bool shouldSkipWindow=(w->workspaceID()!=pWorkspaceWindow->workspaceID() && !crossing(w)) ||
            !w->m_isFloating || !w->shouldRenderOverFullscreen() || !w->m_isMapped || Fullscreen::controller()->isFullscreen(w);
        if(shouldSkipWindow)continue;
        if(w->m_monitor==pWorkspace->m_monitor && pWorkspace->m_isSpecialWorkspace!=w->onSpecialWorkspace())continue;
        if(pWorkspace->m_isSpecialWorkspace && w->m_monitor!=pWorkspace->m_monitor)continue;
        FullscreenRenderAccess::paint(renderer,w,pMonitor,time,true);
    }
    renderer->renderFadeouts(pMonitor,Desktop::FADEOUT_PLANE_WINDOW_OVER_FULLSCREEN,pWorkspace);
}
} // namespace Wobbly
