// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <GLES3/gl32.h>

namespace Wobbly {
// Raw effect draws temporarily borrow the current program. A renderer pass
// owns its shader binding AND Hyprland's cached program/uniform selection.
enum class ShaderOwner { Effect, Renderer };

template<class Renderer> struct GLState {
    Renderer& renderer;
    const ShaderOwner shaderOwner;
    GLint program, vao, buffer, active, texture, srcRGB, dstRGB, srcA, dstA, eqRGB, eqA;
    GLint scissor[4], depthFunc;
    GLfloat depthClear;
    GLboolean blending, scissoring, depth, cull, stencil, depthWrite;
    GLboolean colorWrite[4];
    GLState(Renderer& renderer, ShaderOwner owner):renderer(renderer),shaderOwner(owner) {
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
    GLState(const GLState&) = delete;
    GLState& operator=(const GLState&) = delete;
    ~GLState() {
        // Never rewind only GL_CURRENT_PROGRAM after renderer->draw()/pass
        // rendering. useShader() would then skip a required bind and uniform
        // updates could corrupt another shader (and its persistent cache).
        if (shaderOwner == ShaderOwner::Effect) glUseProgram(program);
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
        auto gl = renderer.glBackend();
        gl->setCapStatus(GL_BLEND, blending);
        gl->setCapStatus(GL_DEPTH_TEST, depth);
        gl->setCapStatus(GL_CULL_FACE, cull);
        gl->setCapStatus(GL_STENCIL_TEST, stencil);
        if (renderer.m_renderData.pMonitor)
            gl->scissor(scissor[0], scissor[1], scissor[2], scissor[3], false);
        gl->setCapStatus(GL_SCISSOR_TEST, scissoring);
    }
};
} // namespace Wobbly
