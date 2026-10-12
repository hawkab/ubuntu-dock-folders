# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Instrument the real widget with native panel and pointer probes."""

STARTUP = "    Component.onCompleted: {\n        properties.updateAll();"

PANEL = """
    Timer {
        interval: 3000; running: true
        onTriggered: {
            console.log("NATIVE_PANEL_READY", Object.keys(root.state.groups).length);
            root.currentKey = "test";
            popup.visualParent = root.fullRepresentationItem;
            popup.visible = true;
            root.activate("test.terminal.desktop");
        }
    }
    Timer {
        interval: 5500; running: true
        onTriggered: {
            console.log("NATIVE_WINDOW_DOT", !!root.taskSummary["test.terminal.desktop"]);
            console.log("NATIVE_TASKS", JSON.stringify(Array.from({length: root.taskDelegateModel?.count || 0}, (_, index) => {const t=root.taskDelegateModel.itemAt(index); return {id:t.desktop,title:t.title,running:t.running,appId:t.model.AppId,launcher:t.model.LauncherUrlWithoutIcon};})), JSON.stringify(root.taskSummary));
            root.currentKey = "test";
            popup.visible = true;
            folderSettings.show();
        }
    }
    Component.onCompleted: {
        properties.updateAll();"""

INTERACTION = """
    function collect(item, result) {
        if (item.visible && item.objectName && item.objectName.endsWith(".desktop")) {
            const point = item.mapToGlobal(item.width/2, Math.min(item.height/2,32));
            result[item.objectName] = {x:point.x,y:point.y};
            if (item.folder && !item.folderKey) result.__hover = {desktop:item.desktop,progress:item.hoverProgress, mode:root.hoverEffect,
                size:item.miniatures.size, width:item.width, height:item.height, items:item.miniatures.items,
                cards:item.miniatures.cardOpacity, stacked:item.miniatures.stacked, body:item.iconSize,
                angle:root.hoverAngle, duration:root.hoverDuration,
                orbitalPhase:item.data.find(child=>child.objectName==="folder-orbital-motion")?.angle || 0,
                orbitalVelocity:item.data.find(child=>child.objectName==="folder-orbital-motion")?.velocity || 0,
                orbitalRunning:item.data.find(child=>child.objectName==="folder-orbital-motion")?.running || false};
            if (result.__hover && item.folder && !item.folderKey)
                result.__hover.glyphAngles=item.iconAnchor.children
                    .filter(c=>c.objectName.startsWith("folder-miniature-"))
                    .map(c=>c.rotation+c.children.find(g=>g.objectName.startsWith("folder-glyph-"))?.rotation);
        }
        for (const child of item.children) collect(child,result);
    }
    Timer {
        interval: 250; repeat:true; running:true
        onTriggered: {
            const result={};
            if(root.fullRepresentationItem) {
                collect(root.fullRepresentationItem,result);
                const point=root.fullRepresentationItem.mapToGlobal(0,0);
                result.__dock={x:point.x,y:point.y,width:root.fullRepresentationItem.width,height:root.fullRepresentationItem.height};
            }
            if(popup.visible && popup.transition.live) collect(popup.transition.canvas,result);
            result.__popup={visible:popup.visible,key:root.currentKey,live:popup.transition.live,closing:popup.closing};
            console.log("NATIVE_GEOMETRY",JSON.stringify(result));
        }
    }
    Component.onCompleted: {
        properties.updateAll();"""


def instrument(text, interaction=False):
    """Add the selected probe without changing widget startup behavior."""
    return text.replace(STARTUP, INTERACTION if interaction else PANEL)
