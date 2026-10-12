/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Select saved groups and source folders using the common folder API. */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.workspace.dbus as DBus

ColumnLayout {
    id: selector
    spacing:Kirigami.Units.largeSpacing
    property var folders: []
    property bool pending: false
    property bool groupingEnabled: true
    property string error: ""
    readonly property string bus: "io.github.hawkab.DockFolders.Plasma"
    readonly property string path: "/io/github/hawkab/DockFolders"
    function request(member, args, done) {
        pending=true;
        const reply = DBus.SessionBus.asyncCall({service:bus, path, iface:bus, member, arguments:args});
        function finished() {
            pending=false;
            error=reply.isError ? reply.error.message : "";
            if (!reply.isError) done(reply.value);
        }
        if (reply.isFinished) finished(); else reply.finished.connect(finished);
    }
    function reload() {
        if(pending || !visible)return;
        request("ListFolders", [], value => {
            try { folders=JSON.parse(String(value)); }
            catch (exception) { error=exception.message; }
        });
    }
    function pin(id, value) {
        pending=true;
        request("PinFolder", [id,value], () => reload());
    }
    onVisibleChanged:if(visible)reload()
    Component.onCompleted:if(visible)reload()
    DBus.Properties {
        service:selector.bus; path:selector.path; iface:selector.bus
        onPropertiesChanged: if (selector.visible) refresh.restart()
    }
    Timer { id:refresh; interval:50; onTriggered:selector.reload() }
    ColumnLayout {
        Layout.fillWidth:true
        QQC2.Label {
            text:i18nd("ubuntu-dock-folders", "Choose saved groups or folders from GNOME's app grid")
            wrapMode:Text.WordWrap
            Layout.fillWidth:true
            opacity:.7
        }
        Kirigami.InlineMessage { visible:selector.error.length>0; text:selector.error; type:Kirigami.MessageType.Error; Layout.fillWidth:true }
        QQC2.Label {
            visible:!selector.pending && !selector.folders.length && !selector.error.length
            text:i18nd("ubuntu-dock-folders", "No folders available")
            Layout.fillWidth:true
        }
        QQC2.BusyIndicator { visible:selector.pending && !selector.folders.length;running:visible;Layout.alignment:Qt.AlignHCenter }
        QQC2.ScrollView {
            Layout.fillWidth:true; Layout.preferredHeight:360
            contentWidth:availableWidth
            ColumnLayout {
                width:parent.width
                Repeater {
                    model:selector.folders
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth:true
                        Kirigami.Icon { source:"folder"; implicitWidth:32; implicitHeight:32 }
                        ColumnLayout {
                            Layout.fillWidth:true
                            QQC2.Label { text:modelData.name; textFormat:Text.PlainText; elide:Text.ElideRight; Layout.fillWidth:true }
                            QQC2.Label {
                                text:modelData.apps.slice(0,3).map(app => app.label).join(" · ")
                                textFormat:Text.PlainText; elide:Text.ElideRight; opacity:.7; Layout.fillWidth:true
                            }
                        }
                        QQC2.Button {
                            objectName:modelData.id
                            checkable:true; checked:modelData.pinned
                            enabled:!selector.pending && ((modelData.enabled && selector.groupingEnabled) || modelData.pinned)
                            text:modelData.pinned ? i18nd("ubuntu-dock-folders", "Pinned") : i18nd("ubuntu-dock-folders", "Pin to panel")
                            QQC2.ToolTip.text:modelData.pinned ? i18nd("ubuntu-dock-folders", "Unpin from panel") : i18nd("ubuntu-dock-folders", "Pin to panel")
                            QQC2.ToolTip.visible:hovered
                            onClicked:selector.pin(modelData.id,!modelData.pinned)
                        }
                    }
                }
            }
        }
    }
}
