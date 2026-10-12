// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "windoweffects.h"
#include "waylandblur.h"

#include <KWindowEffects>
#include <QEvent>
#include <QGuiApplication>
#include <QPainterPath>
#include <QRegion>
#include <QQuickWindow>
#include <QTimer>
#include <QPlatformSurfaceEvent>

WindowEffects::WindowEffects(QObject *parent) : QObject(parent)
{
    connect(this, &WindowEffects::changed, this, &WindowEffects::scheduleUpdate);
    m_wayland = std::make_unique<WaylandBlur>([this] { scheduleUpdate(); });
}

WindowEffects::~WindowEffects()
{
    if (m_window) {
        m_wayland->clear();
        m_window->removeEventFilter(this);
        KWindowEffects::enableBlurBehind(m_window, false);
    }
}

void WindowEffects::setWindow(QWindow *window)
{
    if (window == m_window) return;
    if (m_window) {
        m_wayland->clear();
        m_window->removeEventFilter(this);
        disconnect(m_window, nullptr, this, nullptr);
        KWindowEffects::enableBlurBehind(m_window, false);
    }
    m_window = window;
    if (window) {
        window->installEventFilter(this);
        connect(window, &QWindow::visibleChanged, this, &WindowEffects::scheduleUpdate);
        connect(window, &QWindow::screenChanged, this, &WindowEffects::scheduleUpdate);
    }
    emit changed();
}

void WindowEffects::setEnabled(bool enabled)
{
    if (m_enabled == enabled) return;
    m_enabled = enabled;
    emit changed();
}

void WindowEffects::setAllowSmallBlur(bool allowed)
{
    if (m_allowSmallBlur == allowed) return;
    m_allowSmallBlur = allowed;
    emit changed();
}

void WindowEffects::setRegion(const QRectF &region)
{
    if (m_region == region) return;
    m_region = region;
    emit changed();
}

void WindowEffects::setRadius(qreal radius)
{
    if (qFuzzyCompare(m_radius, radius)) return;
    m_radius = qMax(0.0, radius);
    emit changed();
}

void WindowEffects::setPolygon(const QVariantList &polygon)
{
    if (m_polygon == polygon) return;
    m_polygon = polygon;
    emit changed();
}

void WindowEffects::setConstrainInput(bool constrain)
{
    if (m_constrainInput == constrain) return;
    m_constrainInput = constrain;
    emit changed();
}

void WindowEffects::setInputRegion(const QRectF &region)
{
    if (m_inputRegion == region) return;
    m_inputRegion = region;
    emit changed();
}

bool WindowEffects::eventFilter(QObject *watched, QEvent *event)
{
    if (event->type() == QEvent::PlatformSurface
        && static_cast<QPlatformSurfaceEvent *>(event)->surfaceEventType() == QPlatformSurfaceEvent::SurfaceAboutToBeDestroyed)
        m_wayland->clear();
    if (event->type() == QEvent::PlatformSurface || event->type() == QEvent::Show
        || event->type() == QEvent::Expose || event->type() == QEvent::Resize)
        scheduleUpdate();
    return QObject::eventFilter(watched, event);
}

bool WindowEffects::blurAvailable() const
{
    return KWindowEffects::isEffectAvailable(KWindowEffects::BlurBehind);
}

void WindowEffects::raiseForeground()
{
    if (m_window && m_window->isVisible() && QGuiApplication::platformName() == QStringLiteral("xcb"))
        m_window->raise();
}

void WindowEffects::scheduleUpdate()
{
    if (m_pending) return;
    m_pending = true;
    QTimer::singleShot(0, this, &WindowEffects::update);
}

void WindowEffects::update()
{
    m_pending = false;
    if (!m_window) return;
    if (!m_window->isVisible()) {
        if (!m_wayland->apply(m_window, false, {})) KWindowEffects::enableBlurBehind(m_window, false);
        return;
    }
    KWindowEffects::slideWindow(m_window, KWindowEffects::NoEdge, 0);
    m_window->setMask(m_constrainInput ? QRegion(m_inputRegion.toAlignedRect()) : QRegion());
    QPainterPath path;
    if (m_polygon.isEmpty()) {
        path.addRoundedRect(m_region, m_radius, m_radius);
    } else {
        QPolygonF polygon;
        for (const auto &point : m_polygon) {
            const auto coordinates = point.toMap();
            const QPointF position = coordinates.isEmpty() ? point.toPointF()
                : QPointF(coordinates.value("x").toReal(), coordinates.value("y").toReal());
            if (!qIsFinite(position.x()) || !qIsFinite(position.y())) { polygon.clear(); break; }
            polygon.append(position);
        }
        path.addPolygon(polygon);
    }
    const QRegion region = QRegion(path.toFillPolygon().toPolygon())
        .intersected(QRect(0, 0, m_window->width(), m_window->height()));
    const QRect bounds = region.boundingRect();
    const int minimum = m_allowSmallBlur ? 1 : 32;
    const bool safe = m_enabled && bounds.width() >= minimum && bounds.height() >= minimum;
    if (!m_wayland->apply(m_window, safe, region)) KWindowEffects::enableBlurBehind(m_window, safe, region);
    if (m_enabled) {
        if (auto quick = qobject_cast<QQuickWindow *>(m_window.data())) quick->update();
    }
}
