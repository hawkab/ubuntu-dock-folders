/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.workspace.dbus as DBus
import org.kde.taskmanager as TaskManager
import "Core.js" as Core
import "FolderInteraction.js" as Folders

PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    LayoutMirroring.enabled: Qt.application.layoutDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true
    property var state: ({groups: {}, favorites: [], apps: {}, aliases: {}, undo: false})
    property var taskSummary: ({})
    property var taskIndex: ({})
    readonly property var folderIndex: indexFolders(state.groups)
    property bool dragging: false
    property bool groupingEnabled: Plasmoid.configuration.enabled
    readonly property var groupedApps: groupingEnabled ? Core.groupedDesktops(state.groups,state.favorites) : []
    readonly property bool folderVisible: popup.visible
    property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    property int iconSize: Math.max(24, Math.min(64, (vertical ? width : height) - 6))
    readonly property var preferences: Core.preferences(item => Plasmoid.configuration[item.name], Plasmoid.configuration.glass)
    readonly property int blurStrength: preferences.blurStrength
    readonly property int popupIconSize: preferences.popupIconSize
    property real groupIconScale: preferences.groupIconSize / 100
    readonly property var hoverSettings: Core.hoverEffect(preferences.hoverEffect)
    readonly property int hoverAngle: preferences.hoverAngle
    readonly property int hoverDuration: Core.hoverDuration(preferences.hoverSpeed)
    readonly property int hoverEffect: Core.hoverEffect(preferences.hoverEffect).id
    property real groupMiniIconScale: preferences.groupMiniIconSize / 100
    readonly property int animationMode: Core.animation(preferences.animation).id
    property alias taskModel: tasks
    property int labelFontSize: Plasmoid.configuration.fontSize
    property string currentKey: ""
    property var currentGroup: state.groups[currentKey] || null
    property string serviceError: ""
    property var contextTarget: null
    property var taskDelegateModel: null
    property var dockFavorites: []
    readonly property string bus: "io.github.hawkab.DockFolders.Plasma"
    readonly property string path: "/io/github/hawkab/DockFolders"
    Layout.minimumWidth: vertical ? 40 : 100
    Layout.minimumHeight: vertical ? 100 : 40
    Layout.preferredWidth: vertical ? 48 : 600
    Layout.preferredHeight: vertical ? 600 : 48
    Layout.fillWidth: !vertical
    Layout.fillHeight: vertical

    function rpc(member, args, done) {
        const reply = DBus.SessionBus.asyncCall({service: bus, path, iface: bus, member, arguments: args});
        function finished() {
            if (reply.isError) serviceError = reply.error.message;
            else { serviceError = ""; if (done) done(reply.value); }
        }
        if (reply.isFinished) finished(); else reply.finished.connect(finished);
    }
    function refreshState() {
        if (dragging) return;
        const value = properties.properties.State;
        if (!value) return;
        let next;
        try { next = JSON.parse(value); }
        catch (error) { serviceError = error.message; return; }
        if (JSON.stringify(next) !== JSON.stringify(state)) state = next;
        updateFavorites();
        if (currentKey && !currentGroup) {
            popup.visible = false;
            folderSettings.visible = false;
            preview.visible = false;
            currentKey = "";
        }
        updateTasks.restart();
    }
    function edit(request) { rpc("Edit", [JSON.stringify(request)]); }
    function scheduleTasks() { updateTasks.restart(); }
    function groupKey(group) { return group ? Object.keys(state.groups).find(key => state.groups[key].id === group.id) || "" : ""; }
    function indexFolders(groups) {
        const result = Object.create(null);
        for (const group of Object.values(groups)) result[group.id + ".desktop"] = group;
        return result;
    }
    function groupFor(desktop) { return folderIndex[desktop] || null; }
    function canonical(value) {
        return Core.canonicalDesktop(String(value || ""),state.aliases);
    }
    function grouped(desktop) {
        return groupedApps.includes(desktop);
    }
    function dragDesktop(event) {
        if (event.formats.indexOf("application/x-ubuntu-dock-folders-app") >= 0)
            return canonical(event.getDataAsString("application/x-ubuntu-dock-folders-app"));
        return event.urls.length === 1 ? canonical(event.urls[0]) : "";
    }
    function taskRows(desktop) {
        return taskIndex[desktop] || [];
    }
    function activate(desktop, newInstance = false) {
        const rows = taskRows(desktop);
        const decision = Core.activation(rows,newInstance);
        const item = rows[decision.index] || rows[0];
        if (item) {
            const index = tasks.makeModelIndex(item.row);
            if (decision.action === "launch") tasks.requestNewInstance(index);
            else if (decision.action === "minimize") tasks.requestToggleMinimized(index);
            else tasks.requestActivate(index);
        } else rpc("Launch", [desktop]);
        popup.close();
        preview.visible = false;
    }
    function cycle(desktop, direction) {
        const rows = taskRows(desktop).filter(row => row.running);
        if (!rows.length) return;
        tasks.requestActivate(tasks.makeModelIndex(rows[Core.cycleWindow(rows,direction)].row));
    }
    function windowRow(ids) {
        for (let row = 0; row < (taskDelegateModel?.count || 0); row++) {
            const item = taskDelegateModel.itemAt(row);
            if (item?.running && item.ids.some(id => ids.indexOf(id) >= 0)) return row;
        }
        return -1;
    }
    function closeWindow(ids) {
        const row = windowRow(ids);
        if (row >= 0) tasks.requestClose(tasks.makeModelIndex(row));
    }
    function activateWindow(ids) {
        const row = windowRow(ids);
        if (row >= 0) tasks.requestActivate(tasks.makeModelIndex(row));
        popup.close();
        preview.visible = false;
    }
    function openFolder(desktop, anchor) {
        Folders.activate(root, popup, desktop, anchor);
    }
    function folderPress(point) { return Folders.press(root, popup, point); }
    function showPreview(anchor) {
        preview.visualParent = anchor;
        preview.anchor = anchor;
        preview.rows = taskRows(anchor.desktop).filter(row => row.running).slice(0, Core.contract.layout.maxPreviews)
            .map(row => ({desktop: row.desktop, title: row.title, ids: Array.from(row.ids)}));
        Qt.callLater(() => preview.visible = preview.rows.length > 0 && !root.dragging);
    }
    function openContextMenu(target) { contextTarget = target; contextMenu.popup(target); }
    function appearance(name, value) { edit({operation: "appearance", key: currentKey, property: name, value}); }
    function favorites() {
        return groupingEnabled ? state.favorites : Core.expandedFavorites(state.groups,state.favorites);
    }
    function updateFavorites() {
        const next = favorites();
        if (JSON.stringify(next) !== JSON.stringify(dockFavorites)) dockFavorites = next;
    }
    onGroupingEnabledChanged: updateFavorites()
    DBus.Properties {
        id: properties
        service: root.bus
        path: root.path
        iface: root.bus
        onPropertiesChanged: root.refreshState()
        onRefreshed: root.refreshState()
    }
    TaskManager.TasksModel {
        id: tasks
        groupMode: TaskManager.TasksModel.GroupDisabled
        sortMode: TaskManager.TasksModel.SortManual
        filterByVirtualDesktop: false
        filterByScreen: false
        launcherList: {
            const launchers = Core.expandedFavorites(root.state.groups,root.state.favorites);
            return Array.from(new Set(launchers)).map(desktop => "applications:" + desktop);
        }
        onDataChanged: updateTasks.restart()
        onCountChanged: updateTasks.restart()
    }
    Timer {
        id: updateTasks
        interval: 0
        onTriggered: {
            const summary = {};
            const index = Object.create(null);
            for (let row = 0; row < (root.taskDelegateModel?.count || 0); row++) {
                const item = root.taskDelegateModel.itemAt(row);
                if (item) {
                    if (!index[item.desktop]) index[item.desktop] = [];
                    index[item.desktop].push(item);
                }
                if (item && item.running) {
                    const state = summary[item.desktop] || {active: false, count: 0};
                    state.count++;
                    state.active = state.active || item.active;
                    summary[item.desktop] = state;
                }
            }
            root.taskSummary = summary;
            root.taskIndex = index;
            if (preview.visible && preview.rows.some(row => root.windowRow(row.ids) < 0)) preview.visible = false;
        }
    }
    fullRepresentation: DockStrip { controller: root }
    FolderPopup {
        id: popup
        controller: root
        settingsVisible: folderSettings.visible
        previewVisible: preview.visible
        onSettingsRequested: folderSettings.show()
    }
    WindowPreview { id: preview; controller: root; location: Plasmoid.location }
    FolderSettings { id: folderSettings; controller: root }
    QQC2.Menu {
        id: contextMenu
        QQC2.MenuItem {
            text: i18nd("ubuntu-dock-folders", "Pin to dock")
            checkable: true
            checked: root.contextTarget && root.state.favorites.indexOf(root.contextTarget.desktop) >= 0
            visible: root.contextTarget && !root.contextTarget.folder && !root.contextTarget.folderKey
            onTriggered: root.edit({operation: "pin", desktop: root.contextTarget.desktop})
        }
        QQC2.MenuItem {
            text: i18nd("ubuntu-dock-folders", "Folder settings")
            visible: !!root.contextTarget?.folder
            onTriggered: { root.currentKey = root.groupKey(root.contextTarget.folder); folderSettings.show(); }
        }
        QQC2.MenuItem {
            text: i18nd("ubuntu-dock-folders", "General folder settings")
            onTriggered: Plasmoid.internalAction("configure").trigger()
        }
    }
    PanelPlacement { applet: root }
    Component.onCompleted: {
        properties.updateAll();
        if (Plasmoid.configuration.blurStrength < 0) {
            Plasmoid.configuration.blurStrength = root.blurStrength;
            Plasmoid.configuration.writeConfig();
        }
        Plasmoid.configuration.animation = Core.animation(Plasmoid.configuration.animation).id;
    }
}
