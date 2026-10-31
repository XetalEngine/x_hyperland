// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <hyprland/src/render/Renderer.hpp>
#include "motion.hpp"
namespace Minimize {
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
    GLuint program=0, vao=0, vbo=0;
    GLint projection=-1, time=-1, opacity=-1, emphasis=-1;
    GLuint compile(GLenum type, const char* source) {
        GLuint shader=glCreateShader(type);
        glShaderSource(shader,1,&source,nullptr); glCompileShader(shader);
        GLint ok=0; glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
        if (!ok) {
            char message[2048]{}; glGetShaderInfoLog(shader,sizeof(message),nullptr,message);
            glDeleteShader(shader); throw std::runtime_error(std::string("Minimize shader: ")+message);
        }
        return shader;
    }
    void init() {
        g_pHyprRenderer->glBackend()->makeEGLCurrent(); GLState restore;
        const char* vs=R"(#version 300 es
            layout(location=0) in vec2 position; layout(location=1) in vec2 uv;
            uniform mat3 projection; out vec2 coord;
            void main(){vec3 p=projection*vec3(position,1.0);gl_Position=vec4(p.xy,0,1);coord=uv;}
        )";
        const char* fs=R"(#version 300 es
            precision highp float;
            uniform float time, opacity, emphasis; in vec2 coord; out vec4 fragColor;
            float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
            float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
                return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
            void main(){
                vec2 p=coord-vec2(.5,.66);
                float n=noise(vec2(coord.x*9.0,coord.y*7.0+time*3.7));
                float n2=noise(vec2(coord.x*23.0,coord.y*16.0+time*6.1));
                float rise=clamp((.66-coord.y)/.62,0.0,1.0);
                float sway=sin(rise*8.0-time*3.0)*.065*rise;
                float width=.34*pow(1.0-rise,.8)+.015;
                float tongue=1.0-abs(p.x+sway)/width-rise*.65;
                float core=1.0-length(p/vec2(.34,.28));
                float flame=max(core,coord.y<.66?tongue:-1.0)+(n-.5)*.33+(n2-.5)*.13;
                float a=smoothstep(-.12,.15,flame);
                vec3 color=mix(vec3(1.0,.10,.008),vec3(1.0,.55,.025),smoothstep(0.0,.36,flame));
                color=mix(color,vec3(1.0,.96,.63),smoothstep(.32,.75,flame));
                float glow=exp(-dot(p,p)*16.0)*.20;
                a=max(a,glow)*(1.0-smoothstep(.43,.50,abs(p.x)));
                a*=smoothstep(0.0,.10,coord.y)*(1.0-smoothstep(.90,1.0,coord.y))*opacity;
                color=mix(color,vec3(1.0,.83,.46),emphasis*.23);
                // Premultiplied output, like the compositor's own textures.
                fragColor=vec4(color*a,a);
            }
        )";
        auto v=compile(GL_VERTEX_SHADER,vs); GLuint f=0;
        try { f=compile(GL_FRAGMENT_SHADER,fs); } catch (...) {glDeleteShader(v);throw;}
        program=glCreateProgram(); glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);
        glDeleteShader(v);glDeleteShader(f); GLint ok=0;glGetProgramiv(program,GL_LINK_STATUS,&ok);
        if (!ok) throw std::runtime_error("Cannot link Minimize fireball shader");
        projection=glGetUniformLocation(program,"projection"); time=glGetUniformLocation(program,"time");
        opacity=glGetUniformLocation(program,"opacity"); emphasis=glGetUniformLocation(program,"emphasis");
        glGenVertexArrays(1,&vao);glGenBuffers(1,&vbo);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        glEnableVertexAttribArray(0);glEnableVertexAttribArray(1);
        glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,4*sizeof(float),nullptr);
        glVertexAttribPointer(1,2,GL_FLOAT,GL_FALSE,4*sizeof(float),(void*)(2*sizeof(float)));
    }
    void release() {
        if (!g_pHyprRenderer || !g_pHyprRenderer->glBackend()) return;
        g_pHyprRenderer->glBackend()->makeEGLCurrent();GLState restore;
        if(vbo)glDeleteBuffers(1,&vbo);
        if(vao)glDeleteVertexArrays(1,&vao);
        if(program)glDeleteProgram(program);
        program=vao=vbo=0;
    }
    void fire(PHLMONITOR monitor, Rect box, double seconds, float alpha, bool hover) {
        GLState restore;auto gl=g_pHyprRenderer->glBackend();
        glUseProgram(program);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        gl->setCapStatus(GL_BLEND,true);gl->setCapStatus(GL_DEPTH_TEST,false);
        gl->setCapStatus(GL_CULL_FACE,false);gl->setCapStatus(GL_STENCIL_TEST,false);
        glBlendEquation(GL_FUNC_ADD);glBlendFunc(GL_ONE,GL_ONE_MINUS_SRC_ALPHA);
        CBox screen{0,0,monitor->m_transformedSize.x,monitor->m_transformedSize.y};
        g_pHyprRenderer->m_renderData.renderModif.applyToBox(screen);
        auto matrix=g_pHyprRenderer->projectBoxToTarget(screen,HYPRUTILS_TRANSFORM_NORMAL).transpose().getMatrix();
        glUniformMatrix3fv(projection,1,GL_FALSE,matrix.data());
        glUniform1f(time,seconds);glUniform1f(opacity,alpha);glUniform1f(emphasis,hover?1:0);
        float x=box.x/monitor->m_size.x,y=box.y/monitor->m_size.y;
        float r=(box.x+box.w)/monitor->m_size.x,b=(box.y+box.h)/monitor->m_size.y;
        const float vertices[]={x,y,0,0,x,b,0,1,r,b,1,1,x,y,0,0,r,b,1,1,r,y,1,0};
        glBufferData(GL_ARRAY_BUFFER,sizeof(vertices),vertices,GL_STREAM_DRAW);
        g_pHyprRenderer->m_renderData.damage.forEachRect([&](const auto& rect){
            gl->scissor(&rect,g_pHyprRenderer->m_renderData.transformDamage);glDrawArrays(GL_TRIANGLES,0,6);
        });
    }
};
}
