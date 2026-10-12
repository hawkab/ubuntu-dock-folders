/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Bind one native slider to the shared preference range. */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "Core.js" as Core

RowLayout {
    id: row
    required property string preference
    property string suffix: "%"
    property alias value: slider.value
    Kirigami.FormData.label: i18nd("ubuntu-dock-folders",Core.preference(preference).label)
    QQC2.Slider {
        id: slider
        objectName:row.preference
        from:Core.preference(row.preference).range[0];to:Core.preference(row.preference).range[1]
        stepSize:Core.preference(row.preference).range[2]
        snapMode:QQC2.Slider.SnapAlways
        Layout.fillWidth:true
        Layout.minimumWidth:150
    }
    QQC2.Label { text:Math.round(slider.value)+row.suffix; Layout.minimumWidth:48; horizontalAlignment:Text.AlignRight }
}
