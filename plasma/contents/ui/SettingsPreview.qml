/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Preview shared sizes, hover formations and the production animation shader. */
import QtQuick
import "Core.js" as Core

Item {
    id: preview
    required property var values
    required property var apps
    property string mode:"dock"
    implicitHeight:214
    clip:true
    property real progress:1
    property real hoverProgress:hover.hovered && mode==="dock" ? 1 : 0
    Behavior on hoverProgress { NumberAnimation { duration:Core.hoverDuration(preview.values.hoverSpeed);easing.type:Easing.OutCubic } }
    readonly property var scene:Core.settingsPreview({values,apps,name:i18nd("ubuntu-dock-folders","Dock folders"),
        width:Math.max(1,width),height:214,mode,hover:hoverProgress,orbit:orbit.angle,labels:false})
    readonly property bool software:GraphicsInfo.api===GraphicsInfo.Software
    function replay() { if(Core.animation(values.animation).key!=="none")motion.restart(); }
    onSceneChanged:refresh.restart()
    onVisibleChanged:if(!visible){motion.stop();progress=1;}
    onValuesChanged:{motion.stop();progress=1;}
    Accessible.role:Accessible.StaticText
    Accessible.name:mode==="dock" ? i18nd("ubuntu-dock-folders","Dock icon preview") : i18nd("ubuntu-dock-folders","Open folder preview")
    HoverHandler { id:hover }
    OrbitalMotion { id:orbit;values:preview.values;hovered:hover.hovered;hoverProgress:preview.hoverProgress;allowed:preview.visible && preview.mode==="dock" }
    Repeater { model:preview.scene.background.length;delegate:PreviewCommand { required property int index;command:preview.scene.background[index] } }
    Item {
        id:card
        anchors.fill:parent
        opacity:preview.software && Core.animation(preview.values.animation).fade ? preview.progress : 1
        transform:Scale {
            origin.x:preview.scene.anchor.x;origin.y:preview.scene.anchor.y
            xScale:preview.mode!=="popup" || !preview.software || ["none","fade"].includes(Core.animation(preview.values.animation).key) ? 1 : .12+.88*preview.progress
            yScale:xScale
        }
        Repeater { model:preview.scene.commands.length;delegate:PreviewCommand { required property int index;command:preview.scene.commands[index] } }
    }
    ShaderEffectSource {
        id:sample
        sourceItem:preview.mode==="popup" && !preview.software ? card : null
        live:false;hideSource:true;visible:false
        onSourceRectChanged:scheduleUpdate()
        onTextureSizeChanged:scheduleUpdate()
        Component.onCompleted:scheduleUpdate()
    }
    Timer { id:refresh;interval:0;onTriggered:sample.scheduleUpdate() }
    ShaderEffect {
        anchors.fill:parent
        visible:preview.mode==="popup" && !preview.software
        property var source:sample
        property real progress:preview.progress
        property vector2d anchor:Qt.vector2d(preview.scene.anchor.x,preview.scene.anchor.y)
        property vector4d card:Qt.vector4d(preview.scene.rect.x,preview.scene.rect.y,preview.scene.rect.width,preview.scene.rect.height)
        property real edge:0
        property real style:Core.animation(preview.values.animation).id
        mesh:Qt.size(32,16)
        vertexShader:"../shaders/genie.vert.qsb"
        fragmentShader:"../shaders/genie.frag.qsb"
    }
    SequentialAnimation {
        id:motion
        NumberAnimation { target:preview;property:"progress";from:1;to:0;duration:Core.duration(preview.values.animation,preview.values.animationSpeed);easing.type:Core.animation(preview.values.animation).curve==="linear" ? Easing.Linear : Easing.InCubic }
        PauseAnimation { duration:120 }
        NumberAnimation { target:preview;property:"progress";from:0;to:1;duration:Core.duration(preview.values.animation,preview.values.animationSpeed);easing.type:Core.animation(preview.values.animation).curve==="linear" ? Easing.Linear : Easing.OutCubic }
    }
}
