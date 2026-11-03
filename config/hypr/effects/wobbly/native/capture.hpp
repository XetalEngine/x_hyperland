// SPDX-License-Identifier: GPL-2.0-or-later
// Preserve the whole decorated source before the lattice crosses an output edge.
#pragma once
#include <hyprland/src/render/ElementRenderer.hpp>
#include <hyprutils/utils/ScopeGuard.hpp>

namespace Wobbly {
using ElementDraw=void(*)(Render::IElementRenderer*,WP<IPassElement>,const CRegion&);
inline ElementDraw originalElementDraw=nullptr;
struct CaptureContext {Vector2D offset;double scale;};
inline const CaptureContext* captureContext=nullptr;

// Translate copies, not the live window or the monitor. Surfaces keep their
// original buffer/viewport mapping, decorations and presentation feedback.
inline void drawCaptured(Render::IElementRenderer* renderer,WP<IPassElement> element,const CRegion& damage){
    const auto prior=captureContext;const auto context=*prior;captureContext=nullptr;
    const Hyprutils::Utils::CScopeGuard restore([&]{captureContext=prior;});
    auto& data=g_pHyprRenderer->m_renderData;
    const auto savedDamage=data.damage.copy();const auto savedModif=data.renderModif;
    const Hyprutils::Utils::CScopeGuard state([&]{data.damage=savedDamage;data.renderModif=savedModif;});
    CRegion local=damage.copy().translate(-context.offset);data.damage=local;
    SP<IPassElement> moved;
    switch(element->type()){
        case EK_SURFACE:{
            auto value=static_cast<CSurfacePassElement*>(element.get())->m_data;
            value.pos-=context.offset/context.scale;
            if(!value.clipBox.empty())value.clipBox.translate(-context.offset);
            moved=makeShared<CSurfacePassElement>(value);break;
        }
        case EK_BORDER:{
            auto value=static_cast<CBorderPassElement*>(element.get())->m_data;
            value.box.translate(-context.offset);moved=makeShared<CBorderPassElement>(value);break;
        }
        case EK_RECT:{
            auto value=static_cast<CRectPassElement*>(element.get())->m_data;
            value.box.translate(-context.offset);
            if(!value.clipBox.empty())value.clipBox.translate(-context.offset);
            moved=makeShared<CRectPassElement>(value);break;
        }
        default:
            // Shadow and inner-glow decorations calculate their own boxes.
            data.renderModif.modifs.emplace_back(Render::SRenderModifData::RMOD_TYPE_TRANSLATE,-context.offset);
            break;
    }
    originalElementDraw(renderer,moved?WP<IPassElement>(moved):element,local);
}

template<class Paint>void captureWindow(SP<Render::IFramebuffer> fb,PHLMONITOR m,const CBox& source,Paint paint){
    auto renderer=g_pHyprRenderer.get();auto saved=renderer->m_renderData;
    const auto outputTransform=m->m_transform;
    GLint viewport[4];glGetIntegerv(GL_VIEWPORT,viewport);
    const auto prior=captureContext;
    GLState glState;
    auto guard=renderer->bindTempFB(fb);
    renderer->pushMonitorTransformEnabled(false);
    const Hyprutils::Utils::CScopeGuard restore([&]{
        m->m_transform=outputTransform;
        captureContext=prior;renderer->popMonitorTransformEnabled();
        renderer->m_renderData=saved;renderer->setViewport(viewport[0],viewport[1],viewport[2],viewport[3]);
    });
    auto& data=renderer->m_renderData;
    // The pinned GL backend derives rounding/border uniforms directly from
    // this field, even when monitor transforms are disabled for projection.
    // This synchronous offscreen pass uses identity coordinates throughout;
    // restore the output transform before any final display draw or callback.
    m->m_transform=WL_OUTPUT_TRANSFORM_NORMAL;
    data.fbSize=fb->m_size;renderer->setProjectionType(Render::RPT_EXPORT);
    renderer->setViewport(0,0,fb->m_size.x,fb->m_size.y);
    data.transformDamage=false;data.noSimplify=true;data.clipBox={};data.renderModif={};data.surface.reset();
    data.damage=CRegion{0,0,int(fb->m_size.x),int(fb->m_size.y)};
    renderer->glBackend()->setCapStatus(GL_SCISSOR_TEST,false);
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    const GLfloat clear[4]={0,0,0,0};glClearBufferfv(GL_COLOR,0,clear);
    const CaptureContext context{source.pos(),m->m_scale};captureContext=&context;
    paint(data);
}
} // namespace Wobbly
