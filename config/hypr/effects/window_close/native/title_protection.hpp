// SPDX-License-Identifier: GPL-2.0-or-later
// Native reachability check: no IPC polling, input grabs or window activation.
namespace TitlebarProtection {
uint64_t corrections=0;
Clock::time_point lastSweep{};
void tick() {
    if(!titleProtectionEnabled||stopping||!g_pCompositor->m_sessionActive||g_pSessionLockManager->isSessionLocked()||
       PROTO::inputCapture->isCaptured()||PROTO::data->dndActive()||g_layoutManager->dragController()->target())return;
    const auto now=Clock::now();
    if(now-lastSweep<std::chrono::milliseconds(250))return;
    lastSweep=now;
    for(const auto& w:Desktop::windowState()->windows()) {
        if(!w->m_isMapped||w->isHidden()||!w->m_isFloating||!WindowTypes::geometryManaged(w)||
           Fullscreen::controller()->getFullscreenModes(w).internal!=Fullscreen::FSMODE_NONE)continue;
        auto target=w->layoutTarget();auto monitor=w->m_monitor.lock();
        if(!target||!target->floating()||!target->space()||!monitor||!g_pHyprRenderer->shouldRenderWindow(w,monitor))continue;
        // A workspace animation/cube owns the visual transform until it ends.
        if(w->m_workspace&&(w->m_workspace->m_renderOffset->isBeingAnimated()||w->m_workspace->m_alpha->isBeingAnimated()))continue;
        const auto position=target->position(),work=target->space()->workArea(true);
        const auto ext=w->getWindowExtentsUnified(Desktop::View::RESERVED_EXTENTS|Desktop::View::INPUT_EXTENTS);
        const auto fitted=TitleProtection::reachable({position.x,position.y,position.w,position.h},
            {work.x,work.y,work.w,work.h},{ext.topLeft.x,ext.topLeft.y,ext.bottomRight.x,ext.bottomRight.y});
        if(!fitted)continue;
        // Set normal layout geometry so restore/memory agree. Do not warp the
        // animation, focus the app, move its workspace or resize its content.
        target->space()->algorithm()->floatingAlgo()->setTargetGeom(CBox{fitted->x,fitted->y,fitted->w,fitted->h},target);
        if(auto it=g_pKeybindManager->m_dispatchers.find("xetalwobbly:anchorplacement");it!=g_pKeybindManager->m_dispatchers.end())
            it->second(std::to_string(w->m_stableID));
        g_pHyprRenderer->damageWindow(w,true);++corrections;
    }
}
std::string status() {
    return std::format("\"titlebar_protection_supported\":true,\"titlebar_protection_enabled\":{},\"titlebar_protection_corrections\":{},",
                       titleProtectionEnabled,corrections);
}
}
