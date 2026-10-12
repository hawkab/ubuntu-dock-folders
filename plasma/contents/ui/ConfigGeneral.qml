/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Configure grouping, dock appearance, and folder opening behavior. */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import "Core.js" as Core

KCM.SimpleKCM {
    id: globalSettings
    globalToolBarStyle:Kirigami.ApplicationHeaderStyle.None
    property bool cfg_enabledDefault: Core.defaultValue("enabled",true)
    property bool cfg_customizationDefault: Core.defaultValue("customization",true)
    property bool cfg_glassDefault: true
    property int cfg_animationDefault: Core.defaultValue("animation",true)
    property int cfg_animationSpeedDefault: Core.defaultValue("animationSpeed",true)
    property real cfg_fontSizeDefault: Core.defaultValue("fontSize",true)
    property int cfg_groupIconSizeDefault: Core.defaultValue("groupIconSize",true)
    property int cfg_groupMiniIconSizeDefault: Core.defaultValue("groupMiniIconSize",true)
    property int cfg_placementBefore: -1
    property int cfg_placementBeforeDefault: -1
    property int cfg_placementWidget: 0
    property int cfg_placementWidgetDefault: 0
    property alias cfg_enabled: grouping.checked
    property alias cfg_customization: customization.checked
    property bool cfg_glass: true
    property int cfg_blurStrengthDefault: Core.defaultValue("blurStrength",true)
    property int cfg_blurStrength: Core.defaultValue("blurStrength",true)
    property int cfg_animation: Core.defaultValue("animation",true)
    onCfg_animationChanged: {
        if (Core.animation(cfg_animation).id !== cfg_animation) cfg_animation = Core.animation(cfg_animation).id;
        applyValue("animation", cfg_animation);
    }
    property alias cfg_animationSpeed: openedTab.animationSpeed
    property real cfg_fontSize: Core.defaultValue("fontSize",true)
    property alias cfg_groupIconSize: dockTab.groupIconSize
    property alias cfg_groupMiniIconSize: dockTab.groupMiniIconSize
    property int cfg_hoverEffect: Core.defaultValue("hoverEffect",true)
    property int cfg_hoverEffectDefault: Core.defaultValue("hoverEffect",true)
    onCfg_hoverEffectChanged: applyValue("hoverEffect", cfg_hoverEffect)
    property alias cfg_popupIconSize: openedTab.popupIconSize
    property int cfg_popupIconSizeDefault: Core.defaultValue("popupIconSize",true)
    onCfg_popupIconSizeChanged: applyValue("popupIconSize", Math.round(cfg_popupIconSize))
    property alias cfg_hoverAngle: dockTab.hoverAngle
    property int cfg_hoverAngleDefault: Core.defaultValue("hoverAngle",true)
    onCfg_hoverAngleChanged: applyValue("hoverAngle",Math.round(cfg_hoverAngle))
    property alias cfg_hoverSpeed: dockTab.hoverSpeed
    property int cfg_hoverSpeedDefault: Core.defaultValue("hoverSpeed",true)
    onCfg_hoverSpeedChanged: applyValue("hoverSpeed",Math.round(cfg_hoverSpeed))
    property alias cfg_orbitSpeed: dockTab.orbitSpeed
    property int cfg_orbitSpeedDefault: Core.defaultValue("orbitSpeed",true)
    onCfg_orbitSpeedChanged: applyValue("orbitSpeed",Math.round(cfg_orbitSpeed))
    property alias cfg_hoverOrbitSpeed: dockTab.hoverOrbitSpeed
    property int cfg_hoverOrbitSpeedDefault: Core.defaultValue("hoverOrbitSpeed",true)
    onCfg_hoverOrbitSpeedChanged: applyValue("hoverOrbitSpeed",Math.round(cfg_hoverOrbitSpeed))
    property bool ready: false
    Component.onCompleted: {title="";Qt.callLater(() => ready = true);}
    function applyValue(key, value) {
        if (!ready || Plasmoid.configuration[key] === value) return;
        Plasmoid.configuration[key] = value;
        Plasmoid.configuration.writeConfig();
    }
    onCfg_enabledChanged: applyValue("enabled", cfg_enabled)
    onCfg_customizationChanged: applyValue("customization", cfg_customization)
    onCfg_animationSpeedChanged: applyValue("animationSpeed", Math.round(cfg_animationSpeed))
    onCfg_groupIconSizeChanged: applyValue("groupIconSize", Math.round(cfg_groupIconSize))
    onCfg_groupMiniIconSizeChanged: applyValue("groupMiniIconSize", Math.round(cfg_groupMiniIconSize))

    readonly property var previewValues: ({
        enabled:cfg_enabled,customization:cfg_customization,animation:cfg_animation,animationSpeed:cfg_animationSpeed,
        groupIconSize:cfg_groupIconSize,groupMiniIconSize:cfg_groupMiniIconSize,popupIconSize:cfg_popupIconSize,
        hoverEffect:cfg_hoverEffect,hoverAngle:cfg_hoverAngle,hoverSpeed:cfg_hoverSpeed,fontSize:cfg_fontSize,
        orbitSpeed:cfg_orbitSpeed,hoverOrbitSpeed:cfg_hoverOrbitSpeed
    })
    SettingsSample { id:sample }
    ColumnLayout {
        spacing:Kirigami.Units.largeSpacing
        ColumnLayout {
            Layout.fillWidth:true
            spacing:0
            FeatureSwitch {
                id:grouping;objectName:"grouping-enabled";heading:true
                text:i18nd("ubuntu-dock-folders","Dock folders")
            }
            FeatureSwitch {
                id:customization;objectName:"allow-folder-customization"
                enabled:grouping.checked
                text:i18nd("ubuntu-dock-folders","Allow customizing each folder separately")
            }
        }
        QQC2.TabBar {
            id:tabs
            objectName:"general-settings-tabs"
            Layout.fillWidth:true
            QQC2.TabButton { width:tabs.availableWidth/Math.max(1,tabs.count);text:i18nd("ubuntu-dock-folders","On the dock") }
            QQC2.TabButton { width:tabs.availableWidth/Math.max(1,tabs.count);text:i18nd("ubuntu-dock-folders","When opened") }
            QQC2.TabButton { width:tabs.availableWidth/Math.max(1,tabs.count);text:i18nd("ubuntu-dock-folders","Existing folders") }
        }
        StackLayout {
            currentIndex:tabs.currentIndex
            Layout.fillWidth:true
            Layout.fillHeight:false
            Layout.minimumHeight:0
            Layout.preferredHeight:currentIndex===0 ? dockTab.implicitHeight : currentIndex===1 ? openedTab.implicitHeight : existingFolders.implicitHeight
            GeneralDockSettings { id:dockTab;settings:globalSettings;apps:sample.apps }
            GeneralOpenedSettings { id:openedTab;settings:globalSettings;apps:sample.apps }
            ExistingFolders { id:existingFolders;objectName:"existing-folders-tab";groupingEnabled:grouping.checked }
        }
        QQC2.Label {
            text:i18nd("ubuntu-dock-folders","Changes are saved automatically")
            opacity:.7
            Layout.alignment:Qt.AlignHCenter
        }
    }
}
