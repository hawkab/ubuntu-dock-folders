// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "windoweffects.h"
#include "backdropblur.h"
#include "taskidentity.h"
#include <QQmlExtensionPlugin>
#include <qqml.h>

/** Register the window-effects adapter for the folder popup. */
class DockEffectsPlugin final : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override
    {
        qmlRegisterType<WindowEffects>(uri, 1, 0, "WindowEffects");
        qmlRegisterType<BackdropBlur>(uri, 1, 0, "BackdropBlur");
        qmlRegisterType<TaskIdentity>(uri, 1, 0, "TaskIdentity");
    }
};

#include "plugin.moc"
