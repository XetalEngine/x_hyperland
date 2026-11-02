// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine. Shared GL state discipline with Cube.
#pragma once
#include <hyprland/src/render/Renderer.hpp>
#include "mesh.hpp"
namespace Wobbly {
struct GLState {
    GLint program, vao, buffer, active, texture, srcRGB, dstRGB, srcA, dstA, eqRGB, eqA;
    GLint scissor[4], depthFunc;
    GLfloat depthClear;
    GLboolean blending, scissoring, depth, cull, stencil, depthWrite;
    GLboolean colorWrite[4];
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
        glGetBooleanv(GL_COLOR_WRITEMASK, colorWrite);
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
        glColorMask(colorWrite[0], colorWrite[1], colorWrite[2], colorWrite[3]);
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
    GLuint program=0,vao=0,vbo=0;
    GLint projection=-1;
    uint64_t uploaded=0;
    GLuint compile(GLenum type,const char* code){
        auto shader=glCreateShader(type);glShaderSource(shader,1,&code,nullptr);glCompileShader(shader);
        GLint ok;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
        if(!ok){char error[2048]{};glGetShaderInfoLog(shader,sizeof(error),nullptr,error);glDeleteShader(shader);throw std::runtime_error(error);}return shader;
    }
    void init(){
        GLState restore;
        auto v=compile(GL_VERTEX_SHADER,R"(#version 300 es
            layout(location=0) in vec2 position;layout(location=1) in vec2 source;
            uniform mat3 projection;out vec2 uv;
            // Input workbuffers already contain the output transform. Return a
            // logical, unrotated texture for Hyprland's final window draw.
            void main(){gl_Position=vec4(position*2.0-1.0,0.0,1.0);
                uv=(projection*vec3(source,1.0)).xy*.5+.5;}
        )");
        auto f=compile(GL_FRAGMENT_SHADER,R"(#version 300 es
            precision highp float;uniform sampler2D image;in vec2 uv;out vec4 color;
            void main(){if(any(lessThan(uv,vec2(0)))||any(greaterThan(uv,vec2(1)))){color=vec4(0);return;}color=texture(image,uv);}
        )");
        program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);glDeleteShader(v);glDeleteShader(f);
        GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);if(!ok)throw std::runtime_error("Cannot link Wobbly shader");
        glUseProgram(program);glUniform1i(glGetUniformLocation(program,"image"),0);projection=glGetUniformLocation(program,"projection");
        glGenVertexArrays(1,&vao);glGenBuffers(1,&vbo);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        glEnableVertexAttribArray(0);glEnableVertexAttribArray(1);
        glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),nullptr);
        glVertexAttribPointer(1,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)(2*sizeof(float)));
    }
    void draw(PHLMONITOR monitor,SP<Render::ITexture> texture,const std::vector<Vertex>& vertices,uint64_t revision){
        GLState restore;auto gl=g_pHyprRenderer->glBackend();
        glUseProgram(program);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        gl->setCapStatus(GL_BLEND,false);gl->setCapStatus(GL_DEPTH_TEST,false);gl->setCapStatus(GL_STENCIL_TEST,false);
        gl->setCapStatus(GL_CULL_FACE,false);gl->setCapStatus(GL_SCISSOR_TEST,false);glDepthMask(false);
        // Nested window passes leave damage restricted to the original rectangle.
        // Every pooled framebuffer must be cleared in full before drawing a mesh
        // that can extend outside that rectangle, including the blur alpha matte.
        glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
        const GLfloat transparent[4]={0,0,0,0};glClearBufferfv(GL_COLOR,0,transparent);
        auto matrix=g_pHyprRenderer->projectBoxToTarget(CBox{0,0,monitor->m_transformedSize.x,monitor->m_transformedSize.y},HYPRUTILS_TRANSFORM_NORMAL).transpose().getMatrix();
        glUniformMatrix3fv(projection,1,GL_FALSE,matrix.data());
        glActiveTexture(GL_TEXTURE0);texture->bind();
        texture->setTexParameter(GL_TEXTURE_MIN_FILTER,GL_LINEAR);texture->setTexParameter(GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        texture->setTexParameter(GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);texture->setTexParameter(GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
        // The color image and blur matte share the same mesh in this frame.
        if(uploaded!=revision){glBufferData(GL_ARRAY_BUFFER,vertices.size()*sizeof(Vertex),vertices.data(),GL_STREAM_DRAW);uploaded=revision;}
        glDrawArrays(GL_TRIANGLES,0,vertices.size());
    }
    void release(){if(vbo)glDeleteBuffers(1,&vbo);if(vao)glDeleteVertexArrays(1,&vao);if(program)glDeleteProgram(program);vbo=vao=program=0;}
};
} // namespace Wobbly
