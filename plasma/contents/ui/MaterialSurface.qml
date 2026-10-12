/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Paint the folder's tint, frosted wallpaper, border, and shadow. */

import QtQuick
import QtQuick.Effects
import org.kde.kirigami as Kirigami
import "Core.js" as Core

Item {
    id: surface
    required property var group
    required property int blurStrength
    property bool legacyGlass: true
    readonly property bool glass: appearance.glass
    property Item backdropSource: null
    readonly property var appearance: Core.surface(group, blurStrength, legacyGlass)
    readonly property real tintOpacity: appearance.backgroundOpacity
    readonly property real cornerRadius: Core.contract.layout.radius
    Kirigami.ShadowedRectangle {
        anchors.fill: parent
        radius: surface.cornerRadius
        color: "transparent"
        shadow.size: Core.contract.layout.shadowSize
        shadow.yOffset: 5
        shadow.color: Qt.rgba(0, 0, 0, .28 * Math.min(1, surface.tintOpacity * 3))
    }
    MultiEffect {
        anchors.fill: parent
        source: surface.backdropSource
        visible: !!source && surface.glass
        autoPaddingEnabled: false
        blurEnabled: true
        blurMax: Core.contract.layout.blurRadius
        blur: surface.appearance.blurAmount
        opacity: 1
        maskEnabled: true
        maskSource: mask
    }
    Rectangle {
        anchors.fill: parent
        radius: surface.cornerRadius
        color: surface.appearance.popupColor
        opacity: surface.tintOpacity
    }
    Image {
        id: wallpaper
        anchors.fill: parent
        source: surface.group?.wallpaper ? "file://" + surface.group.wallpaper : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio))
        visible: false
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: surface.cornerRadius
        layer.enabled: true
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        source: wallpaper
        visible: !!wallpaper.source
        autoPaddingEnabled: false
        maskEnabled: true
        maskSource: mask
        blurEnabled: surface.glass
        blurMax: Core.contract.layout.blurRadius
        blur: .65 * surface.appearance.blurAmount
        saturation: -.15 * surface.appearance.blurAmount
        opacity: surface.tintOpacity * (1 - .2 * surface.appearance.blurAmount)
    }
    Rectangle {
        anchors.fill: parent
        radius: surface.cornerRadius
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, (.08 + .22 * surface.appearance.blurAmount) * surface.tintOpacity)
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(1, 1, 1, (.02 + .18 * surface.appearance.blurAmount) * surface.tintOpacity) }
            GradientStop { position: .6; color: "transparent" }
        }
    }
}
