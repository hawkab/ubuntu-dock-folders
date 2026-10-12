/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Read example applications without changing folders or favorites. */
import QtQuick
import org.kde.plasma.workspace.dbus as DBus

QtObject {
    id: sample
    property var state:({groups:{},apps:{}})
    readonly property var apps: {
        const group=Object.values(state.groups).find(item=>item.apps.length);
        return group ? group.apps.map(app=>Object.assign({},app,{icon:state.apps[app.desktop]?.icon || "application-x-executable"}))
            : ["applications-internet","system-file-manager","utilities-terminal"].map(icon=>({icon,desktop:icon,label:""}));
    }
    function read() {
        try {
            const value=JSON.parse(properties.properties.State || "{}");
            if(value.groups && value.apps)state=value;
        }catch(_exception){}
    }
    property DBus.Properties properties: DBus.Properties {
        service:"io.github.hawkab.DockFolders.Plasma"
        path:"/io/github/hawkab/DockFolders"
        iface:service
        onRefreshed:sample.read()
        onPropertiesChanged:sample.read()
    }
    Component.onCompleted:properties.updateAll()
}
