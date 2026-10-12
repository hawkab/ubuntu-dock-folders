// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "backdropblur.h"
#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QPointer>
#include <QUuid>
#include <QColor>

namespace {
QDBusMessage request(const QString &path, const QString &interface, const QString &member)
{
    return QDBusMessage::createMethodCall(QStringLiteral("org.kde.KWin"), path, interface, member);
}
int owners = 0;
void unload()
{
    auto message = request(QStringLiteral("/Effects"), QStringLiteral("org.kde.kwin.Effects"), QStringLiteral("unloadEffect"));
    message << QStringLiteral(DOCK_BACKDROP_PLUGIN_ID);
    QDBusConnection::sessionBus().asyncCall(message, 1000);
}
}

BackdropBlur::BackdropBlur(QObject *parent) : QObject(parent)
{
    ++owners;
    m_prefix = QStringLiteral("io.github.hawkab.DockFolders.Glass.") + QUuid::createUuid().toString(QUuid::Id128) + QLatin1Char(':');
    QDBusConnection::sessionBus().connect(QStringLiteral("org.kde.KWin"),
        QStringLiteral("/io/github/hawkab/DockFolders/Backdrop"), QStringLiteral("io.github.hawkab.DockFolders.Backdrop"),
        QStringLiteral("backgroundChanged"), this, SLOT(receiveBackground(QString,QString)));
    auto service = new QDBusServiceWatcher(QStringLiteral("org.kde.KWin"), QDBusConnection::sessionBus(),
                                          QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(service, &QDBusServiceWatcher::serviceOwnerChanged, this,
        [this](const QString &, const QString &, const QString &owner) {
            m_ready = false;
            emit readyChanged();
            if (!owner.isEmpty()) load();
        });
    load();
}

void BackdropBlur::receiveBackground(const QString &token, const QString &color)
{
    if (token != m_prefix || !QColor::isValidColorName(color) || color == m_background) return;
    m_background = color;
    emit backgroundChanged();
}

void BackdropBlur::load()
{
    auto message = request(QStringLiteral("/Effects"), QStringLiteral("org.kde.kwin.Effects"), QStringLiteral("loadEffect"));
    message << QStringLiteral(DOCK_BACKDROP_PLUGIN_ID);
    const QPointer<BackdropBlur> guard(this);
    auto watcher = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message, 2000), qApp);
    connect(watcher, &QDBusPendingCallWatcher::finished, qApp, [guard](QDBusPendingCallWatcher *pending) {
        const QDBusPendingReply<bool> reply = *pending;
        pending->deleteLater();
        if (reply.isError()) return;
        if (!guard) { if (!owners) unload(); return; }
        auto check = request(QStringLiteral("/Effects"), QStringLiteral("org.kde.kwin.Effects"), QStringLiteral("isEffectLoaded"));
        check << QStringLiteral(DOCK_BACKDROP_PLUGIN_ID);
        auto running = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(check, 2000), qApp);
        connect(running, &QDBusPendingCallWatcher::finished, qApp, [guard](QDBusPendingCallWatcher *completion) {
            const QDBusPendingReply<bool> result = *completion;
            completion->deleteLater();
            if (!guard) { if (!owners) unload(); return; }
            if (result.isError()) return;
            guard->m_ready = result.value();
            emit guard->readyChanged();
        });
    });
}

BackdropBlur::~BackdropBlur()
{
    if (--owners == 0) unload();
}
