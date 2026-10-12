/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Paint one portable preview command using native Quick controls. */
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Item {
    id: item
    required property var command
    x:command.type==="circle" ? command.x-command.radius : command.x
    y:command.type==="circle" ? command.y-command.radius : command.y
    width:command.width || command.size || command.radius*2 || 1
    height:command.height || command.size || command.radius*2 || 24
    rotation:command.rotation || 0
    opacity:command.alpha ?? 1
    Rectangle {
        anchors.fill:parent
        visible:item.command.type==="round" || item.command.type==="circle"
        radius:item.command.radius || 0
        color:item.command.color || "transparent"
    }
    Kirigami.Icon {
        anchors.fill:parent
        visible:item.command.type==="icon"
        source:item.command.app?.icon || "application-x-executable"
        roundToIconSize:false
    }
    QQC2.Label {
        anchors.fill:parent
        visible:item.command.type==="text"
        text:item.command.value || ""
        textFormat:Text.PlainText
        color:item.command.color || "white"
        font.pixelSize:item.command.size || 13
        elide:Text.ElideRight
        horizontalAlignment:Text.AlignHCenter
    }
}
