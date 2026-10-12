/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.taskmanager as TaskManager
import org.kde.pipewire as PipeWire

PlasmaCore.Dialog {
    id: dialog
    required property var controller
    property var rows: []
    property var anchor: null
    type: PlasmaCore.Dialog.Tooltip
    hideOnWindowDeactivate: true
    backgroundHints: PlasmaCore.Dialog.StandardBackground
    onRowsChanged: if (!rows.length) visible = false
    mainItem: RowLayout {
        width: Math.max(260, implicitWidth)
        height: Math.max(200, implicitHeight)
        spacing: Kirigami.Units.largeSpacing
        Repeater {
            model: dialog.rows
            delegate: ColumnLayout {
                required property var modelData
                QQC2.Label {
                    text: modelData.title
                    Layout.preferredWidth: 220
                    elide: Text.ElideRight
                }
                Item {
                    Layout.preferredWidth: 220
                    Layout.preferredHeight: 140
                    Loader {
                        anchors.fill: parent
                        active: dialog.visible && modelData.ids.length > 0
                        sourceComponent: typeof modelData.ids[0] === "number" ? x11 : wayland
                    }
                    Component {
                        id: x11
                        PlasmaCore.WindowThumbnail { winId: modelData.ids[0] }
                    }
                    Component {
                        id: wayland
                        PipeWire.PipeWireSourceItem {
                            nodeId: capture.nodeId
                            TaskManager.ScreencastingRequest { id: capture; uuid: modelData.ids[0] }
                        }
                    }
                    TapHandler { onTapped: dialog.controller.activateWindow(modelData.ids) }
                }
                QQC2.ToolButton {
                    text: i18nd("ubuntu-dock-folders", "Close")
                    icon.name: "window-close"
                    Layout.alignment: Qt.AlignRight
                    onClicked: {
                        dialog.controller.closeWindow(modelData.ids);
                        dialog.visible = false;
                    }
                }
            }
        }
        HoverHandler {
            id: hover
            onHoveredChanged: {
                if (hovered || dialog.anchor?.hovered) hideTimer.stop();
                else hideTimer.restart();
            }
        }
    }
    property QtObject hoverConnection: Connections {
        target: dialog.anchor
        ignoreUnknownSignals: true
        function onHoveredChanged() {
            if (dialog.anchor.hovered || hover.hovered) hideTimer.stop();
            else hideTimer.restart();
        }
    }
    property Timer dismissalTimer: Timer {
        id: hideTimer
        interval: 350
        onTriggered: if (!hover.hovered && !dialog.anchor?.hovered) dialog.visible = false
    }
}
