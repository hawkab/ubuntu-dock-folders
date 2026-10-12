/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Display folder actions and draggable applications. */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import "Core.js" as Core

Item {
    id: content
    required property var controller
    required property var popup
    signal settingsRequested()
    readonly property int columns: Math.min(Core.contract.layout.maxColumns, controller.currentGroup?.apps.length || 1)
    readonly property int rows: Math.ceil((controller.currentGroup?.apps.length || 1) / columns)
    readonly property real cellHeight: controller.popupIconSize + 15 + metrics.lineSpacing * 2
    readonly property color foreground: Core.surface(controller.currentGroup, controller.blurStrength,
        Plasmoid.configuration.glass, popup.transition?.compositor?.background || null).foreground
    FontMetrics { id: metrics; font: Kirigami.Theme.defaultFont }
    width: Math.max(330, columns * 104 + (columns - 1) * Kirigami.Units.smallSpacing + 32)
    height: header.implicitHeight + rows * cellHeight + (rows - 1) * Kirigami.Units.largeSpacing + Kirigami.Units.largeSpacing + 32
    focus: true
    Keys.onEscapePressed: popup.close()
    Keys.onPressed: event => {
        if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_Z) controller.edit({operation: "undo"});
    }
    MaterialSurface {
        anchors.fill: parent
        group: controller.currentGroup
        blurStrength: controller.blurStrength
        legacyGlass: Plasmoid.configuration.glass
    }
    ColumnLayout {
        id: folderBody
        width: parent.width - 32
        anchors.centerIn: parent
        spacing: Kirigami.Units.largeSpacing
        RowLayout {
            id: header
            Layout.fillWidth: true
            QQC2.Label { text: controller.currentGroup?.name || ""; color: content.foreground; font.bold: true; font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.2; Layout.fillWidth: true; elide: Text.ElideRight }
            PlasmaComponents.ToolButton {
                Kirigami.Theme.inherit: false
                Kirigami.Theme.textColor: content.foreground
                icon.name: "edit-undo"
                visible: controller.state.undo
                text: i18nd("ubuntu-dock-folders", "Undo")
                display: QQC2.AbstractButton.IconOnly
                onClicked: controller.edit({operation: "undo"})
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
            }
            PlasmaComponents.ToolButton {
                Kirigami.Theme.inherit: false
                Kirigami.Theme.textColor: content.foreground
                icon.name: "configure"
                visible: Plasmoid.configuration.customization
                text: i18nd("ubuntu-dock-folders", "Folder settings")
                display: QQC2.AbstractButton.IconOnly
                onClicked: content.settingsRequested()
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
            }
        }
        GridLayout {
            Layout.alignment: Qt.AlignHCenter
            columns: content.columns
            rowSpacing: Kirigami.Units.largeSpacing
            columnSpacing: Kirigami.Units.smallSpacing
            Repeater {
                model: controller.currentGroup?.apps || []
                delegate: ApplicationIcon {
                    required property var modelData
                    controller: content.controller
                    desktop: modelData.desktop
                    label: modelData.label
                    foreground: content.foreground
                    folderKey: controller.currentKey
                    Layout.preferredHeight: content.cellHeight
                    onActivated: controller.activate(desktop)
                }
            }
        }
    }
}
