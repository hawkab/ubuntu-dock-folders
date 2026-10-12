/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Edit a folder's appearance with autosaving dock and popup tabs. */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.kquickcontrols as KQuickControls
import "Core.js" as Core

Kirigami.ApplicationWindow {
    id: window
    required property var controller
    property string subjectKey: ""
    readonly property var group: controller.state.groups[subjectKey] || null
    readonly property var appearanceValues: Core.surface(group || {},controller.blurStrength,Plasmoid.configuration.glass)
    title: i18nd("ubuntu-dock-folders", "Folder appearance") + (group ? " — " + group.name : "")
    width: 540
    height: 600
    minimumWidth: 440
    minimumHeight: 480
    visible: false
    LayoutMirroring.enabled: Qt.application.layoutDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true
    function show() {
        subjectKey = controller.currentKey;
        nameField.text = group?.name || "";
        visible = true; raise(); requestActivate();
    }
    function appearance(property, value) {
        controller.edit({operation: "appearance", key: subjectKey, property, value});
    }
    function saveName() {
        nameSave.stop();
        if (group && nameField.text.trim() && nameField.text !== group.name) appearance("name", nameField.text);
    }
    onVisibleChanged: if (!visible) { saveName(); applyConfirmation.close(); }
    onGroupChanged: if (!group && visible) visible = false
    Timer { id: nameSave; interval: 180; onTriggered: window.saveName() }
    pageStack.initialPage: Kirigami.ScrollablePage {
        title: window.title
        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing
            Kirigami.FormLayout {
                Layout.fillWidth: true
                QQC2.TextField {
                    Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Name")
                    id: nameField
                    maximumLength: Core.contract.appearancePreferences.find(item => item.name === "name").maxLength
                    onTextEdited: nameSave.restart()
                    onEditingFinished: window.saveName()
                }
            }
            QQC2.TabBar {
                id: tabs
                Layout.fillWidth: true
                QQC2.TabButton { text: i18nd("ubuntu-dock-folders", "On the dock") }
                QQC2.TabButton { text: i18nd("ubuntu-dock-folders", "When opened") }
            }
            StackLayout {
                currentIndex: tabs.currentIndex
                Layout.fillWidth: true
                Kirigami.FormLayout {
                    ApplicationIcon {
                        controller: window.controller
                        desktop: window.group?.id + ".desktop"
                        folder: window.group
                        slotSize: 72
                        inputEnabled: false
                        implicitHeight: Math.max(100, contentSize + 6)
                    }
                    RowLayout {
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Icon rotation")
                        QQC2.Slider {
                            id: rotation
                            objectName: "icon-rotation"
                            from: 0; to: Core.contract.appearancePreferences.find(item => item.name === "iconRotation").range[1]; stepSize: 1
                            snapMode: QQC2.Slider.SnapAlways
                            value: window.group?.iconRotation || 0
                            Layout.fillWidth: true
                            onMoved: window.appearance("iconRotation", Math.round(value) % 360)
                        }
                        QQC2.Label { text: Math.round(rotation.value) + "°"; Layout.minimumWidth: 40 }
                    }
                    QQC2.CheckBox {
                        text: i18nd("ubuntu-dock-folders", "Always use card stack")
                        checked: window.group?.alwaysStack || false
                        onToggled: window.appearance("alwaysStack", checked)
                    }
                    KQuickControls.ColorButton {
                        objectName: "dock-background-color"
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Background color")
                        dialogTitle: i18nd("ubuntu-dock-folders", "Background color")
                        showAlphaChannel: false
                        color: window.appearanceValues.dockColor
                        onAccepted: selected => window.appearance("dockColor", selected.toString())
                    }
                    RowLayout {
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Transparency")
                        QQC2.Slider {
                            id: dockOpacity
                            from: 0
                            to: 100
                            stepSize: 1
                            value: (1 - window.appearanceValues.dockOpacity) * 100
                            onMoved: window.appearance("dockOpacity", 1 - value / 100)
                            Layout.fillWidth: true
                        }
                        QQC2.Label { text: Math.round(dockOpacity.value) + "%" }
                    }

                }
                Kirigami.FormLayout {
                    FolderPreview {
                        id: openedPreview
                        objectName: "open-folder-preview"
                        Kirigami.FormData.isSection: true
                        Layout.fillWidth: true
                        controller: window.controller
                        group: window.group
                        blurStrength: popupBlur.value
                        legacyGlass: Plasmoid.configuration.glass
                        transparency: popupOpacity.value
                    }
                    KQuickControls.ColorButton {
                        objectName: "popup-background-color"
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Background color")
                        dialogTitle: i18nd("ubuntu-dock-folders", "Background color")
                        showAlphaChannel: false
                        color: window.appearanceValues.popupColor
                        onAccepted: selected => window.appearance("popupColor", selected.toString())
                    }
                    RowLayout {
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Transparency")
                        QQC2.Slider {
                            id: popupOpacity
                            objectName: "popup-transparency"
                            from: 0
                            to: 100
                            stepSize: 1
                            value: (1 - Core.surface(window.group, window.controller.blurStrength, Plasmoid.configuration.glass).backgroundOpacity) * 100
                            onMoved: window.appearance("backgroundOpacity", 1 - value / 100)
                            Layout.fillWidth: true
                        }
                        QQC2.Label { text: Math.round(popupOpacity.value) + "%" }
                    }
                    RowLayout {
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Background blur")
                        QQC2.Slider {
                            id: popupBlur
                            objectName: "folder-background-blur"
                            from: 0; to: 100; stepSize: 1
                            snapMode: QQC2.Slider.SnapAlways
                            Layout.fillWidth: true
                            value: Core.surface(window.group, window.controller.blurStrength, Plasmoid.configuration.glass).blurStrength
                            onMoved: window.appearance("blurStrength", Math.round(value))
                        }
                        QQC2.Label { text: Math.round(popupBlur.value) + "%"; Layout.minimumWidth: 40 }
                    }
                    QQC2.Label {
                        text: i18nd("ubuntu-dock-folders", "Transparency affects the background color; blur is independent.")
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        Kirigami.FormData.label: i18nd("ubuntu-dock-folders", "Wallpaper")
                        QQC2.Button {
                            text: window.group?.wallpaper ? i18nd("ubuntu-dock-folders", "Replace…") : i18nd("ubuntu-dock-folders", "Choose…")
                            icon.name: "folder-pictures"
                            onClicked: wallpaper.open()
                        }
                        QQC2.ToolButton {
                            visible: !!window.group?.wallpaper
                            icon.name: "edit-delete"
                            text: i18nd("ubuntu-dock-folders", "Remove wallpaper")
                            display: QQC2.AbstractButton.IconOnly
                            onClicked: controller.rpc("Wallpaper", [window.subjectKey, ""])
                        }
                    }
                    QQC2.Label {
                        text: window.group?.wallpaperName || "PNG, JPEG, BMP, WebP, GIF, SVG"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
            QQC2.Button {
                objectName: "apply-appearance-to-all"
                Layout.alignment: Qt.AlignHCenter
                text: i18nd("ubuntu-dock-folders", "Apply to all folders…")
                icon.name: "edit-copy"
                onClicked: applyConfirmation.open()
            }
            QQC2.Button {
                Layout.alignment: Qt.AlignHCenter
                text: i18nd("ubuntu-dock-folders", "General folder settings")
                icon.name: "configure"
                onClicked: Plasmoid.internalAction("configure").trigger()
            }
            QQC2.Label {
                Layout.alignment: Qt.AlignHCenter
                text: i18nd("ubuntu-dock-folders", "Changes are saved automatically")
                opacity: .65
            }
        }
    }
    Kirigami.PromptDialog {
        id: applyConfirmation
        objectName: "apply-appearance-confirmation"
        parent: QQC2.Overlay.overlay
        title: i18nd("ubuntu-dock-folders", "Replace other folders’ appearance?")
        subtitle: i18nd("ubuntu-dock-folders", "This will overwrite the custom appearance settings of all other folders. Names and applications will stay the same.")
        dialogType: Kirigami.PromptDialog.Warning
        standardButtons: Kirigami.Dialog.Cancel
        onOpened: standardButton(Kirigami.Dialog.Cancel).forceActiveFocus()
        customFooterActions: [Kirigami.Action {
            text: i18nd("ubuntu-dock-folders", "Apply to all folders")
            icon.name: "edit-copy"
            onTriggered: {
                window.controller.edit({operation:"applyAppearance", key:window.subjectKey,
                    blurStrength:window.controller.blurStrength, legacyGlass:Plasmoid.configuration.glass});
                applyConfirmation.close();
            }
        }]
    }
    FileDialog {
        id: wallpaper
        title: i18nd("ubuntu-dock-folders", "Folder wallpaper")
        nameFilters: ["PNG, JPEG, BMP, WebP, GIF, SVG (*.png *.PNG *.jpg *.JPG *.jpeg *.JPEG *.bmp *.BMP *.webp *.WEBP *.gif *.GIF *.svg *.SVG)", i18nd("ubuntu-dock-folders", "All files") + " (*)"]
        onAccepted: controller.rpc("Wallpaper", [window.subjectKey, selectedFile.toString()])
    }
}
