// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once
#include <memory>
#include <QSize>
#include <QVector2D>
#include <QRect>
#include <array>
#include "compat.h"

namespace KWin {
class GLTexture;
class GLFramebuffer;
class GLShader;
class RenderTarget;
class RenderViewport;
}

/** Filter compositor pixels behind a clipped surface with a variable Gaussian radius. */
class GaussianBackdrop {
public:
    GaussianBackdrop();
    ~GaussianBackdrop();
    bool valid() const;
    bool render(const KWin::RenderTarget &target, const KWin::RenderViewport &viewport,
                const KWin::Region &shape, const KWin::Region &damage, double radius, double opacity = 1);
private:
    bool allocate(const QSize &size);
    void pass(int source, int destination, const QVector2D &direction, float sigma, const QRect &patch);
    std::unique_ptr<KWin::GLShader> m_shader;
    std::unique_ptr<KWin::GLTexture> m_texture[3];
    std::unique_ptr<KWin::GLFramebuffer> m_framebuffer[3];
    KWin::Rect m_capture;
    QSize m_size;
    float m_kernelSigma = -1;
    float m_filteredSigma = -1;
    std::array<float,34> m_taps{};
};
