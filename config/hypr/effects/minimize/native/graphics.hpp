// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <hyprland/src/render/Renderer.hpp>
#include "motion.hpp"
#include "fire.hpp"
// #include "splat.hpp" // Parked: Fireball is the only enabled effect.
#include "dock_shader.hpp"
#include "../../burn/native/fire_texture.hpp"
namespace Minimize __attribute__((visibility("hidden"))) {
struct GLState {
    GLint program, vao, buffer, active, texture, srcRGB, dstRGB, srcA, dstA, eqRGB, eqA;
    GLint scissor[4], depthFunc;
    GLfloat depthClear;
    GLboolean blending, scissoring, depth, cull, stencil, depthWrite;
    GLState() {
        glGetIntegerv(GL_CURRENT_PROGRAM, &program);
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao);
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &buffer);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
        glGetIntegerv(GL_BLEND_SRC_RGB, &srcRGB);
        glGetIntegerv(GL_BLEND_DST_RGB, &dstRGB);
        glGetIntegerv(GL_BLEND_SRC_ALPHA, &srcA);
        glGetIntegerv(GL_BLEND_DST_ALPHA, &dstA);
        glGetIntegerv(GL_BLEND_EQUATION_RGB, &eqRGB);
        glGetIntegerv(GL_BLEND_EQUATION_ALPHA, &eqA);
        blending = glIsEnabled(GL_BLEND);
        scissoring = glIsEnabled(GL_SCISSOR_TEST);
        depth = glIsEnabled(GL_DEPTH_TEST);
        cull = glIsEnabled(GL_CULL_FACE);
        stencil = glIsEnabled(GL_STENCIL_TEST);
        glGetBooleanv(GL_DEPTH_WRITEMASK, &depthWrite);
        glGetIntegerv(GL_SCISSOR_BOX, scissor);
        glGetIntegerv(GL_DEPTH_FUNC, &depthFunc);
        glGetFloatv(GL_DEPTH_CLEAR_VALUE, &depthClear);
    }
    ~GLState() {
        glUseProgram(program);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, buffer);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, texture);
        glActiveTexture(active);
        glBlendFuncSeparate(srcRGB, dstRGB, srcA, dstA);
        glBlendEquationSeparate(eqRGB, eqA);
        glDepthMask(depthWrite);
        glDepthFunc(depthFunc);
        glClearDepthf(depthClear);
        auto gl = g_pHyprRenderer->glBackend();
        gl->setCapStatus(GL_BLEND, blending);
        gl->setCapStatus(GL_DEPTH_TEST, depth);
        gl->setCapStatus(GL_CULL_FACE, cull);
        gl->setCapStatus(GL_STENCIL_TEST, stencil);
        if (g_pHyprRenderer->m_renderData.pMonitor)
            gl->scissor(scissor[0], scissor[1], scissor[2], scissor[3], false);
        gl->setCapStatus(GL_SCISSOR_TEST, scissoring);
    }
};
struct Graphics {
    struct Vertex {float x,y,u,v,r,g,b,a;};
    GLuint fireProgram=0, dockProgram=0, vao=0, vbo=0, texture=0;
    GLuint compile(GLenum type, const char* source) {
        GLuint shader=glCreateShader(type);
        glShaderSource(shader,1,&source,nullptr);glCompileShader(shader);
        GLint ok=0;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
        if(!ok){char message[2048]{};glGetShaderInfoLog(shader,sizeof(message),nullptr,message);
            glDeleteShader(shader);throw std::runtime_error(std::string("Minimize shader: ")+message);}
        return shader;
    }
    GLuint link(const char* fragment) {
        const char* vs=R"(#version 300 es
        layout(location=0) in vec2 position;layout(location=1) in vec2 uv;layout(location=2) in vec4 color;
        uniform mat3 projection;out vec2 coord;out vec4 particleColor;
        void main(){vec3 p=projection*vec3(position,1);gl_Position=vec4(p.xy,0,1);coord=uv;particleColor=color;})";
        GLuint v=compile(GL_VERTEX_SHADER,vs),f=0;
        try{f=compile(GL_FRAGMENT_SHADER,fragment);}catch(...){glDeleteShader(v);throw;}
        GLuint program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);
        glDeleteShader(v);glDeleteShader(f);GLint ok=0;glGetProgramiv(program,GL_LINK_STATUS,&ok);
        if(!ok){glDeleteProgram(program);throw std::runtime_error("Cannot link Minimize effect shader");}
        return program;
    }
    void init() {
        g_pHyprRenderer->glBackend()->makeEGLCurrent();GLState restore;
        fireProgram=link(R"(#version 300 es
        precision highp float;
        uniform sampler2D sprite;uniform float alphaScale;
        in vec2 coord;in vec4 particleColor;out vec4 fragColor;
        void main(){fragColor=texture(sprite,coord)*particleColor;fragColor.a*=alphaScale;})");
        dockProgram=link(dockFragment);
        glGenTextures(1,&texture);glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,texture);
        glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,32,32,0,GL_RGBA,GL_UNSIGNED_BYTE,fireTex);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
        glGenVertexArrays(1,&vao);glGenBuffers(1,&vbo);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        glEnableVertexAttribArray(0);glEnableVertexAttribArray(1);glEnableVertexAttribArray(2);
        glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),nullptr);
        glVertexAttribPointer(1,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)(2*sizeof(float)));
        glVertexAttribPointer(2,4,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)(4*sizeof(float)));
    }
    void release() {
        if(!g_pHyprRenderer || !g_pHyprRenderer->glBackend())return;
        g_pHyprRenderer->glBackend()->makeEGLCurrent();GLState restore;
        if(vbo)glDeleteBuffers(1,&vbo);
        if(vao)glDeleteVertexArrays(1,&vao);
        if(fireProgram)glDeleteProgram(fireProgram);
        if(dockProgram)glDeleteProgram(dockProgram);
        if(texture)glDeleteTextures(1,&texture);
        fireProgram=dockProgram=vao=vbo=texture=0;
    }
    void prepare(PHLMONITOR m,GLuint program) {
        glUseProgram(program);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        auto gl=g_pHyprRenderer->glBackend();
        gl->setCapStatus(GL_BLEND,true);gl->setCapStatus(GL_DEPTH_TEST,false);
        gl->setCapStatus(GL_CULL_FACE,false);gl->setCapStatus(GL_STENCIL_TEST,false);glBlendEquation(GL_FUNC_ADD);
        CBox screen{0,0,m->m_transformedSize.x,m->m_transformedSize.y};
        g_pHyprRenderer->m_renderData.renderModif.applyToBox(screen);
        auto matrix=g_pHyprRenderer->projectBoxToTarget(screen,HYPRUTILS_TRANSFORM_NORMAL).transpose().getMatrix();
        glUniformMatrix3fv(glGetUniformLocation(program,"projection"),1,GL_FALSE,matrix.data());
    }
    void quad(std::vector<Vertex>& vertices, PHLMONITOR m,Rect b,std::array<float,4> c) {
        float x=b.x/m->m_size.x,y=b.y/m->m_size.y,r=(b.x+b.w)/m->m_size.x,t=(b.y+b.h)/m->m_size.y;
        auto put=[&](float px,float py,float u,float v){vertices.push_back({px,py,u,v,c[0],c[1],c[2],c[3]});};
        put(x,y,0,0);put(x,t,0,1);put(r,t,1,1);put(x,y,0,0);put(r,t,1,1);put(r,y,1,0);
    }
    void upload(const std::vector<Vertex>& vertices) {
        glBufferData(GL_ARRAY_BUFFER,vertices.size()*sizeof(Vertex),vertices.data(),GL_STREAM_DRAW);
    }
    void draw(int count) {
        g_pHyprRenderer->m_renderData.damage.forEachRect([&](const auto& rect){
            g_pHyprRenderer->glBackend()->scissor(&rect,g_pHyprRenderer->m_renderData.transformDamage);
            glDrawArrays(GL_TRIANGLES,0,count);
        });
    }
    std::array<float,3> color(const std::array<float,3>& rgb) {
        const auto c=g_pHyprRenderer->getConvertedColor(CHyprColor(rgb[0],rgb[1],rgb[2],1));
        return {float(c.r),float(c.g),float(c.b)};
    }
    void fire(PHLMONITOR m,Rect b,const Fire& emitter,const std::array<float,3>& rgb,float alpha,bool hover) {
        GLState restore;prepare(m,fireProgram);
        glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,texture);
        glUniform1i(glGetUniformLocation(fireProgram,"sprite"),0);
        auto base=color(rgb);std::vector<Vertex> vertices;vertices.reserve(emitter.particles.size()*6);
        for(const auto& p:emitter.particles)if(p.life>0){
            const float edge=std::clamp((p.y-4)/18.F,0.F,1.F)*std::clamp((96-p.y)/12.F,0.F,1.F);
            float w=p.width*(1+p.w_mod*p.life),h=p.height*(1+p.h_mod*p.life);
            // Keep the familiar Compiz wisps; newly emitted cores glow hotter.
            float hot=std::pow(p.life,5.F)*.25F;
            std::array<float,4> tint;
            for(int i=0;i<3;++i)tint[i]=(base[i]*(1-hot)+hot)*p.r*(hover?1.17F:1.F);
            tint[3]=p.a*p.life*edge*alpha;
            quad(vertices,m,{b.x+(p.x-w/2)*b.w/100,b.y+(p.y-h/2)*b.h/100,w*b.w/100,h*b.h/100},tint);
        }
        upload(vertices);
        // Compiz's darken pass gives the flame volume, then additive sprites
        // build bright cores without drawing a flat opaque flame silhouette.
        glUniform1f(glGetUniformLocation(fireProgram,"alphaScale"),.5F);
        glBlendFunc(GL_ZERO,GL_ONE_MINUS_SRC_ALPHA);draw(vertices.size());
        glUniform1f(glGetUniformLocation(fireProgram,"alphaScale"),1.F);
        glBlendFunc(GL_SRC_ALPHA,GL_ONE);draw(vertices.size());
    }
    void dock(PHLMONITOR m,Rect b,int style,const std::array<float,3>& rgb,const std::array<float,3>& background,
              const std::array<float,3>& light,double seconds,float alpha,bool vertical,int part=0,float hover=0,float reveal=1,int edge=0) {
        if(b.w<2 || b.h<2 || alpha<=0)return;
        GLState restore;prepare(m,dockProgram);
        auto uniform=[&](const char* name){return glGetUniformLocation(dockProgram,name);};
        const auto tint=color(rgb),base=color(background),ink=color(light);
        glUniform3fv(uniform("tint"),1,tint.data());glUniform3fv(uniform("base"),1,base.data());glUniform3fv(uniform("ink"),1,ink.data());
        glUniform2f(uniform("dimensions"),b.w,b.h);glUniform1f(uniform("time"),seconds);glUniform1f(uniform("opacity"),alpha);
        glUniform1i(uniform("style"),style);glUniform1i(uniform("part"),part);glUniform1i(uniform("vertical"),vertical);
        glUniform1f(uniform("reveal"),reveal);glUniform1i(uniform("edge"),edge);
        glUniform1f(uniform("emphasis"),hover);glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
        std::vector<Vertex> vertices;quad(vertices,m,b,{1,1,1,1});upload(vertices);draw(vertices.size());
    }
#if 0 // Retain Splat's implementation for a future revision, without compiling its shader.
    void splat(PHLMONITOR m,Rect b,double seconds,uint32_t seed,int shape,int surface,float bubbles,
               const std::array<float,3>& rgb,float alpha,bool hover) {
        GLState restore;prepare(m,splatProgram);
        auto uniform=[&](const char* name){return glGetUniformLocation(splatProgram,name);};
        const auto c=color(rgb);glUniform3fv(uniform("tint"),1,c.data());
        glUniform1f(uniform("time"),seconds);glUniform1f(uniform("opacity"),alpha);
        glUniform1f(uniform("emphasis"),hover?1:0);glUniform1f(uniform("seed"),seed%8192);
        glUniform1f(uniform("outlineSeed"),shape<0?seed%8192:shape*17+11);
        glUniform1i(uniform("shape"),shape<0?seed%8:shape);glUniform1f(uniform("bubbles"),bubbles);glUniform1i(uniform("surface"),surface);
        glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
        std::vector<Vertex> vertices;quad(vertices,m,b,{1,1,1,1});upload(vertices);draw(vertices.size());
    }
#endif
};
}
