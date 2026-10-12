/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Toggle a feature from its label, switch, or keyboard. */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

QQC2.ItemDelegate {
    id: control
    property bool heading: false
    checkable: true
    Layout.fillWidth: true
    implicitHeight: Math.max(52,contentItem.implicitHeight+topPadding+bottomPadding)
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    contentItem: RowLayout {
        spacing: Kirigami.Units.largeSpacing
        QQC2.Label {
            text: control.text
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            font.pointSize: Kirigami.Theme.defaultFont.pointSize*(control.heading ? 1.2 : 1)
            font.bold: control.heading
        }
        QQC2.Switch {
            checked: control.checked
            onToggled: control.checked=checked
            focusPolicy: Qt.NoFocus
            Accessible.ignored: true
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
