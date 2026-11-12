// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine.
#pragma once
#include <hyprland/src/render/Renderer.hpp>
#include "mesh.hpp"
#include "gl_state.hpp"
namespace Wobbly {
struct Graphics {
    GLuint program=0,vao=0,vbo=0;
    GLint projection=-1,localSource=-1;
    uint64_t uploaded=0;
    GLuint compile(GLenum type,const char* code){
        auto shader=glCreateShader(type);glShaderSource(shader,1,&code,nullptr);glCompileShader(shader);
        GLint ok;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
        if(!ok){char error[2048]{};glGetShaderInfoLog(shader,sizeof(error),nullptr,error);glDeleteShader(shader);throw std::runtime_error(error);}return shader;
    }
    void init(){
        GLState restore{*g_pHyprRenderer,ShaderOwner::Effect};
        auto v=compile(GL_VERTEX_SHADER,R"(#version 300 es
            layout(location=0) in vec2 position;layout(location=1) in vec2 source;
            uniform mat3 projection;uniform bool localSource;out vec2 uv;
            // Input workbuffers already contain the output transform. Return a
            // logical, unrotated texture for Hyprland's final window draw.
            void main(){gl_Position=vec4(position*2.0-1.0,0.0,1.0);
                uv=localSource?source:(projection*vec3(source,1.0)).xy*.5+.5;}
        )");
        auto f=compile(GL_FRAGMENT_SHADER,R"(#version 300 es
            precision highp float;uniform sampler2D image;in vec2 uv;out vec4 color;
            void main(){if(any(lessThan(uv,vec2(0)))||any(greaterThan(uv,vec2(1)))){color=vec4(0);return;}color=texture(image,uv);}
        )");
        program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);glDeleteShader(v);glDeleteShader(f);
        GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);if(!ok)throw std::runtime_error("Cannot link Wobbly shader");
        glUseProgram(program);glUniform1i(glGetUniformLocation(program,"image"),0);projection=glGetUniformLocation(program,"projection");
        localSource=glGetUniformLocation(program,"localSource");
        glGenVertexArrays(1,&vao);glGenBuffers(1,&vbo);glBindVertexArray(vao);glBindBuffer(GL_ARRAY_BUFFER,vbo);
        glEnableVertexAttribArray(0);glEnableVertexAttribArray(1);
        glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),nullptr);
        glVertexAttribPointer(1,2,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)(2*sizeof(float)));
    }
    void draw(PHLMONITOR monitor,SP<Render::ITexture> texture,const std::vector<Vertex>& vertices,uint64_t revision,bool windowSource=false){
        GLState restore{*g_pHyprRenderer,ShaderOwner::Effect};auto gl=g_pHyprRenderer->glBackend();
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
        glUniform1i(localSource,windowSource);
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
