// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/render/OpenGL.hpp>
#include <hyprland/src/helpers/cm/ColorManagement.hpp>
#include <chrono>
#include <map>
#include "dominant.hpp"

namespace WindowButtons {
class Backgrounds {
    using Clock=std::chrono::steady_clock;
    static constexpr int width=40,height=12,bytes=width*height*4;
    struct Sample {
        GLuint buffer=0;GLsync fence=nullptr;
        Clock::time_point requested{},seen{};
        CHyprColor color{32/255.,36/255.,43/255.,1};
        CBox region;
        uint64_t monitor=0;
        NColorManagement::PImageDescription description;
        bool ready=false;
        ~Sample(){if(fence)glDeleteSync(fence);if(buffer)glDeleteBuffers(1,&buffer);}
    };
    // Every binding/pixel-pack option touched below belongs to the renderer.
    // Leave its state (and its capability cache) exactly as it was.
    struct State {
        GLint read,draw,buffer,renderbuffer,alignment,rowLength,skipRows,skipPixels;
        GLboolean scissor;
        State(){
            glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
            glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&buffer);glGetIntegerv(GL_RENDERBUFFER_BINDING,&renderbuffer);
            glGetIntegerv(GL_PACK_ALIGNMENT,&alignment);glGetIntegerv(GL_PACK_ROW_LENGTH,&rowLength);
            glGetIntegerv(GL_PACK_SKIP_ROWS,&skipRows);glGetIntegerv(GL_PACK_SKIP_PIXELS,&skipPixels);
            scissor=glIsEnabled(GL_SCISSOR_TEST);
        }
        ~State(){
            glBindFramebuffer(GL_READ_FRAMEBUFFER,read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
            glBindBuffer(GL_PIXEL_PACK_BUFFER,buffer);glBindRenderbuffer(GL_RENDERBUFFER,renderbuffer);
            glPixelStorei(GL_PACK_ALIGNMENT,alignment);glPixelStorei(GL_PACK_ROW_LENGTH,rowLength);
            glPixelStorei(GL_PACK_SKIP_ROWS,skipRows);glPixelStorei(GL_PACK_SKIP_PIXELS,skipPixels);
            g_pHyprRenderer->glBackend()->setCapStatus(GL_SCISSOR_TEST,scissor);
        }
    };
    std::map<uint64_t,Sample> samples;
    GLuint framebuffer=0,renderbuffer=0;
    bool failed=false;
    bool allocate(){
        if(framebuffer)return true;
        if(failed)return false;
        glGenFramebuffers(1,&framebuffer);glGenRenderbuffers(1,&renderbuffer);
        glBindRenderbuffer(GL_RENDERBUFFER,renderbuffer);glRenderbufferStorage(GL_RENDERBUFFER,GL_RGBA8,width,height);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,framebuffer);
        glFramebufferRenderbuffer(GL_DRAW_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_RENDERBUFFER,renderbuffer);
        if(glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE)return true;
        glDeleteFramebuffers(1,&framebuffer);glDeleteRenderbuffers(1,&renderbuffer);
        framebuffer=renderbuffer=0;failed=true;return false;
    }
public:
    // Called with the GL context current, including unload/window-close paths.
    void clear(){
        samples.clear();
        if(framebuffer)glDeleteFramebuffers(1,&framebuffer);
        if(renderbuffer)glDeleteRenderbuffers(1,&renderbuffer);
        framebuffer=renderbuffer=0;failed=false;
    }
    void erase(uint64_t id){samples.erase(id);}
    bool ready(uint64_t id)const {auto it=samples.find(id);return it!=samples.end()&&it->second.ready;}
    CHyprColor last(uint64_t id)const {auto it=samples.find(id);return it==samples.end()?CHyprColor{32/255.,36/255.,43/255.,1}:it->second.color;}

    CHyprColor sample(uint64_t id,PHLMONITOR monitor,const CBox& logical){
        auto& data=g_pHyprRenderer->m_renderData;
        // Non-monitor exports/snapshots have another projection. Keep the last
        // valid match there instead of reading unrelated framebuffer pixels.
        if(!data.currentFB||data.projectionType!=Render::RPT_MONITOR)return last(id);
        CBox pixels=logical;data.renderModif.applyToBox(pixels);
        pixels.transform(Math::wlTransformToHyprutils(Math::invertTransform(monitor->m_transform)),
                         monitor->m_transformedSize.x,monitor->m_transformedSize.y);
        pixels=pixels.intersection(CBox{0,0,data.currentFB->m_size.x,data.currentFB->m_size.y}).round();
        if(pixels.empty())return last(id);
        if(!samples.contains(id)&&samples.size()>=128){
            auto oldest=std::min_element(samples.begin(),samples.end(),[](const auto& a,const auto& b){return a.second.seen<b.second.seen;});
            samples.erase(oldest);
        }
        auto& sample=samples[id];const auto now=Clock::now();sample.seen=now;
        const bool moved=sample.region!=pixels||sample.monitor!=uint64_t(monitor->m_id);
        // No glFinish, blocking readback or timed wait in the compositor thread.
        if(sample.fence){
            const auto state=glClientWaitSync(sample.fence,0,0);
            if(state==GL_ALREADY_SIGNALED||state==GL_CONDITION_SATISFIED){
                State saved;glBindBuffer(GL_PIXEL_PACK_BUFFER,sample.buffer);
                auto* rgba=static_cast<const uint8_t*>(glMapBufferRange(GL_PIXEL_PACK_BUFFER,0,bytes,GL_MAP_READ_BIT));
                if(rgba){
                    const auto color=dominant(rgba,width*height);glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
                    if(color&&!moved){
                        sample.color=NColorManagement::convertColor(CHyprColor{float((*color)[0]),float((*color)[1]),float((*color)[2]),1},
                            sample.description,NColorManagement::DEFAULT_SRGB_IMAGE_DESCRIPTION);
                        sample.color.a=1;sample.ready=true;
                    }
                }
                glDeleteSync(sample.fence);sample.fence=nullptr;
            }else if(state==GL_WAIT_FAILED){glDeleteSync(sample.fence);sample.fence=nullptr;}
        }
        if(!sample.fence&&(moved||now-sample.requested>=std::chrono::milliseconds(250))){
            State saved;
            if(allocate()){
                if(!sample.buffer){glGenBuffers(1,&sample.buffer);glBindBuffer(GL_PIXEL_PACK_BUFFER,sample.buffer);glBufferData(GL_PIXEL_PACK_BUFFER,bytes,nullptr,GL_STREAM_READ);}
                g_pHyprRenderer->glBackend()->setCapStatus(GL_SCISSOR_TEST,false);
                glBindFramebuffer(GL_READ_FRAMEBUFFER,saved.draw);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,framebuffer);
                // Hyprland's working framebuffer uses the same orientation as
                // its transformed scissor rectangles, not a second Y flip.
                glBlitFramebuffer(pixels.x,pixels.y,pixels.x+pixels.w,pixels.y+pixels.h,0,0,width,height,GL_COLOR_BUFFER_BIT,GL_NEAREST);
                glBindFramebuffer(GL_READ_FRAMEBUFFER,framebuffer);glBindBuffer(GL_PIXEL_PACK_BUFFER,sample.buffer);
                glPixelStorei(GL_PACK_ALIGNMENT,1);glPixelStorei(GL_PACK_ROW_LENGTH,0);
                glPixelStorei(GL_PACK_SKIP_ROWS,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);
                glReadPixels(0,0,width,height,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);
                sample.fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0);
                sample.requested=now;sample.region=pixels;sample.monitor=uint64_t(monitor->m_id);
                sample.description=data.currentFB->imageDescription();
            }
        }
        return sample.color;
    }
};
}
