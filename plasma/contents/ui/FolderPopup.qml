/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Resolve popup placement and delegate rendering to one persistent surface. */

import QtQuick
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import "Core.js" as Core

PlasmaCore.Dialog {
    id: popup
    required property var controller
    property bool settingsVisible: false
    property bool previewVisible: false
    property string sourceDesktop: ""
    property int generation: 0
    property bool closing: false
    property int geometrySamples: 0
    property point lastPosition: Qt.point(-1, -1)
    property size lastSize: Qt.size(-1, -1)
    readonly property var surface: Core.surface(controller.currentGroup, controller.blurStrength, Plasmoid.configuration.glass)
    readonly property bool genie: controller.animationMode === 1 && content.GraphicsInfo.api !== GraphicsInfo.Software
    readonly property bool animating: settle.running || transition.running
    readonly property QtObject blur: transition.blur
    signal settingsRequested()
    type: PlasmaCore.Dialog.Dock
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
    transientParent: null
    onTransientParentChanged: parent => { if (parent) popup.transientParent = null; }
    location: Plasmoid.location
    hideOnWindowDeactivate: false
    backgroundHints: PlasmaCore.Dialog.NoBackground

    function findAnchor(item) {
        if (item.objectName === sourceDesktop && item.iconAnchor) return item.iconAnchor;
        for (const child of item.children) {
            const anchor = findAnchor(child);
            if (anchor) return anchor;
        }
        return null;
    }
    function open() {
        generation++;
        transition.cancel();
        focusLoss.stop();
        closing = false;
        visible = true;
        geometrySamples = 0;
        lastPosition = Qt.point(-1, -1);
        lastSize = Qt.size(-1, -1);
        settle.restart();
    }
    function close() {
        if (!visible || closing) return;
        if (controller.animationMode === 3 || settle.running || !transition.live) { dismiss(); return; }
        closing = true;
        animate();
    }
    function dismiss() {
        generation++;
        focusLoss.stop();
        settle.stop();
        transition.cancel();
        visible = false;
    }
    function animate() {
        const anchor = (controller.fullRepresentationItem && findAnchor(controller.fullRepresentationItem)) || visualParent;
        if (!anchor) { dismiss(); return; }
        transition.targetRect = Qt.rect(x, y, content.width, content.height);
        transition.sourceAnchor = anchor.mapToGlobal(anchor.width / 2, anchor.height / 2);
        transition.genie = genie;
        transition.animationStyle = content.GraphicsInfo.api === GraphicsInfo.Software && controller.animationMode !== 10 ? 0 : controller.animationMode;
        transition.animationSpeed = Plasmoid.configuration.animationSpeed;
        transition.edge = location === PlasmaCore.Types.TopEdge ? 1
            : location === PlasmaCore.Types.LeftEdge ? 2 : location === PlasmaCore.Types.RightEdge ? 3 : 0;
        transition.start(closing, controller.animationMode === 3);
    }
    function updateAnchor() {
        const anchor = controller.fullRepresentationItem && findAnchor(controller.fullRepresentationItem);
        if (!anchor || anchor.width <= 0 || anchor.height <= 0) return;
        const point = anchor.mapToGlobal(anchor.width / 2, anchor.height / 2);
        if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return;
        transition.sourceAnchor = point;
        transition.place();
    }
    function refreshGeometry() {
        if (!visible || !transition.live || closing) return;
        Qt.callLater(() => {
            if (!visible || !transition.live || closing) return;
            transition.targetRect = Qt.rect(x, y, content.width, content.height);
            transition.place();
        });
    }
    onVisibleChanged: if (!visible) { generation++; settle.stop(); transition.cancel(); }
    onXChanged: refreshGeometry()
    onYChanged: refreshGeometry()
    property Timer focusLoss: Timer {
        interval: 80
        onTriggered: if (popup.visible && !transition.active && !controller.dragging) popup.close()
    }
    property QtObject dragFocus: Connections {
        target: controller
        function onDraggingChanged() {
            if (!controller.dragging && popup.visible && !transition.active) focusLoss.restart();
        }
    }
    property Timer settle: Timer {
        interval: 16; repeat: true
        onTriggered: {
            popup.geometrySamples++;
            const position = Qt.point(popup.x, popup.y);
            if ((popup.geometrySamples > 2 && position.x === popup.lastPosition.x && position.y === popup.lastPosition.y
                && content.width === popup.lastSize.width && content.height === popup.lastSize.height)
                || popup.geometrySamples >= 6) {
                stop();
                popup.animate();
            }
            popup.lastPosition = position;
            popup.lastSize = Qt.size(content.width, content.height);
        }
    }
    property FolderTransition transition: FolderTransition {
        controller: popup.controller
        popup: popup
        glass: popup.surface.blurStrength > 0
        blurAmount: popup.surface.blurStrength / 100
        onFinished: if (popup.closing) popup.dismiss()
        onDeactivated: focusLoss.restart()
    }
    mainItem: Item {
        id: content
        width: transition.folderWidth + 48
        height: transition.folderHeight + 48
        onWidthChanged: popup.refreshGeometry()
        onHeightChanged: popup.refreshGeometry()
    }
}
