/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Place a newly installed widget before its saved neighbour once. */

import QtQuick
import org.kde.plasma.plasmoid

Timer {
    required property Item applet
    property int attempts: 0
    interval: 100
    repeat: true
    running: Plasmoid.configuration.placementBefore >= 0
    onRunningChanged: if (running) attempts = 0
    onTriggered: {
        if (++attempts > 10) { stop(); return; }
        let panel = applet.parent;
        while (panel && !panel.layoutManager) panel = panel.parent;
        if (!panel) {
            return;
        }
        const widget = Plasmoid.configuration.placementWidget || Plasmoid.id;
        const ids = String(panel.plasmoid.configuration.AppletOrder).split(";").map(Number)
            .filter(id => id > 0 && id !== widget);
        const next = ids.indexOf(Plasmoid.configuration.placementBefore);
        ids.splice(next >= 0 ? next : ids.length, 0, widget);
        if (typeof panel.reorderApplets === "function") {
            panel.reorderApplets(ids);
        } else {
            const containers = panel.layoutManager.layout.children;
            const item = containers.find(child => child.applet?.plasmoid?.id === widget);
            const neighbour = containers.find(child => child.applet?.plasmoid?.id === Plasmoid.configuration.placementBefore);
            if (!item) return;
            panel.layoutManager.move(item, neighbour ? neighbour.index : ids.length);
        }
        Plasmoid.configuration.placementBefore = -1;
        Plasmoid.configuration.placementWidget = 0;
        stop();
    }
}
