#pragma once
// Exercise the real sampler with deterministic GPU completion and the real
// Hyprutils unique/weak ownership used by Hyprland 0.57's color registry.
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <GLES3/gl3.h>
#include <hyprutils/memory/UniquePtr.hpp>
#include <hyprutils/memory/WeakPtr.hpp>

inline std::map<GLenum,GLint> glState{{GL_READ_FRAMEBUFFER_BINDING,7},{GL_DRAW_FRAMEBUFFER_BINDING,8},
    {GL_PIXEL_PACK_BUFFER_BINDING,9},{GL_RENDERBUFFER_BINDING,10},{GL_PACK_ALIGNMENT,8},
    {GL_PACK_ROW_LENGTH,11},{GL_PACK_SKIP_ROWS,12},{GL_PACK_SKIP_PIXELS,13}};
inline bool scissoring=true,complete=true;
inline int conversions=0,deleted=0;
inline std::array<uint8_t,40*12*4> pixels{};
inline GLuint serial=100;
inline GLenum completion=GL_ALREADY_SIGNALED;
inline void glGetIntegerv(GLenum p,GLint* v){*v=glState.at(p);}
inline GLboolean glIsEnabled(GLenum p){assert(p==GL_SCISSOR_TEST);return scissoring;}
inline void glBindFramebuffer(GLenum target,GLuint fb){
    if(target==GL_FRAMEBUFFER||target==GL_READ_FRAMEBUFFER)glState[GL_READ_FRAMEBUFFER_BINDING]=fb;
    if(target==GL_FRAMEBUFFER||target==GL_DRAW_FRAMEBUFFER)glState[GL_DRAW_FRAMEBUFFER_BINDING]=fb;
}
inline void glBindBuffer(GLenum target,GLuint buffer){assert(target==GL_PIXEL_PACK_BUFFER);glState[GL_PIXEL_PACK_BUFFER_BINDING]=buffer;}
inline void glBindRenderbuffer(GLenum,GLuint buffer){glState[GL_RENDERBUFFER_BINDING]=buffer;}
inline void glPixelStorei(GLenum p,GLint v){glState[p]=v;}
inline void glGenFramebuffers(GLsizei n,GLuint* p){while(n--)*p++=++serial;}
inline void glGenRenderbuffers(GLsizei n,GLuint* p){glGenFramebuffers(n,p);}
inline void glGenBuffers(GLsizei n,GLuint* p){glGenFramebuffers(n,p);}
inline void glRenderbufferStorage(GLenum,GLenum,GLsizei,GLsizei){}
inline void glFramebufferRenderbuffer(GLenum,GLenum,GLenum,GLuint){}
inline GLenum glCheckFramebufferStatus(GLenum){return complete?GL_FRAMEBUFFER_COMPLETE:GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT;}
inline void glDeleteFramebuffers(GLsizei n,const GLuint* p){
    while(n--){for(auto key:{GL_READ_FRAMEBUFFER_BINDING,GL_DRAW_FRAMEBUFFER_BINDING})if(glState[key]==GLint(*p))glState[key]=0;++p;}
}
inline void glDeleteRenderbuffers(GLsizei,const GLuint*){}
inline void glDeleteBuffers(GLsizei,const GLuint*){}
inline void glDeleteSync(GLsync){}
inline GLenum glClientWaitSync(GLsync,GLbitfield,GLuint64){return completion;}
inline void* glMapBufferRange(GLenum,GLintptr,GLsizeiptr,GLbitfield){return pixels.data();}
inline GLboolean glUnmapBuffer(GLenum){return true;}
inline void glBufferData(GLenum,GLsizeiptr,const void*,GLenum){}
inline void glBlitFramebuffer(GLint,GLint,GLint,GLint,GLint,GLint,GLint,GLint,GLbitfield,GLenum){}
inline void glReadPixels(GLint,GLint,GLsizei,GLsizei,GLenum,GLenum,void*){}
inline GLsync glFenceSync(GLenum,GLbitfield){return reinterpret_cast<GLsync>(uintptr_t(1));}

struct CHyprColor {double r,g,b,a;};
struct Vector2D {double x,y;};
struct CBox {
    double x=0,y=0,w=0,h=0;
    auto operator<=>(const CBox&)const=default;
    void transform(int,double,double){}
    CBox intersection(CBox other)const{
        auto left=std::max(x,other.x),top=std::max(y,other.y);
        return {left,top,std::max(0.,std::min(x+w,other.x+other.w)-left),std::max(0.,std::min(y+h,other.y+other.h)-top)};
    }
    CBox round()const{return *this;}
    bool empty()const{return w<=0||h<=0;}
};
namespace Math {inline int wlTransformToHyprutils(int n){return n;}inline int invertTransform(int n){return n;}}
namespace NColorManagement {
struct Description {};
using PImageDescription=Hyprutils::Memory::CWeakPointer<const Description>;
inline Hyprutils::Memory::CUniquePointer<const Description> owned{new Description};
inline const PImageDescription DEFAULT_SRGB_IMAGE_DESCRIPTION=owned;
inline CHyprColor convertColor(CHyprColor color,PImageDescription src,PImageDescription dst,int){
    assert(src&&dst);++conversions;return color;
}
}
struct Framebuffer {
    Vector2D m_size{1920,1080};
    NColorManagement::PImageDescription imageDescription(){return NColorManagement::DEFAULT_SRGB_IMAGE_DESCRIPTION;}
};
namespace Render {
enum Projection {RPT_MONITOR,RPT_EXPORT};
struct CRenderContext {
    struct Data {
        Framebuffer* currentFB=nullptr;
        Projection projectionType=RPT_MONITOR;
        struct Modif {void applyToBox(CBox&)const{}} renderModif;
    } m_data;
};
}
struct Monitor {int m_transform=0,m_id=1;Vector2D m_transformedSize{1920,1080};};
using PHLMONITOR=std::shared_ptr<Monitor>;
struct Backend {
    GLint read=7,draw=8;
    void setCapStatus(GLenum p,bool state){assert(p==GL_SCISSOR_TEST);scissoring=state;}
    void bindFramebuffer(GLenum target,GLuint fb){
        if(target==GL_READ_FRAMEBUFFER&&read==GLint(fb))return;
        if(target==GL_DRAW_FRAMEBUFFER&&draw==GLint(fb))return;
        glBindFramebuffer(target,fb);
        if(target==GL_FRAMEBUFFER||target==GL_READ_FRAMEBUFFER)read=fb;
        if(target==GL_FRAMEBUFFER||target==GL_DRAW_FRAMEBUFFER)draw=fb;
    }
    void onFramebufferDeleted(GLuint fb){++deleted;if(read==GLint(fb))read=0;if(draw==GLint(fb))draw=0;}
};
struct Renderer {
    Backend backend;
    Backend* glBackend(){return &backend;}
    int getCMSettings(Render::CRenderContext&,NColorManagement::PImageDescription src,NColorManagement::PImageDescription dst){assert(src&&dst);return 0;}
};
inline Renderer renderer;
inline Renderer* g_pHyprRenderer=&renderer;
