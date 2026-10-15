/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Display and scroll dock launchers without wrapping across the panel. */

import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "../effects" as Effects
import "Core.js" as Core

Item {
    id: strip
    required property var controller
    implicitWidth: strip.controller.vertical ? 48 : dock.implicitWidth
    implicitHeight: strip.controller.vertical ? dock.implicitHeight : 48
    function folderAnchors() {
        const anchors = [];
        for (const item of dock.children) {
            if (!item.visible || !item.folder || !item.iconAnchor) continue;
            const point = item.mapToGlobal(0, 0);
            anchors.push({key: strip.controller.groupKey(item.folder), x: point.x, y: point.y,
                width: item.width, height: item.height, button: item});
        }
        return anchors;
    }
    Flickable {
        id: viewport
        x: strip.controller.vertical ? -6 : 0
        y: strip.controller.vertical ? 0 : -6
        width: parent.width + (strip.controller.vertical ? 12 : 0)
        height: parent.height + (strip.controller.vertical ? 0 : 12)
        contentWidth: strip.controller.vertical ? width : dock.implicitWidth
        contentHeight: strip.controller.vertical ? dock.implicitHeight : height
        flickableDirection: strip.controller.vertical ? Flickable.VerticalFlick : Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        Grid {
            id: dock
            x: strip.controller.vertical ? 6 : 0
            y: strip.controller.vertical ? 0 : 6
            rows: strip.controller.vertical ? 0 : 1
            columns: strip.controller.vertical ? 1 : 0
            spacing: 0
            Repeater {
                model: strip.controller.dockFavorites
                delegate: ApplicationIcon {
                    required property string modelData
                    controller: strip.controller
                    desktop: modelData
                    folder: strip.controller.groupingEnabled ? strip.controller.groupFor(desktop) : null
                    onActivated: folder ? strip.controller.openFolder(desktop, this) : strip.controller.activate(desktop)
                }
            }
            Repeater {
                id: taskRepeater
                Component.onCompleted: strip.controller.taskDelegateModel = this
                model: strip.controller.taskModel
                delegate: Item {
                    id: task
                    required property var model
                    required property int index
                    property int row: index
                    property string desktop: Core.matchPwa(strip.controller.state.pwas || {},
                        Array.from(identity.classes).concat([model.AppId]),
                        strip.controller.canonical(model.LauncherUrlWithoutIcon || model.AppId))
                    property bool running: model.IsWindow
                    property bool active: model.IsActive
                    property var ids: model.WinIdList || []
                    property string title: model.display || model.AppName || ""
                    property bool shown: running && !strip.controller.grouped(desktop) && strip.controller.state.favorites.indexOf(desktop) < 0
                                         && !strip.controller.taskRows(desktop).some(item => item.row < row && item.running)
                    width: shown && visual.item ? visual.item.implicitWidth : 0
                    height: shown && visual.item ? visual.item.implicitHeight : 0
                    visible: shown
                    onRunningChanged: strip.controller.scheduleTasks()
                    onActiveChanged: strip.controller.scheduleTasks()
                    onDesktopChanged: strip.controller.scheduleTasks()
                    Effects.TaskIdentity {
                        id: identity
                        enabled: task.running && Object.keys(strip.controller.state.pwas || {}).length > 0
                        windowIds: task.ids
                        hint: String(task.model.AppId || "") + String(task.model.LauncherUrlWithoutIcon || "")
                    }
                    Loader {
                        id: visual
                        anchors.fill: parent
                        active: task.shown
                        sourceComponent: ApplicationIcon {
                            controller: strip.controller
                            desktop: task.desktop
                            label: task.title
                            iconSource: task.model.decoration
                            onActivated: strip.controller.activate(task.desktop)
                        }
                    }
                    Component.onCompleted: strip.controller.scheduleTasks()
                }
            }
            Item { width: 24; height: strip.controller.iconSize }
        }
    }
    DropArea {
        z: -1
        anchors.fill: parent
        enabled: strip.controller.groupingEnabled
        onDropped: event => {
            const desktop = strip.controller.dragDesktop(event);
            if (desktop) { strip.controller.edit({operation: desktop.indexOf("local.groups.") === 0 ? "reorder" : "extract", desktop}); event.acceptProposedAction(); }
        }
    }
    QQC2.Label {
        visible: !!strip.controller.serviceError
        anchors.centerIn: parent
        text: strip.controller.serviceError
        wrapMode: Text.Wrap
    }
}
