/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Configure group geometry and hover effects with a live preview. */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "Core.js" as Core

ColumnLayout {
    required property var settings
    required property var apps
    property alias groupIconSize:folderSize.value
    property alias groupMiniIconSize:miniSize.value
    property alias hoverAngle:angle.value
    property alias hoverSpeed:speed.value
    property alias orbitSpeed:orbitControl.value
    property alias hoverOrbitSpeed:hoverOrbitControl.value
    spacing:Kirigami.Units.largeSpacing
    SettingsPreview { objectName:"dock-settings-preview";values:settings.previewValues;apps:parent.apps;Layout.fillWidth:true }
    Kirigami.FormLayout {
        Layout.fillWidth:true
        enabled:settings.cfg_enabled
        SettingSlider { id:folderSize;preference:"groupIconSize" }
        SettingSlider { id:miniSize;preference:"groupMiniIconSize" }
    }
    Kirigami.Heading { text:i18nd("ubuntu-dock-folders","Icon rotation");level:3 }
    QQC2.Label {
        text:i18nd("ubuntu-dock-folders","0 disables each mode. A nonzero hover speed replaces continuous speed while hovered. Negative speeds reverse rotation.")
        wrapMode:Text.Wrap;Layout.fillWidth:true;opacity:.7
    }
    Kirigami.FormLayout {
        Layout.fillWidth:true
        enabled:settings.cfg_enabled
        SettingSlider { id:orbitControl;preference:"orbitSpeed";suffix:" °/s" }
        SettingSlider { id:hoverOrbitControl;preference:"hoverOrbitSpeed";suffix:" °/s" }
    }
    Kirigami.Heading { text:i18nd("ubuntu-dock-folders","On hover");level:3 }
    Kirigami.FormLayout {
        Layout.fillWidth:true
        enabled:settings.cfg_enabled
        QQC2.CheckBox {
            text:i18nd("ubuntu-dock-folders","Rotate on hover")
            checked:Core.hoverEffect(settings.cfg_hoverEffect).rotate
            onClicked:settings.cfg_hoverEffect=Core.hoverChoice(checked,Core.hoverEffect(settings.cfg_hoverEffect).cards).id
        }
        QQC2.CheckBox {
            text:i18nd("ubuntu-dock-folders","Fan out cards")
            checked:Core.hoverEffect(settings.cfg_hoverEffect).cards
            onClicked:settings.cfg_hoverEffect=Core.hoverChoice(Core.hoverEffect(settings.cfg_hoverEffect).rotate,checked).id
        }
        SettingSlider { id:angle;preference:"hoverAngle";suffix:"°";visible:Core.hoverEffect(settings.cfg_hoverEffect).rotate }
        SettingSlider { id:speed;preference:"hoverSpeed";visible:settings.cfg_hoverEffect!==0 }
    }
}
