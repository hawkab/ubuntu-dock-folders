// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "compat.h"
#include "core/rendertarget.h"
#include "effect/effect.h"
#include "effect/effecthandler.h"
#include "effect/effectwindow.h"
#include "wayland/blur.h"
#include "wayland/surface.h"
#include <QDir>
#include <QFile>
#include <QElapsedTimer>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <epoxy/gl.h>

using namespace KWin;
#if DOCK_KWIN_REGIONS
using ProbeOutput = LogicalOutput;
#else
using ProbeOutput = Output;
#endif

/** Read the next normally painted private frame without scheduling a repaint. */
class PresentedFrame : public Effect {
    Q_OBJECT
public:
    bool isActive() const override { return true; }
    bool blocksDirectScanout() const override { return false; }
    int requestedEffectChainPosition() const override { return 1; }
    QString debug(const QString &parameter) const override
    {
        if (parameter == QStringLiteral("capture")) pending = true;
        if (parameter == QStringLiteral("record")) { recording = true; sequence = 0; clock.start(); last = -40; }
        if (parameter == QStringLiteral("stop")) recording = false;
        return pending ? QStringLiteral("pending") : QStringLiteral("ready");
    }
    void paintScreen(const RenderTarget &target, const RenderViewport &viewport, int mask,
                     const Region &damage, ProbeOutput *output) override
    {
        effects->paintScreen(target, viewport, mask, damage, output);
        if (target.size() != QSize(1100, 760)) return;
        const Region painted = logicalDamage(viewport,damage);
        bool folderPainted = false;
        for (EffectWindow *window : effects->stackingOrder())
            if (window->isVisible() && window->caption().startsWith(QStringLiteral("io.github.hawkab.DockFolders.Glass."))
                && painted.intersects(Rect(window->frameGeometry().toAlignedRect()))) folderPainted = true;
        if (!pending && !recording && !folderPainted) return;
        if (recording && clock.elapsed() - last < 40) return;
        if (recording) last = clock.elapsed();
        const bool captureFrame = pending;
        pending = false;
        QImage frame(target.size(), QImage::Format_RGBA8888);
        GLint alignment, buffer;
        glGetIntegerv(GL_PACK_ALIGNMENT, &alignment);
        glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &buffer);
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
        glPixelStorei(GL_PACK_ALIGNMENT, 4);
        glReadPixels(0, 0, frame.width(), frame.height(), GL_RGBA, GL_UNSIGNED_BYTE, frame.bits());
        glPixelStorei(GL_PACK_ALIGNMENT, alignment);
        glBindBuffer(GL_PIXEL_PACK_BUFFER, buffer);
        if (target.transform() != OutputTransform::FlipY) frame = frame.flipped(Qt::Vertical);
        if (presented.size() != frame.size()) presented = frame.copy();
        else {
            QPainter painter(&presented);
            painter.setCompositionMode(QPainter::CompositionMode_Source);
            for (const Rect &area : rectangles(painted)) {
                const QRect rect(area.x(),area.y(),area.width(),area.height());
                painter.drawImage(rect,frame,rect);
            }
        }
        const QString directory = qEnvironmentVariable("XDG_CACHE_HOME");
        QDir().mkpath(directory);
        if (!recording) {
            if (captureFrame) presented.save(directory + QStringLiteral("/presented-frame.png"));
            return;
        }
        for (EffectWindow *window : effects->stackingOrder()) {
            if (!window->isVisible() || !window->caption().startsWith(QStringLiteral("io.github.hawkab.DockFolders.Glass."))) continue;
            const QString stem = directory + QStringLiteral("/animation-%1").arg(sequence++, 4, 10, QLatin1Char('0'));
            Rect bounds;
            if (auto surface = window->surface()) {
                if (auto blur = surface->blur()) bounds = blur->region().boundingRect();
            }
            if (bounds.isEmpty()) bounds = Rect(QPoint(),window->size().toSize());
            presented.save(stem + QStringLiteral(".png"));
            QFile metadata(stem + QStringLiteral(".json"));
            if (metadata.open(QIODevice::WriteOnly)) metadata.write(QJsonDocument(QJsonObject{
                {QStringLiteral("caption"),window->caption()}, {QStringLiteral("x"),window->pos().x()},
                {QStringLiteral("y"),window->pos().y()}, {QStringLiteral("width"),window->size().width()},
                {QStringLiteral("height"),window->size().height()}, {QStringLiteral("left"),bounds.x()},
                {QStringLiteral("top"),bounds.y()}, {QStringLiteral("right"),bounds.x()+bounds.width()},
                {QStringLiteral("bottom"),bounds.y()+bounds.height()}}).toJson(QJsonDocument::Compact));
            break;
        }
        if (sequence >= 600) recording = false;
    }
private:
    QImage presented;
    mutable bool pending = false;
    mutable bool recording = false;
    mutable int sequence = 0;
    mutable QElapsedTimer clock;
    mutable qint64 last = -40;
};

KWIN_EFFECT_FACTORY_SUPPORTED_ENABLED(PresentedFrame, "presented-frame.json",
    return effects->isOpenGLCompositing();, return false;)

#include "presented-frame.moc"
