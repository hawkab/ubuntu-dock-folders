/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Configure opening animations and application size without changing folder appearance. */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "Core.js" as Core

ColumnLayout {
    required property var settings
    required property var apps
    property alias popupIconSize:iconSize.value
    property alias animationSpeed:speed.value
    spacing:Kirigami.Units.largeSpacing
    SettingsPreview { id:preview;objectName:"opened-settings-preview";mode:"popup";values:settings.previewValues;apps:parent.apps;Layout.fillWidth:true }
    QQC2.Button {
        objectName:"preview-animation"
        text:i18nd("ubuntu-dock-folders","Preview animation")
        icon.name:"media-playback-start"
        Layout.alignment:Qt.AlignHCenter
        enabled:settings.cfg_enabled && Core.animation(settings.cfg_animation).key!=="none"
        onClicked:preview.replay()
    }
    Kirigami.FormLayout {
        Layout.fillWidth:true
        enabled:settings.cfg_enabled
        SettingSlider { id:iconSize;preference:"popupIconSize";suffix:" px" }
        QQC2.ComboBox {
            Kirigami.FormData.label:i18nd("ubuntu-dock-folders","Opening and closing animation")
            textRole:"label";valueRole:"value"
            model:Core.contract.animations.map(item=>({label:i18nd("ubuntu-dock-folders",item.label),value:item.id}))
            currentIndex:model.findIndex(item=>item.value===settings.cfg_animation)
            onActivated:settings.cfg_animation=currentValue
        }
        SettingSlider { id:speed;preference:"animationSpeed";enabled:Core.animation(settings.cfg_animation).key!=="none" }
    }
}
