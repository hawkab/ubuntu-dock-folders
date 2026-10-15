// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once
#include <QObject>
#include <QStringList>
#include <QVariantList>

/** Read original compositor classes for one ungrouped task row. */
class TaskIdentity : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList windowIds READ windowIds WRITE setWindowIds NOTIFY inputsChanged)
    Q_PROPERTY(QString hint READ hint WRITE setHint NOTIFY inputsChanged)
    Q_PROPERTY(bool enabled READ enabled WRITE setEnabled NOTIFY inputsChanged)
    Q_PROPERTY(QStringList classes READ classes NOTIFY classesChanged)
public:
    explicit TaskIdentity(QObject *parent = nullptr);
    QVariantList windowIds() const { return m_ids; }
    QString hint() const { return m_hint; }
    bool enabled() const { return m_enabled; }
    QStringList classes() const { return m_classes; }
    void setWindowIds(const QVariantList &ids);
    void setHint(const QString &hint);
    void setEnabled(bool enabled);
signals:
    void inputsChanged();
    void classesChanged();
private:
    void schedule();
    void refresh();
    void publish(const QStringList &classes);
    QVariantList m_ids;
    QString m_hint;
    QStringList m_classes;
    quint64 m_generation = 0;
    bool m_enabled = false;
    bool m_scheduled = false;
};
