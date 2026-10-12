// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once
#include "compat.h"
#include <QColor>
#include <QElapsedTimer>
#include <epoxy/gl.h>
#include <memory>

namespace KWin { class GLTexture; class GLFramebuffer; class RenderTarget; }

/** Read a small backdrop sample asynchronously and retain only its average color. */
class BackdropContrast {
public:
    BackdropContrast();
    ~BackdropContrast();
    QColor update(const KWin::RenderTarget &target, const KWin::RenderViewport &viewport,
                  const KWin::Rect &bounds, const KWin::Region &damage);
    void invalidate() { m_dirty = true; }
    bool pending() const { return m_fence && m_attempts < 8; }
    bool due() const { return m_dirty && !m_fence && (!m_clock.isValid() || m_clock.elapsed() >= 200); }
    quint64 reads() const { return m_reads; }
private:
    bool allocate();
    QColor collect();
    std::unique_ptr<KWin::GLTexture> m_texture;
    std::unique_ptr<KWin::GLFramebuffer> m_framebuffer;
    GLuint m_buffer = 0;
    GLsync m_fence = nullptr;
    int m_attempts = 0;
    QElapsedTimer m_clock;
    KWin::Rect m_bounds;
    bool m_dirty = true;
    quint64 m_reads = 0;
};
