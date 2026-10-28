// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 XetalEngine. See COPYING and README.md.
#pragma once
#include "math.hpp"
#include <hyprland/src/render/Renderer.hpp>

namespace Cube {
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
using Color = std::array<float, 4>;
struct Vertex {
    float x, y, w, u, v;
};
struct Polygon {
    std::vector<Vertex> vertices;
    SP<Render::ITexture> texture;
    Color color = {1, 1, 1, 1};
    double depth = 0;
};

struct Graphics {
    GLuint program = 0, vao = 0, vbo = 0;
    GLint projection = -1, color = -1, textured = -1, skyMode = -1, skyAngles = -1, skyTop = -1, skyBottom = -1, aspect = -1;
    GLuint compile(GLenum type, const char *source) {
        auto s = glCreateShader(type);
        glShaderSource(s, 1, &source, nullptr);
        glCompileShader(s);
        GLint ok;
        glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
        if (!ok) {
            char msg[2048]{};
            glGetShaderInfoLog(s, sizeof(msg), nullptr, msg);
            glDeleteShader(s);
            throw std::runtime_error(msg);
        }
        return s;
    }
    void init() {
        GLState restore;
        const char *vs = R"(#version 300 es
            layout(location=0) in vec3 position; layout(location=1) in vec2 uv;
            uniform mat3 projection;out vec2 texcoord;
            void main(){vec3 p=projection*vec3(position.xy,1.0);gl_Position=vec4(p.xy*position.z,1.0001*position.z-.100005,position.z);texcoord=uv;}
        )";
        const char *fs = R"(#version 300 es
            precision highp float;
            uniform sampler2D sprite;uniform vec4 tint;uniform bool textured;
            uniform int skyMode;uniform vec2 skyAngles;uniform vec4 skyTop,skyBottom;uniform float aspect;
            in vec2 texcoord;out vec4 fragColor;
            void main(){
                if(skyMode>0){
                    vec2 uv=texcoord;
                    if(skyMode==3){
                        vec3 d=normalize(vec3((uv.x-.5)*aspect,(.5-uv.y),-.8));
                        float cp=cos(skyAngles.y),sp=sin(skyAngles.y);d.yz=mat2(cp,sp,-sp,cp)*d.yz;
                        float cy=cos(skyAngles.x),sy=sin(skyAngles.x);d.xz=mat2(cy,sy,-sy,cy)*d.xz;
                        uv=vec2(fract(atan(d.x,-d.z)/6.2831853+.5),acos(clamp(d.y,-1.0,1.0))/3.14159265);
                    }
                    vec4 base=mix(skyTop,skyBottom,texcoord.y);
                    fragColor=textured?texture(sprite,uv):base;
                    fragColor.a=1.0;return;
                }
                vec4 c=textured?texture(sprite,texcoord):vec4(1.0);
                if(c.a<.005)discard;
                // Hyprland framebuffer textures and UI images are premultiplied.
                fragColor=vec4(c.rgb*tint.rgb*tint.a,c.a*tint.a);
            }
        )";
        auto v = compile(GL_VERTEX_SHADER, vs), f = compile(GL_FRAGMENT_SHADER, fs);
        program = glCreateProgram();
        glAttachShader(program, v);
        glAttachShader(program, f);
        glLinkProgram(program);
        glDeleteShader(v);
        glDeleteShader(f);
        GLint ok;
        glGetProgramiv(program, GL_LINK_STATUS, &ok);
        if (!ok)
            throw std::runtime_error("Cannot link Desktop Cube shaders");
        glUseProgram(program);
        glUniform1i(glGetUniformLocation(program, "sprite"), 0);
        projection = glGetUniformLocation(program, "projection");
        color = glGetUniformLocation(program, "tint");
        textured = glGetUniformLocation(program, "textured");
        skyMode = glGetUniformLocation(program, "skyMode");
        skyAngles = glGetUniformLocation(program, "skyAngles");
        skyTop = glGetUniformLocation(program, "skyTop");
        skyBottom = glGetUniformLocation(program, "skyBottom");
        aspect = glGetUniformLocation(program, "aspect");
        glGenVertexArrays(1, &vao);
        glGenBuffers(1, &vbo);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glEnableVertexAttribArray(0);
        glEnableVertexAttribArray(1);
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), nullptr);
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void *)(3 * sizeof(float)));
    }
    void begin(PHLMONITOR monitor) {
        auto gl = g_pHyprRenderer->glBackend();
        glUseProgram(program);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        gl->setCapStatus(GL_BLEND, true);
        gl->setCapStatus(GL_CULL_FACE, false);
        gl->setCapStatus(GL_DEPTH_TEST, false);
        gl->setCapStatus(GL_STENCIL_TEST, false);
        glDepthMask(false);
        glBlendEquation(GL_FUNC_ADD);
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
        auto matrix =
            g_pHyprRenderer
                ->projectBoxToTarget(CBox{0, 0, monitor->m_transformedSize.x, monitor->m_transformedSize.y}, HYPRUTILS_TRANSFORM_NORMAL)
                .transpose()
                .getMatrix();
        glUniformMatrix3fv(projection, 1, GL_FALSE, matrix.data());
        glUniform1i(skyMode, 0);
    }
    void draw(const Polygon &p) {
        if (p.vertices.empty())
            return;
        glUniform1i(textured, !!p.texture);
        if (p.texture) {
            p.texture->bind();
            // Raw imported artwork has no mip chain. Set sampling explicitly,
            // as the compositor's normal texture pass would do.
            p.texture->setTexParameter(GL_TEXTURE_MIN_FILTER, GL_LINEAR);
            p.texture->setTexParameter(GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            p.texture->setTexParameter(GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
            p.texture->setTexParameter(GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        } else
            glBindTexture(GL_TEXTURE_2D, 0);
        glUniform4fv(color, 1, p.color.data());
        glBufferData(GL_ARRAY_BUFFER, p.vertices.size() * sizeof(Vertex), p.vertices.data(), GL_STREAM_DRAW);
        g_pHyprRenderer->m_renderData.damage.forEachRect([&](const auto &r) {
            g_pHyprRenderer->glBackend()->scissor(&r, g_pHyprRenderer->m_renderData.transformDamage);
            glDrawArrays(GL_TRIANGLES, 0, p.vertices.size());
        });
    }
    void release() {
        if (vbo)
            glDeleteBuffers(1, &vbo);
        if (vao)
            glDeleteVertexArrays(1, &vao);
        if (program)
            glDeleteProgram(program);
        vbo = vao = program = 0;
    }
};
inline Polygon flat(double x, double y, double w, double h, SP<Render::ITexture> texture, Color color = {1, 1, 1, 1}, bool flip = false) {
    float top = flip ? 1 : 0, bottom = flip ? 0 : 1;
    return {{{float(x), float(y), 1, 0, top},
             {float(x + w), float(y), 1, 1, top},
             {float(x + w), float(y + h), 1, 1, bottom},
             {float(x), float(y), 1, 0, top},
             {float(x + w), float(y + h), 1, 1, bottom},
             {float(x), float(y + h), 1, 0, bottom}},
            texture,
            color};
}
} // namespace Cube
