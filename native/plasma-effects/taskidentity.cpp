// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "taskidentity.h"
#include <KWindowInfo>
#include <KWindowSystem>
#include <KX11Extras>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QTimer>
#include <QUuid>
#include <memory>

TaskIdentity::TaskIdentity(QObject *parent) : QObject(parent)
{
    connect(this, &TaskIdentity::inputsChanged, this, &TaskIdentity::schedule);
    if (KWindowSystem::isPlatformX11()) {
        connect(KX11Extras::self(), &KX11Extras::windowChanged, this,
            [this](WId id, NET::Properties, NET::Properties2 flags) {
                if (m_enabled && (flags & NET::WM2WindowClass) && m_ids.contains(QVariant::fromValue<qulonglong>(id)))
                    schedule();
            });
    }
}

void TaskIdentity::setWindowIds(const QVariantList &ids)
{
    if (m_ids == ids) return;
    m_ids = ids;
    emit inputsChanged();
}

void TaskIdentity::setHint(const QString &hint)
{
    if (m_hint == hint) return;
    m_hint = hint;
    emit inputsChanged();
}

void TaskIdentity::setEnabled(bool enabled)
{
    if (m_enabled == enabled) return;
    m_enabled = enabled;
    emit inputsChanged();
}

void TaskIdentity::publish(const QStringList &classes)
{
    if (m_classes == classes) return;
    m_classes = classes;
    emit classesChanged();
}

void TaskIdentity::schedule()
{
    ++m_generation;
    if (m_scheduled) return;
    m_scheduled = true;
    QTimer::singleShot(0, this, [this] { m_scheduled = false; refresh(); });
}

void TaskIdentity::refresh()
{
    const auto generation = m_generation;
    if (!m_enabled) { publish({}); return; }
    QStringList classes;
    if (KWindowSystem::isPlatformX11()) {
        for (const auto &value : m_ids) {
            const auto id = value.toULongLong();
            if (!id) continue;
            KWindowInfo info(id, {}, NET::WM2WindowClass);
            if (info.valid()) classes << QString::fromUtf8(info.windowClassName()) << QString::fromUtf8(info.windowClassClass());
        }
        publish(classes);
        return;
    }
    publish({});
    auto pendingClasses = std::make_shared<QStringList>();
    for (const auto &value : m_ids) {
        const auto id = value.toString();
        if (QUuid(id).isNull()) continue;
        auto message = QDBusMessage::createMethodCall(QStringLiteral("org.kde.KWin"), QStringLiteral("/KWin"),
            QStringLiteral("org.kde.KWin"), QStringLiteral("getWindowInfo"));
        message << id;
        auto watcher = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message, 1000), this);
        connect(watcher, &QDBusPendingCallWatcher::finished, this, [this,watcher,generation,pendingClasses] {
            const QDBusPendingReply<QVariantMap> reply = *watcher;
            watcher->deleteLater();
            if (generation != m_generation || reply.isError()) return;
            const auto metadata = reply.value();
            *pendingClasses << metadata.value(QStringLiteral("resourceName")).toString()
                            << metadata.value(QStringLiteral("resourceClass")).toString();
            publish(*pendingClasses);
        });
    }
}
