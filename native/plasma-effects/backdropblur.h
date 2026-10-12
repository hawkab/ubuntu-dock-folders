// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once

#include <QObject>
#include <QString>

/** Load the folder's KWin blur effect; unload it with the last widget. */
class BackdropBlur : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString prefix READ prefix NOTIFY prefixChanged)
    Q_PROPERTY(bool ready READ ready NOTIFY readyChanged)
    Q_PROPERTY(QString background READ background NOTIFY backgroundChanged)
public:
    explicit BackdropBlur(QObject *parent = nullptr);
    ~BackdropBlur() override;
    QString prefix() const { return m_prefix; }
    bool ready() const { return m_ready; }
    QString background() const { return m_background; }
signals:
    void prefixChanged();
    void readyChanged();
    void backgroundChanged();
private slots:
    void receiveBackground(const QString &token, const QString &color);
private:
    void load();
    QString m_prefix;
    bool m_ready = false;
    QString m_background;
};
