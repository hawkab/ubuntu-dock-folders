/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Animate one interactive folder surface with a matching backdrop region. */

import QtQuick
import org.kde.plasma.core as PlasmaCore
import "../effects" as Effects
import "Core.js" as Core
import "FolderGeometry.js" as Geometry

PlasmaCore.Dialog {
    id: transition
    required property var controller
    required property var popup
    property rect targetRect
    property point sourceAnchor
    property real progress: 1
    property int edge: 0
    property bool genie: false
    property int animationStyle: 0
    property real animationSpeed: 100
    property bool glass: false
    property real blurAmount: 0
    readonly property real blurOpacity: Core.animation(animationStyle).fade ? progress : 1
    property int padding: 24
    property int placementSamples: 0
    property bool live: false
    property bool closing: false
    property bool hadFocus: false
    property bool ready: false
    readonly property real folderWidth: folder.width
    readonly property real folderHeight: folder.height
    readonly property color foreground: folder.foreground
    property alias canvas: canvasItem
    readonly property int desiredX: Math.floor(Math.min(targetRect.x, sourceAnchor.x - 16))
    readonly property int desiredY: Math.floor(Math.min(targetRect.y, sourceAnchor.y - 16))
    readonly property bool running: motion.running || placement.running
    readonly property point localAnchor: Qt.point(sourceAnchor.x - x, sourceAnchor.y - y)
    readonly property rect card: Qt.rect(targetRect.x - x + padding, targetRect.y - y + padding,
                                         targetRect.width - 2 * padding, targetRect.height - 2 * padding)
    signal finished()
    signal deactivated()
    type: PlasmaCore.Dialog.Dock
    location: PlasmaCore.Types.Floating
    backgroundHints: PlasmaCore.Dialog.NoBackground
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    title: compositor.prefix + blurAmount.toFixed(6) + ":" + blurOpacity.toFixed(6)
        + ":" + [Math.floor(card.x), Math.floor(card.y), Math.ceil(card.width), Math.ceil(card.height)].join(",")
        + ":" + (popup.surface.backgroundOpacity < .98 && !controller.currentGroup?.wallpaper ? "1" : "0")
    transientParent: null
    hideOnWindowDeactivate: false
    onXChanged: if (visible && x !== desiredX) x = desiredX
    onYChanged: if (visible && y !== desiredY) y = desiredY
    onProgressChanged: if (visible && ready && !live) popup.updateAnchor()
    onTransientParentChanged: parent => { if (parent) transition.transientParent = null; }
    onActiveChanged: {
        if (active) hadFocus = true;
        else if (hadFocus && visible) deactivated();
    }

    function start(isClosing, instant) {
        motion.stop();
        closing = isClosing;
        if (!isClosing) {
            place();
            live = instant;
            progress = instant ? 1 : 0;
            ready = instant;
            hadFocus = false;
            visible = true;
            requestActivate();
        }
        if (instant) return;
        ready = true;
        begin();
    }

    function place() {
        x = desiredX;
        y = desiredY;
        scene.width = Math.ceil(Math.max(targetRect.x + targetRect.width, sourceAnchor.x + 16) - x);
        scene.height = Math.ceil(Math.max(targetRect.y + targetRect.height, sourceAnchor.y + 16) - y);
    }
    function begin() {
        live = false;
        progress = closing ? 1 : 0;
        motion.from = progress;
        motion.to = closing ? 0 : 1;
        motion.easing.type = Core.animation(animationStyle).curve === "linear" ? Easing.Linear : closing ? Easing.InCubic : Easing.OutCubic;
        placementSamples = 0;
        placement.restart();
    }
    function cancel() {
        placement.stop();
        motion.stop();
        visible = false;
        ready = false;
        live = false;
    }
    property Timer placement: Timer {
        interval: 16; repeat: true
        onTriggered: {
            transition.placementSamples++;
            transition.x = transition.desiredX;
            transition.y = transition.desiredY;
            if (transition.placementSamples >= 3) { stop(); motion.restart(); }
        }
    }
    property Effects.BackdropBlur compositor: Effects.BackdropBlur {}
    readonly property QtObject blur: input
    property QtObject input: Effects.WindowEffects {
        window: transition
        enabled: transition.visible && transition.ready && transition.glass && transition.blurAmount > 0 && transition.compositor.ready
        allowSmallBlur: transition.compositor.ready
        polygon: Geometry.outline(transition.card, transition.localAnchor, transition.progress,
            transition.edge, transition.animationStyle, Core.contract.layout.radius)
        constrainInput: transition.live
        inputRegion: Qt.rect(transition.targetRect.x - transition.x, transition.targetRect.y - transition.y,
            transition.targetRect.width, transition.targetRect.height)
    }
    property NumberAnimation motion: NumberAnimation {
        target: transition; property: "progress"
        duration: Core.duration(transition.animationStyle, transition.animationSpeed)
        onFinished: {
            if (!transition.closing) {
                transition.live = true;
                transition.requestActivate();
            }
            transition.finished();
        }
    }
    mainItem: Item {
        id: scene
        TapHandler {
            onTapped: point => {
                const local = folder.mapFromItem(scene, point.position);
                if ((!transition.live || !folder.contains(local)) &&
                    !transition.controller.folderPress(scene.mapToGlobal(point.position))) transition.popup.close();
            }
        }
        Item {
            x: transition.targetRect.x - transition.x
            y: transition.targetRect.y - transition.y
            width: transition.targetRect.width
            height: transition.targetRect.height
            opacity: GraphicsInfo.api === GraphicsInfo.Software && Core.animation(transition.animationStyle).fade
                ? transition.progress : 1
            transform: Scale {
                origin.x: transition.sourceAnchor.x - transition.targetRect.x
                origin.y: transition.sourceAnchor.y - transition.targetRect.y
                xScale: transition.live || GraphicsInfo.api !== GraphicsInfo.Software || transition.animationStyle === 10 ? 1 : .12 + .88 * transition.progress
                yScale: xScale
            }
            Item {
                id: canvasItem
                anchors.fill: parent
                FolderContent {
                    id: folder
                    x: transition.padding; y: transition.padding
                    controller: transition.controller
                    popup: transition.popup
                    onSettingsRequested: transition.popup.settingsRequested()
                }
            }
        }
        ShaderEffectSource {
            id: texture
            sourceItem: transition.visible && GraphicsInfo.api !== GraphicsInfo.Software ? canvasItem : null
            live: true
            hideSource: true
            visible: false
        }
        ShaderEffect {
            x: transition.targetRect.x - transition.x
            y: transition.targetRect.y - transition.y
            width: transition.targetRect.width; height: transition.targetRect.height
            visible: transition.ready && GraphicsInfo.api !== GraphicsInfo.Software
            property var source: texture
            property real progress: transition.progress
            property vector2d anchor: Qt.vector2d(transition.sourceAnchor.x - transition.targetRect.x,
                                                   transition.sourceAnchor.y - transition.targetRect.y)
            property vector4d card: Qt.vector4d(transition.padding, transition.padding,
                width - transition.padding * 2, height - transition.padding * 2)
            property real edge: transition.edge
            property real style: transition.animationStyle
            mesh: Qt.size(48, 48)
            vertexShader: "../shaders/genie.vert.qsb"
            fragmentShader: "../shaders/genie.frag.qsb"
        }
        MouseArea {
            anchors.fill: parent
            enabled: !transition.live
            onClicked: mouse => {
                if (!transition.controller.folderPress(mapToGlobal(mouse.x, mouse.y))) transition.popup.close();
            }
        }
    }
}
