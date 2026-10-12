// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "gaussian.h"
#include "contrast.h"
#include "effect/effect.h"
#include "effect/effecthandler.h"
#include "effect/effectwindow.h"
#if DOCK_KWIN_REGIONS
#include "scene/backgroundeffectitem.h"
#endif
#include "wayland/blur.h"
#include "wayland/surface.h"
#include <QHash>
#include <QPointer>
#include <QDBusConnection>
#include <QTimer>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <xcb/xcb.h>

using namespace KWin;

/** Filter the desktop behind tagged folder windows before drawing their controls. */
class DockFolderBackdrop : public Effect {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "io.github.hawkab.DockFolders.Backdrop")
public:
    DockFolderBackdrop()
    {
        QDBusConnection::sessionBus().registerObject(QStringLiteral("/io/github/hawkab/DockFolders/Backdrop"),
            this, QDBusConnection::ExportAllSignals);
        for (EffectWindow *window : effects->stackingOrder()) watch(window);
        connect(effects, &EffectsHandler::windowAdded, this, &DockFolderBackdrop::watch);
        connect(effects, &EffectsHandler::stackingOrderChanged, this, [this] {
            for (const auto &sample : std::as_const(m_samples)) sample->invalidate();
        });
        connect(effects, &EffectsHandler::windowDeleted, this, [this](EffectWindow *window) {
            effects->makeOpenGLContextCurrent();
            m_samples.remove(window); m_colors.remove(window);
        });
        auto timer = new QTimer(this);
        timer->setInterval(200);
        connect(timer, &QTimer::timeout, this, [this] {
            for (auto it = m_samples.cbegin(); it != m_samples.cend(); ++it)
                if (it.key()->isVisible() && it.value()->due()) {
                    const int margin = std::ceil(radius(it.key()) * 3);
                    effects->addRepaint(it.key()->frameGeometry().adjusted(-margin,-margin,margin,margin));
                }
        });
        timer->start();
        m_atom = effects->announceSupportProperty(QByteArrayLiteral("_KDE_NET_WM_BLUR_BEHIND_REGION"), this);
#if DOCK_KWIN_REGIONS
        connect(effects, &EffectsHandler::windowDeleted, this, [this](EffectWindow *window) {
            delete m_items.take(window).data();
        });
#endif
    }
    ~DockFolderBackdrop() override
    {
        effects->makeOpenGLContextCurrent();
        m_samples.clear();
        QDBusConnection::sessionBus().unregisterObject(QStringLiteral("/io/github/hawkab/DockFolders/Backdrop"));
#if DOCK_KWIN_REGIONS
        for (const auto &item : std::as_const(m_items)) delete item.data();
#endif
    }
    int requestedEffectChainPosition() const override { return 19; }
    QString debug(const QString &parameter) const override
    {
        if (parameter == QStringLiteral("api")) return QStringLiteral("dock-folders-backdrop/4");
        if (parameter == QStringLiteral("frames"))
            return QStringLiteral("drawn=%1; clip=%2,%3 %4x%5; scale=%6")
                .arg(m_drawn).arg(m_clip.x()).arg(m_clip.y()).arg(m_clip.width()).arg(m_clip.height()).arg(m_scale);
        if (parameter == QStringLiteral("contrast")) {
            quint64 reads = 0;
            for (const auto &sample : std::as_const(m_samples)) reads += sample->reads();
            return QStringLiteral("reads=%1; windows=%2").arg(reads).arg(m_samples.size());
        }
        return Effect::debug(parameter);
    }
    bool isActive() const override
    {
        if (!m_filter.valid()) return false;
        for (EffectWindow *window : effects->stackingOrder())
            if (window->isVisible() && (radius(window) > 0 || samplesBackground(window))) return true;
        return false;
    }
    void prePaintScreen(ScreenPrePaintData &data, std::chrono::milliseconds presentTime) override
    {
        for (EffectWindow *window : effects->stackingOrder()) {
            const double amount = radius(window);
            if (!window->isVisible() || amount <= 0) continue;
            const Rect bounds = shape(window).boundingRect().translated(window->pos().toPoint());
            if (!bounds.isEmpty() && data.paint.intersects(bounds)) {
                const int margin = std::ceil(amount * 3);
                data.paint |= bounds.adjusted(-margin,-margin,margin,margin);
            }
        }
        effects->prePaintScreen(data, presentTime);
    }
    void drawWindow(const RenderTarget &target, const RenderViewport &viewport,
                    EffectWindow *window, int mask, const Region &damage, WindowPaintData &data) override
    {
        const double amount = radius(window);
        if (amount > 0) mask |= PAINT_WINDOW_TRANSFORMED;
        if (samplesBackground(window) && !effects->activeFullScreenEffect()) {
            const int margin = std::ceil(amount * 3);
            const Rect bounds = sampleBounds(window).translated(window->pos().toPoint());
            if (viewport.renderRect().contains(QPointF(bounds.center()))) {
                auto &sample = m_samples[window];
                if (!sample) sample = std::make_shared<BackdropContrast>();
                const QColor color = sample->update(target, viewport, bounds, damage);
                if (color.isValid() && color != m_colors.value(window)) {
                    m_colors.insert(window, color);
                    emit backgroundChanged(window->caption().section(QLatin1Char(':'), 0, 0) + QLatin1Char(':'), color.name());
                }
                if (sample->pending()) effects->addRepaint(bounds.adjusted(-margin, -margin, margin, margin));
            }
        }
        if (amount > 0 && !effects->activeFullScreenEffect()) {
            Region region = shape(window);
            if (!region.isEmpty()) {
#if DOCK_KWIN_REGIONS
                auto item = m_items.value(window);
                if (!item) {
                    item = new BackgroundEffectItem(window->windowItem());
                    m_items.insert(window, item);
                }
                item->setEffectBoundingRect(region.boundingRect());
                item->setPixelsToExpandRepaintsBelowOpaqueRegions(std::ceil(amount * 3));
#endif
                region.translate(window->pos().toPoint());
                if (m_filter.render(target, viewport, region, damage, amount, opacity(window))) {
                    ++m_drawn;
                    m_clip = targetClip(viewport, region, damage).boundingRect();
                    m_scale = viewport.scale();
                }
            }
        }
        effects->drawWindow(target, viewport, window, mask, damage, data);
    }
signals:
    void backgroundChanged(const QString &token, const QString &color);
private:
    static bool tagged(EffectWindow *window)
    {
        return window->windowClass().contains(QStringLiteral("plasmashell"))
            && window->caption().startsWith(QStringLiteral("io.github.hawkab.DockFolders.Glass."));
    }
    static bool samplesBackground(EffectWindow *window)
    {
        return tagged(window) && window->caption().section(QLatin1Char(':'), 4, 4) == QStringLiteral("1");
    }
    static Rect sampleBounds(EffectWindow *window)
    {
        const auto parts = window->caption().section(QLatin1Char(':'), 3, 3).split(QLatin1Char(','));
        if (parts.size() != 4) return {};
        int values[4];
        for (int i = 0; i < 4; ++i) {
            bool valid;
            values[i] = parts[i].toInt(&valid);
            if (!valid || std::abs(values[i]) > 8192) return {};
        }
        return Rect(values[0], values[1], values[2], values[3]) & Rect(QPoint(),window->size().toSize());
    }
    void watch(EffectWindow *window)
    {
        const auto dirty = [this](EffectWindow *changed) {
            if (tagged(changed)) return;
            const auto order = effects->stackingOrder();
            for (auto it = m_samples.cbegin(); it != m_samples.cend(); ++it)
                if (order.indexOf(changed) < order.indexOf(it.key())
                    && Rect(changed->frameGeometry().toAlignedRect()).intersects(sampleBounds(it.key()).translated(it.key()->pos().toPoint())))
                    it.value()->invalidate();
        };
        connect(window, &EffectWindow::windowDamaged, this, dirty);
        connect(window, &EffectWindow::windowExpandedGeometryChanged, this, dirty);
        connect(window, &EffectWindow::windowFrameGeometryAboutToChange, this, dirty);
        connect(window, &EffectWindow::windowHiddenChanged, this, dirty);
    }
    static double radius(EffectWindow *window)
    {
        const QString caption = window->caption();
        if (!window->windowClass().contains(QStringLiteral("plasmashell"))
            || !caption.startsWith(QStringLiteral("io.github.hawkab.DockFolders.Glass."))) return 0;
        bool valid = false;
        const double strength = caption.section(QLatin1Char(':'), 1, 1).toDouble(&valid);
        return valid && std::isfinite(strength) && strength > 0 && strength <= 1 ? strength * 48 : 0;
    }
    static double opacity(EffectWindow *window)
    {
        const QString value = window->caption().section(QLatin1Char(':'), 2, 2);
        if (value.isEmpty()) return 1;
        bool valid = false;
        const double opacity = value.toDouble(&valid);
        return valid && std::isfinite(opacity) ? std::clamp(opacity, 0.0, 1.0) : 0;
    }
    Region shape(EffectWindow *window) const
    {
        if (auto surface = window->surface()) {
            if (auto blur = surface->blur()) return blur->region();
            return {};
        }
        const QByteArray property = window->readProperty(m_atom, XCB_ATOM_CARDINAL, 32);
        if (property.isEmpty() || property.size() % 16) return {};
        Region region;
        for (qsizetype i = 0; i < property.size(); i += 16) {
            uint32_t rect[4];
            std::memcpy(rect, property.constData() + i, sizeof(rect));
            if (rect[2] > 8192 || rect[3] > 8192) return {};
            region |= Rect(rect[0], rect[1], rect[2], rect[3]);
        }
        return region & Rect(QPoint(), window->size().toSize());
    }
    GaussianBackdrop m_filter;
    QHash<EffectWindow *, std::shared_ptr<BackdropContrast>> m_samples;
    QHash<EffectWindow *, QColor> m_colors;
    quint64 m_drawn = 0;
    Rect m_clip;
    double m_scale = 1;
#if DOCK_KWIN_REGIONS
    QHash<EffectWindow *, QPointer<BackgroundEffectItem>> m_items;
#endif
    xcb_atom_t m_atom;
};

KWIN_EFFECT_FACTORY_SUPPORTED_ENABLED(DockFolderBackdrop, "metadata.json",
    return effects->isOpenGLCompositing();, return false;)

#include "backdrop.moc"
