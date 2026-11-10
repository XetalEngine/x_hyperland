// SPDX-License-Identifier: GPL-2.0-or-later
// Included after the native workspace policy reader. Core raises reorder the
// input stack, but do not revoke other windows' over-fullscreen render plane.
namespace WorkspaceStack {
bool eligible(PHLWINDOW w,PHLWORKSPACE ws) {
    return w && w->m_isMapped && !w->isHidden() && w->m_workspace==ws &&
        w->m_isFloating && !w->m_pinned && WindowTypes::geometryManaged(w);
}
void reconcile(PHLWORKSPACE ws) {
    if(!ws || !WorkspaceRules::floats(WorkspaceRules::forWorkspace(workspaceRules,ws->m_id)))return;
    const auto fullscreen=Fullscreen::controller()->getFullscreenWindow(ws);
    if(!eligible(fullscreen,ws))return;
    const auto& windows=Desktop::windowState()->windows();
    if(std::ranges::find(windows,fullscreen)==windows.end())return;
    bool above=false,changed=false;
    for(const auto& w:windows) {
        if(w==fullscreen){above=true;continue;}
        if(!eligible(w,ws))continue;
        const bool permissionChanged=w->m_allowedOverFullscreen!=above;
        w->m_allowedOverFullscreen=above;
        w->updateFullscreenInputState();
        const float alpha=w->isBlockedByFullscreen()?0.F:1.F;
        auto& opacity=w->alpha(Desktop::View::WINDOW_ALPHA_FULLSCREEN);
        if(!permissionChanged && opacity->value()==alpha && opacity->goal()==alpha)continue;
        // A fading overlay would still cover a window that already owns input.
        // Change this visibility plane atomically with the stacking operation.
        opacity->setValueAndWarp(alpha);
        g_pHyprRenderer->damageWindow(w,true);
        changed=true;
    }
    if(changed)if(auto monitor=ws->m_monitor.lock()) {
        monitor->recheckSolitary();
        g_pHyprRenderer->damageMonitor(monitor);
    }
}
using MoveFn=void (*)(Desktop::CWindowState*,PHLWINDOW,bool);
MoveFn originalMove;
void move(Desktop::CWindowState* state,PHLWINDOW w,bool top) {
    // Preserve native transient/group ordering and all focus decisions.
    originalMove(state,w,top);
    reconcile(w?w->m_workspace:nullptr);
}
}
