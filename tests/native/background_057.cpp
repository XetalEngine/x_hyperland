#include "background_057.hpp"

int main(){
    const auto initial=glState;
    const auto restored=[&]{
        assert(glState==initial&&scissoring);
        assert(renderer.backend.read==glState[GL_READ_FRAMEBUFFER_BINDING]);
        assert(renderer.backend.draw==glState[GL_DRAW_FRAMEBUFFER_BINDING]);
    };
    for(size_t i=0;i<pixels.size();i+=4){pixels[i]=51;pixels[i+1]=74;pixels[i+2]=90;pixels[i+3]=255;}
    Framebuffer fb;Render::CRenderContext ctx;ctx.m_data.currentFB=&fb;
    auto monitor=std::make_shared<Monitor>();
    WindowButtons::Backgrounds backgrounds;
    const CBox panel{500,100,100,30};
    backgrounds.sample(ctx,1,monitor,panel);restored();assert(!backgrounds.ready(1));
    completion=GL_TIMEOUT_EXPIRED;
    backgrounds.sample(ctx,1,monitor,panel);restored();assert(!backgrounds.ready(1));
    completion=GL_ALREADY_SIGNALED;
    backgrounds.sample(ctx,1,monitor,panel);restored();assert(backgrounds.ready(1)&&conversions==1);
    const auto color=backgrounds.last(1);
    assert(std::abs(color.r-51/255.)<1e-6&&std::abs(color.g-74/255.)<1e-6&&std::abs(color.b-90/255.)<1e-6);
    // Exports must neither start a GPU read nor convert unrelated pixels.
    ctx.m_data.projectionType=Render::RPT_EXPORT;
    backgrounds.sample(ctx,2,monitor,panel);restored();assert(!backgrounds.ready(2)&&conversions==1);
    ctx.m_data.projectionType=Render::RPT_MONITOR;
    backgrounds.sample(ctx,2,monitor,panel);restored();
    backgrounds.sample(ctx,2,monitor,{550,100,100,30});restored();assert(!backgrounds.ready(2));
    backgrounds.sample(ctx,2,monitor,{550,100,100,30});restored();assert(backgrounds.ready(2)&&conversions==2);
    backgrounds.clear();restored();assert(deleted==1&&!backgrounds.ready(1));
    // A failed allocation still restores GL and its cached bindings.
    complete=false;backgrounds.sample(ctx,3,monitor,panel);restored();assert(!backgrounds.ready(3)&&deleted==2);
    backgrounds.clear();restored();
}
