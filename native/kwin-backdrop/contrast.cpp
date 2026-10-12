// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "contrast.h"
#include "core/rendertarget.h"
#include "opengl/glframebuffer.h"
#include "opengl/gltexture.h"
#include <array>

using namespace KWin;

namespace {
constexpr int Side = 8, Bytes = Side * Side * 4;
class PackState {
public:
    PackState()
    {
        glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &buffer);
        glGetIntegerv(GL_PACK_ALIGNMENT, &alignment);
        scissor = glIsEnabled(GL_SCISSOR_TEST);
        glDisable(GL_SCISSOR_TEST);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &unit);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
    }
    ~PackState()
    {
        glBindBuffer(GL_PIXEL_PACK_BUFFER, buffer);
        glPixelStorei(GL_PACK_ALIGNMENT, alignment);
        glBindTexture(GL_TEXTURE_2D, texture);
        glActiveTexture(unit);
        if (scissor) glEnable(GL_SCISSOR_TEST);
    }
private:
    GLint buffer, alignment, unit, texture;
    GLboolean scissor;
};
}

BackdropContrast::BackdropContrast() = default;

BackdropContrast::~BackdropContrast()
{
    if (m_fence) glDeleteSync(m_fence);
    if (m_buffer) glDeleteBuffers(1, &m_buffer);
}

bool BackdropContrast::allocate()
{
    if (m_buffer) return true;
    if (epoxy_gl_version() < 30) return false;
    m_texture = GLTexture::allocate(GL_RGBA8, QSize(Side, Side));
    if (!m_texture) return false;
    m_framebuffer = std::make_unique<GLFramebuffer>(m_texture.get());
    if (!m_framebuffer->valid()) return false;
    glGenBuffers(1, &m_buffer);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, m_buffer);
    glBufferData(GL_PIXEL_PACK_BUFFER, Bytes, nullptr, GL_STREAM_READ);
    return m_buffer != 0;
}

QColor BackdropContrast::collect()
{
    if (!m_fence) return {};
    const GLenum result = glClientWaitSync(m_fence, 0, 0);
    if (result == GL_TIMEOUT_EXPIRED && ++m_attempts < 8) return {};
    glDeleteSync(m_fence);
    m_fence = nullptr;
    if (result != GL_ALREADY_SIGNALED && result != GL_CONDITION_SATISFIED) return {};
    glBindBuffer(GL_PIXEL_PACK_BUFFER, m_buffer);
    const auto pixels = static_cast<const unsigned char *>(glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, Bytes, GL_MAP_READ_BIT));
    if (!pixels) return {};
    std::array<int,3> sum{};
    for (int i = 0; i < Bytes; i += 4)
        for (int channel = 0; channel < 3; ++channel) sum[channel] += pixels[i + channel];
    glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
    return QColor(sum[0] / (Side * Side), sum[1] / (Side * Side), sum[2] / (Side * Side));
}

QColor BackdropContrast::update(const RenderTarget &target, const RenderViewport &viewport, const Rect &bounds, const Region &damage)
{
    const PackState state;
    const QColor color = collect();
    if (m_bounds != bounds) { m_bounds = bounds; m_dirty = true; }
    if (m_fence || !m_dirty || (m_clock.isValid() && m_clock.elapsed() < 200)) return color;
    const Rect capture = bounds.intersected(viewport.renderRect().toAlignedRect());
    if (capture.isEmpty() || !logicalDamage(viewport,damage).contains(capture) || !allocate()) return color;
    if (!m_framebuffer->blitFromRenderTarget(target, viewport, capture, Rect(0, 0, Side, Side))) return color;
    GLFramebuffer::pushFramebuffer(m_framebuffer.get());
    glBindBuffer(GL_PIXEL_PACK_BUFFER, m_buffer);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, Side, Side, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    ++m_reads;
    m_fence = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    GLFramebuffer::popFramebuffer();
    m_attempts = 0;
    m_dirty = false;
    m_clock.restart();
    return color;
}
