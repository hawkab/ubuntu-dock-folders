// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once

#include <QObject>
#include <QPointer>
#include <QRectF>
#include <QWindow>
#include <QVariantList>
#include <memory>

class WaylandBlur;

/** Apply compositor blur to a rounded region of a QML window. */
class WindowEffects : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QWindow *window READ window WRITE setWindow NOTIFY changed)
    Q_PROPERTY(bool enabled READ enabled WRITE setEnabled NOTIFY changed)
    Q_PROPERTY(bool allowSmallBlur READ allowSmallBlur WRITE setAllowSmallBlur NOTIFY changed)
    Q_PROPERTY(QRectF region READ region WRITE setRegion NOTIFY changed)
    Q_PROPERTY(qreal radius READ radius WRITE setRadius NOTIFY changed)
    Q_PROPERTY(QVariantList polygon READ polygon WRITE setPolygon NOTIFY changed)
    Q_PROPERTY(bool constrainInput READ constrainInput WRITE setConstrainInput NOTIFY changed)
    Q_PROPERTY(QRectF inputRegion READ inputRegion WRITE setInputRegion NOTIFY changed)

public:
    explicit WindowEffects(QObject *parent = nullptr);
    ~WindowEffects() override;
    QWindow *window() const { return m_window; }
    bool enabled() const { return m_enabled; }
    bool allowSmallBlur() const { return m_allowSmallBlur; }
    QRectF region() const { return m_region; }
    qreal radius() const { return m_radius; }
    QVariantList polygon() const { return m_polygon; }
    bool constrainInput() const { return m_constrainInput; }
    QRectF inputRegion() const { return m_inputRegion; }
    void setWindow(QWindow *window);
    void setEnabled(bool enabled);
    void setAllowSmallBlur(bool allowed);
    void setRegion(const QRectF &region);
    void setRadius(qreal radius);
    void setPolygon(const QVariantList &polygon);
    void setConstrainInput(bool constrain);
    void setInputRegion(const QRectF &region);
    Q_INVOKABLE bool blurAvailable() const;
    Q_INVOKABLE void raiseForeground();

signals:
    void changed();

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void scheduleUpdate();
    void update();
    QPointer<QWindow> m_window;
    QRectF m_region;
    QVariantList m_polygon;
    QRectF m_inputRegion;
    bool m_constrainInput = false;
    qreal m_radius = 20;
    bool m_enabled = false;
    bool m_allowSmallBlur = false;
    bool m_pending = false;
    std::unique_ptr<WaylandBlur> m_wayland;
};
