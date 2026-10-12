/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Preview the open folder against a cached sample desktop. */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "Core.js" as Core

Item {
    id: preview
    required property var controller
    required property var group
    required property int blurStrength
    property bool legacyGlass: true
    required property real transparency
    readonly property var surfaceGroup: Object.assign({}, group, {
        backgroundOpacity: 1 - transparency / 100,
        blurStrength: preview.blurStrength
    })
    readonly property var apps: group?.apps.slice(0, 4) || []
    readonly property color foreground: Core.surface(surfaceGroup, blurStrength, legacyGlass, "#49374c").foreground
    implicitHeight: 176
    Accessible.name: i18nd("ubuntu-dock-folders", "Open folder preview")
    Accessible.role: Accessible.StaticText
    clip: true
    onVisibleChanged: if (visible) Qt.callLater(() => sample.scheduleUpdate())

    Rectangle {
        id: backdrop
        anchors.fill: parent
        radius: 16
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#294f60" }
            GradientStop { position: .5; color: "#49374c" }
            GradientStop { position: 1; color: "#68405a" }
        }
        Rectangle {
            x: parent.width * .06; y: parent.height * .28
            width: parent.height * .72; height: width; radius: width / 2
            color: "#a15f75"
            opacity: .5
        }
        Rectangle {
            x: parent.width * .52; y: 22
            width: parent.width * .42; height: parent.height * .72
            radius: 12
            color: "#9bb8c9"
            opacity: .3
            Column {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                Repeater {
                    model: 5
                    Rectangle { width: parent.width * .9; height: 3; color: "#e1e6e8"; radius: 1 }
                }
            }
        }
    }
    ShaderEffectSource {
        id: sample
        sourceItem: backdrop
        sourceRect: Qt.rect(card.x, card.y, card.width, card.height)
        textureSize: Qt.size(Math.max(1, Math.ceil(card.width * Screen.devicePixelRatio)), Math.max(1, Math.ceil(card.height * Screen.devicePixelRatio)))
        live: false
        visible: false
        onSourceRectChanged: scheduleUpdate()
        onTextureSizeChanged: scheduleUpdate()
        Component.onCompleted: scheduleUpdate()
    }
    Item {
        id: card
        anchors.fill: parent
        anchors.margins: 14
        MaterialSurface {
            id: surface
            anchors.fill: parent
            group: preview.surfaceGroup
            blurStrength: preview.blurStrength
            legacyGlass: preview.legacyGlass
            backdropSource: sample
        }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 12
            QQC2.Label {
                text: preview.group?.name || ""
                font.bold: true
                color: preview.foreground
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8
                Repeater {
                    model: preview.apps
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 0
                        spacing: 8
                        Kirigami.Icon {
                            source: preview.controller.state.apps[modelData.desktop]?.icon || "application-x-executable"
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 40
                            Layout.preferredHeight: 40
                            roundToIconSize: false
                        }
                        QQC2.Label {
                            text: modelData.label.replace(/\n/g, " ")
                            color: preview.foreground
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }
}
