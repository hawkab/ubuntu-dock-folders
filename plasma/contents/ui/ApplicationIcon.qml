/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import "IconGeometry.js" as Geometry
import "Core.js" as Core

PlasmaCore.ToolTipArea {
    id: button
    readonly property var appearanceValues: Core.appearance(folder || {})
    objectName: desktop
    required property var controller
    required property string desktop
    property var folder: null
    property string folderKey: ""
    property color foreground: Kirigami.Theme.textColor
    property string label: folder ? folder.name : (controller.state.apps[desktop]?.label || desktop)
    property var iconSource: controller.state.apps[desktop]?.icon || "application-x-executable"
    property bool showLabel: folderKey !== "" || (Core.contract.capabilities.plasma.dockLabels && !!folder?.showLabel)
    readonly property Item iconAnchor: icon
    property bool running: folder ? folder.apps.some(app => !!controller.taskSummary[app.desktop]) : !!controller.taskSummary[desktop]
    property bool windowActive: controller.taskSummary[desktop]?.active || false
    property bool hovered: mouse.containsMouse
    property bool inputEnabled: true
    property real slotSize: folderKey ? controller.popupIconSize : controller.iconSize
    property real iconSize: folder && !folderKey ? slotSize * controller.groupIconScale : slotSize
    readonly property real crossSpace: inputEnabled && Window.window
        ? controller.vertical ? Window.window.width : Window.window.height : slotSize + 12
    readonly property bool hoverActive: (controller.hoverSettings.rotate || (controller.hoverSettings.cards && (folder?.alwaysStack || folder?.apps.length > 5))) && !!folder && !folderKey && inputEnabled && hovered
        && !controller.dragging && !controller.folderVisible
    property real hoverProgress: hoverActive ? 1 : 0
    Behavior on hoverProgress { NumberAnimation { duration: controller.hoverDuration; easing.type: Easing.BezierSpline; easing.bezierCurve: Core.contract.layout.hoverBezier } }
    readonly property var miniatures: Geometry.miniIconLayout(iconSize, folder?.apps.length || 0,
        controller.groupMiniIconScale, crossSpace, controller.vertical, folder?.id || desktop, (folder?.iconRotation || 0) + orbit.angle + Core.hoverRotation(controller.preferences) * hoverProgress,
        folder?.alwaysStack || false, controller.hoverSettings.cards ? hoverProgress : 0, controller.hoverSettings.cards)
    readonly property real contentSize: folder && (controller.vertical || !inputEnabled) ? Math.max(slotSize, miniatures.height) : slotSize
    readonly property real bodySize: folder ? miniatures.bodySize : iconSize
    readonly property real iconTop: 3 + (contentSize - bodySize) / 2
    mainText: label
    location: Plasmoid.location
    active: inputEnabled && !showLabel && !controller.dragging && !controller.folderVisible
    interactive: false
    signal activated()
    implicitWidth: folderKey ? Core.contract.layout.cellWidth : folder ? miniatures.width : iconSize + Kirigami.Units.smallSpacing * 3
    implicitHeight: contentSize + (showLabel ? text.implicitHeight + 9 : 0) + 6
    Accessible.name: label
    Accessible.role: Accessible.Button
    Accessible.onPressAction: activated()
    activeFocusOnTab: inputEnabled
    Keys.onReturnPressed: activated()
    Keys.onSpacePressed: activated()
    OrbitalMotion {
        id: orbit
        objectName: "folder-orbital-motion"
        values: button.controller.preferences
        hovered: button.hovered
        hoverProgress: button.hoverProgress
        allowed: button.visible && button.enabled && button.inputEnabled && !!button.folder && !button.folderKey
            && !button.controller.dragging && (!button.Window.window || button.Window.window.visible)
    }

    Rectangle {
        anchors.fill: parent
        radius: Kirigami.Units.cornerRadius
        color: Kirigami.Theme.highlightColor
        opacity: drop.containsDrag ? .3 : mouse.containsMouse || button.activeFocus ? .13 : button.windowActive ? .08 : 0
        Behavior on opacity { NumberAnimation { duration: Kirigami.Units.shortDuration } }
    }
    Item {
        id: icon
        width: button.bodySize
        height: width
        x: (button.width - width) / 2
        y: button.iconTop
        property var dragImage: null
        Drag.dragType: Drag.Automatic
        Drag.supportedActions: Qt.MoveAction
        Drag.mimeData: ({"application/x-ubuntu-dock-folders-app": button.desktop,
                         "text/uri-list": "applications:" + button.desktop})
        Drag.hotSpot.x: width / 2
        Drag.hotSpot.y: height / 2
        Drag.onDragStarted: controller.dragging = true
        Drag.onDragFinished: {
            Qt.callLater(() => {
                x = Qt.binding(() => (button.width - width) / 2);
                y = Qt.binding(() => button.iconTop);
                controller.dragging = false;
                controller.refreshState();
            });
        }
        Rectangle {
            objectName: "folder-circle"
            visible: !!button.folder
            anchors.centerIn: parent
            width: parent.width * Core.contract.layout.circleScale
            height: width
            radius: width / 2
            color: button.appearanceValues.dockColor
            opacity: button.appearanceValues.dockOpacity
        }
        Kirigami.Icon {
            visible: !button.folder
            anchors.fill: parent
            anchors.margins: 3
            roundToIconSize: false
            source: button.iconSource
        }
        Repeater {
            model: button.miniatures.items.length
            delegate: Item {
                required property int index
                objectName: "folder-miniature-" + index
                readonly property var placement: button.miniatures.items[index] || {x:0,y:0,rotation:0}
                width: button.miniatures.size
                height: width
                x: placement.x
                y: placement.y
                rotation: placement.rotation
                opacity: placement.opacity ?? 1
                Rectangle {
                    anchors.fill: parent
                    visible: button.miniatures.cardOpacity > 0
                    opacity: button.miniatures.cardOpacity
                    color: button.appearanceValues.dockColor
                    radius: 4
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, .25)
                }
                Kirigami.Icon {
                    anchors.fill: parent
                    anchors.margins: button.miniatures.stacked ? 2 : 0
                    roundToIconSize: false
                    rotation: parent.placement.glyphRotation || 0
                    objectName: "folder-glyph-" + parent.index
                    source: controller.state.apps[button.folder?.apps[index]?.desktop]?.icon || "application-x-executable"
                }
            }
        }
    }
    Rectangle {
        visible: button.running
        width: button.windowActive ? 14 : 5
        height: 3
        radius: 2
        color: Kirigami.Theme.highlightColor
        anchors.horizontalCenter: parent.horizontalCenter
        y: button.contentSize + 3
    }
    QQC2.Label {
        id: text
        visible: button.showLabel
        anchors.horizontalCenter: parent.horizontalCenter
        y: button.contentSize + 9
        width: parent.width
        text: button.label
        color: button.foreground
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        maximumLineCount: button.folderKey ? 2 : 1
        wrapMode: button.folderKey ? Text.Wrap : Text.NoWrap
        font.pixelSize: button.folderKey ? Kirigami.Theme.defaultFont.pixelSize : controller.labelFontSize
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: button.inputEnabled
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        drag.target: controller.groupingEnabled ? icon : null
        drag.threshold: Kirigami.Units.gridUnit / 2
        onPressed: event => {
            button.hideImmediately();
            if (event.button === Qt.LeftButton && controller.groupingEnabled) {
                icon.grabToImage(result => { icon.dragImage = result; icon.Drag.imageSource = result.url; });
            }
        }
        onPositionChanged: event => {
            if (drag.active && (event.buttons & Qt.LeftButton) && !controller.dragging) {
                controller.dragging = true;
                icon.Drag.active = true;
            }
        }
        onClicked: event => {
            if (event.button === Qt.RightButton) {
                controller.openContextMenu(button);
            } else if (event.button === Qt.MiddleButton && !button.folder) {
                controller.activate(button.desktop, true);
            } else {
                button.activated();
            }
        }
        onEntered: if (!button.folder && button.running) hoverTimer.restart()
        onExited: hoverTimer.stop()
        onWheel: event => {
            if (!button.folder && button.running) {
                controller.cycle(button.desktop, event.angleDelta.y > 0 ? 1 : -1);
                event.accepted = true;
            } else event.accepted = false;
        }
    }
    Timer {
        id: hoverTimer
        interval: Core.contract.layout.previewDelay
        onTriggered: if (mouse.containsMouse && !controller.dragging) controller.showPreview(button)
    }
    DropArea {
        id: drop
        anchors.fill: parent
        enabled: button.inputEnabled && controller.groupingEnabled
        onDropped: event => {
            const desktop = controller.dragDesktop(event);
            if (!desktop || desktop === button.desktop) return;
            if (desktop.indexOf("local.groups.") === 0) controller.edit({operation: "reorder", desktop, before: button.desktop});
            else if (button.folderKey) controller.edit({operation: "move", desktop, key: button.folderKey, before: button.desktop});
            else if (button.folder) controller.edit({operation: "move", desktop, key: controller.groupKey(button.folder)});
            else controller.edit({operation: "create", desktop, target: button.desktop, name: i18nd("ubuntu-dock-folders", "New Folder")});
            event.acceptProposedAction();
        }
    }
}
