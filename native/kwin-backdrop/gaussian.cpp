// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "gaussian.h"
#include "core/rendertarget.h"
#include "core/renderviewport.h"
#include "opengl/glframebuffer.h"
#include "opengl/glshader.h"
#include "opengl/glshadermanager.h"
#include "opengl/gltexture.h"
#include <QVector4D>
#include <cmath>

using namespace KWin;

namespace {
/** Isolate the filter's GL state and restore it when rendering returns. */
class FilterState {
public:
    FilterState()
        : blend(glIsEnabled(GL_BLEND)), scissor(glIsEnabled(GL_SCISSOR_TEST))
    {
        glGetIntegerv(GL_SCISSOR_BOX, box);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &unit);
        glGetIntegerv(GL_BLEND_SRC_RGB, &sourceRgb);
        glGetIntegerv(GL_BLEND_DST_RGB, &destinationRgb);
        glGetIntegerv(GL_BLEND_SRC_ALPHA, &sourceAlpha);
        glGetIntegerv(GL_BLEND_DST_ALPHA, &destinationAlpha);
        glGetIntegerv(GL_BLEND_EQUATION_RGB, &equationRgb);
        glGetIntegerv(GL_BLEND_EQUATION_ALPHA, &equationAlpha);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
        glDisable(GL_BLEND);
        glDisable(GL_SCISSOR_TEST);
    }
    ~FilterState()
    {
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, texture);
        glActiveTexture(unit);
        glScissor(box[0], box[1], box[2], box[3]);
        glBlendFuncSeparate(sourceRgb, destinationRgb, sourceAlpha, destinationAlpha);
        glBlendEquationSeparate(equationRgb, equationAlpha);
        if (blend) glEnable(GL_BLEND); else glDisable(GL_BLEND);
        if (scissor) glEnable(GL_SCISSOR_TEST); else glDisable(GL_SCISSOR_TEST);
    }
private:
    GLboolean blend, scissor;
    GLint box[4], unit, texture;
    GLint sourceRgb, destinationRgb, sourceAlpha, destinationAlpha;
    GLint equationRgb, equationAlpha;
};

const QByteArray fragment = R"(
#version 140
uniform sampler2D sampler;
uniform vec2 direction;
uniform vec2 taps[17];
in vec2 texcoord0;
out vec4 fragColor;
void main() {
    vec4 color = texture(sampler, texcoord0) * taps[0].y;
    for (int i = 1; i < 17; ++i) {
        vec2 offset = direction * taps[i].x;
        color += (texture(sampler, texcoord0 + offset) + texture(sampler, texcoord0 - offset)) * taps[i].y;
    }
    fragColor = color;
}
)";
}

GaussianBackdrop::GaussianBackdrop()
    : m_shader(ShaderManager::instance()->generateCustomShader(ShaderTrait::MapTexture, {}, fragment))
{
}

GaussianBackdrop::~GaussianBackdrop() = default;

bool GaussianBackdrop::valid() const
{
    return m_shader && m_shader->isValid();
}

bool GaussianBackdrop::allocate(const QSize &size)
{
    if (m_size == size) return true;
    if (size.isEmpty() || qint64(size.width()) * size.height() > 4 * 1024 * 1024) return false;
    for (int i = 0; i < 3; ++i) {
        m_framebuffer[i].reset();
        m_texture[i] = GLTexture::allocate(GL_RGBA16F, size);
        if (!m_texture[i]) { m_size = {}; return false; }
        m_texture[i]->setFilter(GL_LINEAR);
        m_texture[i]->setWrapMode(GL_CLAMP_TO_EDGE);
        m_framebuffer[i] = std::make_unique<GLFramebuffer>(m_texture[i].get());
        if (!m_framebuffer[i]->valid()) { m_size = {}; return false; }
    }
    m_size = size;
    m_filteredSigma = -1;
    return true;
}

void GaussianBackdrop::pass(int source, int destination, const QVector2D &direction, float sigma, const QRect &patch)
{
    GLFramebuffer::pushFramebuffer(m_framebuffer[destination].get());
    QMatrix4x4 projection;
    projection.ortho(0, m_size.width(), m_size.height(), 0, 0, 1);
    ShaderBinder shader(m_shader.get());
    m_shader->setUniform("modelViewProjectionMatrix", projection);
    m_shader->setUniform("sampler", 0);
    if (sigma != m_kernelSigma) {
        std::array<float,33> weights{};
        weights[0] = 1;
        float total = 1;
        for (int i = 1; i <= 32; ++i) {
            weights[i] = std::exp(-.5f * i * i / (sigma * sigma));
            total += 2 * weights[i];
        }
        m_taps[0] = 0;
        m_taps[1] = 1 / total;
        for (int pair = 1; pair <= 16; ++pair) {
            const int first = pair * 2 - 1;
            const float weight = weights[first] + weights[first + 1];
            m_taps[pair*2] = weight > 0 ? (first * weights[first] + (first + 1) * weights[first + 1]) / weight : first;
            m_taps[pair*2+1] = weight / total;
        }
        glUniform2fv(m_shader->uniformLocation("taps"),17,m_taps.data());
        m_kernelSigma = sigma;
    }
    m_shader->setUniform("direction", direction);
    glEnable(GL_SCISSOR_TEST);
    glScissor(patch.x(),m_size.height()-patch.y()-patch.height(),patch.width(),patch.height());
    m_texture[source]->bind();
    m_texture[source]->render(m_size);
    m_texture[source]->unbind();
    GLFramebuffer::popFramebuffer();
    glDisable(GL_SCISSOR_TEST);
}

bool GaussianBackdrop::render(const RenderTarget &target, const RenderViewport &viewport,
                              const Region &shape, const Region &damage, double radius, double opacity)
{
    if (!valid() || shape.isEmpty() || !std::isfinite(radius) || radius <= 0
        || !std::isfinite(opacity) || opacity <= 0) return false;
    opacity = std::min(opacity, 1.0);
    const Region clip = targetClip(viewport, shape, damage);
    if (clip.isEmpty()) return false;
    const int margin = std::ceil(radius * 3);
    const Rect capture = shape.boundingRect().adjusted(-margin, -margin, margin, margin)
        .intersected(viewport.renderRect().toAlignedRect());
    if (capture.isEmpty()) return false;
    const double divisor = std::max(1.0, std::floor(radius * viewport.scale() / 8));
    const QSize size(std::max(1, int(std::ceil(capture.width() * viewport.scale() / divisor))),
                     std::max(1, int(std::ceil(capture.height() * viewport.scale() / divisor))));
    const bool reset = m_capture != capture || m_size != size;
    const FilterState state;
    if (!allocate(size)) return false;
    const Region dirty = reset ? Region(capture) : logicalDamage(viewport, damage) & capture;
    QRect changed;
    for (const Rect &rect : rectangles(dirty)) {
        const QRectF local((rect.x() - capture.x()) * double(size.width()) / capture.width(),
                           (rect.y() - capture.y()) * double(size.height()) / capture.height(),
                           rect.width() * double(size.width()) / capture.width(),
                           rect.height() * double(size.height()) / capture.height());
        const QRect pixels = local.toAlignedRect();
        changed = changed.united(pixels);
        if (!m_framebuffer[0]->blitFromRenderTarget(target, viewport, rect, Rect(pixels))) return false;
    }
    m_capture = capture;
    const float sigma = std::max(.01, radius * size.width() / capture.width());
    if (!changed.isEmpty() || sigma != m_filteredSigma) {
        const QRect full(QPoint(0,0),size);
        const QRect patch = reset || sigma != m_filteredSigma ? full : changed.adjusted(-32,-32,32,32).intersected(full);
        pass(0, 1, QVector2D(1.0 / size.width(), 0), sigma,patch);
        pass(1, 2, QVector2D(0, 1.0 / size.height()), sigma,patch);
        m_filteredSigma = sigma;
    }
    {
        glEnable(GL_SCISSOR_TEST);
        glEnable(GL_BLEND);
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
        glBlendEquation(GL_FUNC_ADD);
        ShaderBinder shader(ShaderTrait::MapTexture | ShaderTrait::Modulate);
        QMatrix4x4 projection = viewport.projectionMatrix();
        projection.translate(capture.x(), capture.y());
        shader.shader()->setUniform("modelViewProjectionMatrix", projection);
        shader.shader()->setUniform("sampler", 0);
        shader.shader()->setUniform(GLShader::Vec4Uniform::ModulationConstant,
            QVector4D(opacity, opacity, opacity, opacity));
        m_texture[2]->bind();
        m_texture[2]->render(clip, capture.size(), true);
        m_texture[2]->unbind();
    }
    return true;
}
