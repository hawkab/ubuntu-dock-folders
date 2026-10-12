# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check popup focus, opacity, animation geometry, and panel icon sizing."""

import os
import time
from pathlib import Path
from probe_log import records

PROBE = '''
    property int probeTick: 0
    property Window frameProbe: Window {
        x:1060; y:0; width:4; height:4; visible:true
        flags:Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        property bool tick:false
        color:tick ? "#ffffff" : "#111111"
        Timer { interval:60; running:true; repeat:true; onTriggered:frameProbe.tick=!frameProbe.tick }
    }
    property Window focusProbe: Window {
        width:240; height:120; title:"Native focus target"; color:"#40505c"
    }
    function probe(phase) {
        const anchor = popup.findAnchor(root.fullRepresentationItem);
        const point = anchor ? anchor.mapToGlobal(anchor.width / 2, anchor.height / 2) : Qt.point(0, 0);
        console.log("UI_PROBE", JSON.stringify({phase, visible:popup.visible, active:popup.transition.active,
            x:popup.x, y:popup.y, width:popup.mainItem.width, height:popup.mainItem.height,
            anchorX:point.x, anchorY:point.y, sourceX:popup.transition.sourceAnchor.x, sourceY:popup.transition.sourceAnchor.y,
            overlayX:popup.transition.x, overlayY:popup.transition.y, overlayWidth:popup.transition.width,
            overlayHeight:popup.transition.height, overlayVisible:popup.transition.visible && !popup.transition.live, progress:popup.transition.progress,
            style:popup.transition.animationStyle, duration:popup.transition.motion.duration,
            blur:popup.blur.enabled, available:popup.blur.blurAvailable(), iconSize:root.iconSize,
            scale:root.groupIconScale, groupSize:anchor?.width || 0,
            circleSize:anchor?.children.find(item => item.objectName === "folder-circle")?.width || 0,
            stacked:anchor?.parent.miniatures.stacked || false, miniScale:root.groupMiniIconScale, miniSize:anchor?.parent.miniatures.size || 0,
            miniPositions:anchor?.parent.miniatures.items || [],
            renderedMiniatures:anchor?.children.filter(item => item.objectName.startsWith("folder-miniature-") && item.opacity>0).length || 0,
            settingsVisible:folderSettings.visible, showLabel:anchor?.parent.showLabel || false}));
    }
    Timer {
        interval:200; repeat:true; running:true
        onTriggered: {
            if (!root.state.groups.test || !root.fullRepresentationItem) return;
            root.probeTick++;
            const anchor = popup.findAnchor(root.fullRepresentationItem);
            switch(root.probeTick) {
            case 1:
                Plasmoid.configuration.animationSpeed=100;
                Plasmoid.configuration.groupIconSize=110;
                Plasmoid.configuration.groupMiniIconSize=100;
                Plasmoid.configuration.blurStrength=100;
                popup.sourceDesktop = "local.groups.test.desktop"; break;
            case 5: root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 6:
                if (!popup.transition.motion.running) { root.probeTick--; return; }
                popup.transition.motion.pause(); popup.transition.progress = .5; root.probe("genie"); break;
            case 10: popup.transition.progress = 1; root.probe("near-end"); break;
            case 14: popup.transition.motion.resume(); popup.transition.motion.complete(); break;
            case 18: root.probe("steady"); break;
            case 19: root.appearance("backgroundOpacity", 0); break;
            case 22: root.probe("transparent"); break;
            case 23: root.appearance("backgroundOpacity", 1); break;
            case 26: root.probe("opaque"); break;
            case 27: root.appearance("backgroundOpacity", .42); break;
            case 28: Plasmoid.configuration.groupIconSize = 130; Plasmoid.configuration.fontSize = 24; break;
            case 30: root.probe("large-icons"); root.focusProbe.show(); root.focusProbe.requestActivate(); break;
            case 35: root.probe("focus-lost"); root.focusProbe.hide(); popup.dismiss(); break;
            case 37: Plasmoid.configuration.animation = 0; root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 41: root.probe("scale-open"); popup.close(); break;
            case 45: root.probe("scale-closed"); Plasmoid.configuration.animation = 1; break;
            case 47: root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 51: root.dockFavorites = root.state.favorites.concat("test.terminal.desktop"); break;
            case 54: popup.close(); break;
            case 55: root.probe("rebuilt-source"); break;
            case 59: root.probe("genie-closed"); break;
            case 61: Plasmoid.configuration.groupMiniIconSize = 160; Plasmoid.configuration.animation = 8; root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 62:
                if (!popup.transition.motion.running) { root.probeTick--; return; }
                popup.transition.motion.pause(); popup.transition.progress = .1; root.probe("sheet-early"); break;
            case 63: popup.transition.progress = .5; root.probe("sheet-frame"); break;
            case 64: popup.transition.motion.resume(); popup.transition.motion.complete(); break;
            case 65: root.probe("large-mini-icons"); root.probe("sheet-open"); popup.close(); break;
            case 69: root.probe("sheet-closed"); Plasmoid.configuration.groupMiniIconSize = 100; Plasmoid.configuration.animation = 3; break;
            case 71: root.openFolder("local.groups.test.desktop", anchor.parent); root.probe("instant-open"); break;
            case 73: popup.close(); root.probe("instant-closed"); break;
            case 75: Plasmoid.configuration.animation = 4; root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 76:
                if (!popup.transition.motion.running) { root.probeTick--; return; }
                popup.transition.motion.pause(); popup.transition.progress = .5; root.probe("lamp-frame"); break;
            case 79: popup.transition.motion.resume(); popup.transition.motion.complete(); break;
            case 82: root.probe("lamp-open"); popup.close(); break;
            case 86: root.probe("lamp-closed"); Plasmoid.configuration.animation = 5; break;
            case 88: root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 89:
                if (!popup.transition.motion.running) { root.probeTick--; return; }
                popup.transition.motion.pause(); popup.transition.progress = .5; root.probe("fold-frame"); break;
            case 92: popup.transition.motion.resume(); popup.transition.motion.complete(); break;
            case 95: root.probe("fold-open"); popup.close(); break;
            case 99: root.probe("fold-closed"); Plasmoid.configuration.animation = 7; break;
            case 101: root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 102:
                if (!popup.transition.motion.running) { root.probeTick--; return; }
                popup.transition.motion.pause(); popup.transition.progress = .5; root.probe("unfold-frame"); break;
            case 105: popup.transition.motion.resume(); popup.transition.motion.complete(); break;
            case 108: root.probe("unfold-open"); popup.close(); break;
            case 112: root.probe("unfold-closed"); Plasmoid.configuration.animation = 10; break;
            case 114: root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 115:
                if (!popup.transition.motion.running) { root.probeTick--; return; }
                popup.transition.motion.pause(); popup.transition.progress = .45; root.probe("fade-early"); break;
            case 117: popup.transition.progress = .7; root.probe("fade-frame"); break;
            case 119: popup.transition.motion.resume(); popup.transition.motion.complete(); break;
            case 121: root.probe("fade-open"); popup.close(); break;
            case 125: root.probe("fade-closed"); Plasmoid.configuration.animation = 0; break;
            case 127: Plasmoid.configuration.animationSpeed = 50; root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 131: root.probe("slow-open"); popup.close(); break;
            case 136: root.probe("slow-closed"); break;
            case 138: Plasmoid.configuration.animationSpeed = 200; root.openFolder("local.groups.test.desktop", anchor.parent); break;
            case 141: root.probe("fast-open"); popup.close(); break;
            case 145: root.probe("fast-closed"); break;
            case 147:
                root.updateFavorites(); Plasmoid.configuration.animation = 3;
                Plasmoid.configuration.hoverEffect = 2; break;
            case 149:
                popup.sourceDesktop = "local.groups.wide.desktop";
                root.openFolder(popup.sourceDesktop, popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 150: popup.findAnchor(root.fullRepresentationItem).parent.hoverProgress = 1; break;
            case 151: root.probe("wide-folder"); popup.findAnchor(root.fullRepresentationItem).parent.hoverProgress = 0; popup.close(); break;
            case 152: root.probe("cleared-folder"); break;
            case 153:
                popup.sourceDesktop = "local.groups.test.desktop";
                root.openFolder(popup.sourceDesktop, popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 155: root.probe("narrow-folder"); popup.close(); break;
            case 156:
                popup.sourceDesktop = "local.groups.four.desktop";
                root.openFolder(popup.sourceDesktop, popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 157: root.probe("four-icons"); popup.dismiss(); break;
            case 158:
                popup.sourceDesktop = "local.groups.five.desktop";
                root.openFolder(popup.sourceDesktop, popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 159: root.probe("five-icons"); popup.dismiss(); break;
            case 160:
                popup.sourceDesktop = "local.groups.pair.desktop";
                root.openFolder(popup.sourceDesktop, popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 161: root.probe("centered-pair"); break;
            case 162: root.currentKey = "test"; folderSettings.show(); break;
            case 164: root.probe("folder-settings"); break;
            case 165: folderSettings.hide(); break;
            case 166: Plasmoid.internalAction("configure").trigger(); break;
            case 170: root.probe("settings"); stop(); break;
            }
        }
    }
'''


def instrument(source):
    return source.replace("    Component.onCompleted: {\n        properties.updateAll();",
                          PROBE + "    Component.onCompleted: {\n        properties.updateAll();")


def instrument_settings(source):
    return source.replace("    property bool ready: false", """
    Timer {
        interval: 200; running: globalSettings.ready
        onTriggered: {
            const values = {enabled:false, customization:false, animation:10, hoverEffect:3, hoverAngle:75, hoverSpeed:10,
                animationSpeed:170, groupIconSize:200, groupMiniIconSize:300, popupIconSize:88};
            const old = {};
            for (const key in values) { old[key]=globalSettings["cfg_"+key]; globalSettings["cfg_"+key]=values[key]; }
            const saved = Object.keys(values).every(key => Plasmoid.configuration[key] === values[key]);
            console.log(saved ? "AUTOSAVE_PASSED" : "AUTOSAVE_FAILED");
            for (const key in old) globalSettings["cfg_"+key]=old[key];
        }
    }
    property bool ready: false""")


def instrument_folder(source):
    return source.replace("    id: window", """    id: window
    property bool blurReviewDone:false
    property real blurReviewOriginal:0
    property int blurReviewStep:0
    Timer {
        interval:120; repeat:true; running:window.visible && !window.blurReviewDone
        onTriggered: {
            if(window.blurReviewStep++===0) {
                window.blurReviewOriginal=popupBlur.value;
                popupBlur.value=37;
                popupBlur.moved();
            } else if(window.group.blurStrength===37) {
                console.log("FOLDER_BLUR_AUTOSAVE_PASSED");
                window.appearance("blurStrength",window.blurReviewOriginal);
                window.blurReviewDone=true;
                stop();
            }
        }
    }""")


def verify(output, destination):
    from PIL import ImageGrab, ImageChops, ImageStat

    phases = {}
    pictures = {}
    software = os.environ.get("DOCK_FOLDERS_TEST_SOFTWARE_UI") == "1"
    deadline = time.monotonic() + 48
    while time.monotonic() < deadline:
        output.flush()
        for value in records(output.name, "UI_PROBE"):
            phase = value["phase"]
            if phase in phases:
                continue
            phases[phase] = value
            time.sleep(.1)
            if os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"] == "wayland" and not software:
                from plasma_glass_checks import capture
                pictures[phase] = capture()
            else:
                pictures[phase] = ImageGrab.grab(xdisplay=os.environ["DISPLAY"])
            pictures[phase].save(destination / ("plasma-ui-" + phase + ".png"))
        if "settings" in phases:
            break
        time.sleep(.04)
    assert "FOLDER_BLUR_AUTOSAVE_PASSED" in Path(output.name).read_text(), "Folder blur did not save"
    expected = {"genie", "near-end", "steady", "transparent", "opaque", "large-icons",
                "focus-lost", "scale-open", "scale-closed", "rebuilt-source", "genie-closed",
                "large-mini-icons", "sheet-closed", "instant-open", "instant-closed"}
    assert phases.keys() >= expected, phases.keys()
    assert phases["steady"]["visible"], phases["steady"]
    for phase in ("steady", "transparent"):
        assert phases[phase]["blur"] == (not software), phases[phase]
        if software:
            assert not phases[phase]["available"], "Software compositor claimed blur support"
    assert phases["large-icons"]["iconSize"] >= 40 and phases["large-icons"]["scale"] == 1.3
    assert not phases["large-icons"]["showLabel"]
    assert phases["large-icons"]["circleSize"] > phases["genie"]["circleSize"]
    assert abs(phases["large-icons"]["groupSize"] / phases["large-icons"]["iconSize"] - 1.3) < .01
    assert abs(phases["large-icons"]["circleSize"] / phases["large-icons"]["groupSize"] - .86) < .01
    assert phases["wide-folder"]["width"] > phases["narrow-folder"]["width"]
    assert phases["narrow-folder"]["width"] == phases["steady"]["width"]
    assert phases["folder-settings"]["settingsVisible"]
    for phase in ("focus-lost", "scale-closed", "genie-closed", "sheet-closed", "instant-closed"):
        assert not phases[phase]["visible"], (phase, phases[phase])
    for style, name in ((4, "lamp"), (5, "fold"), (7, "unfold"), (8, "sheet"), (10, "fade")):
        assert phases[name + "-frame"]["style"] == style and phases[name + "-frame"]["overlayVisible"]
        assert phases[name + "-open"]["visible"] and not phases[name + "-closed"]["visible"]
    assert phases["slow-open"]["duration"] == phases["fast-open"]["duration"] * 4
    assert not phases["slow-closed"]["visible"] and not phases["fast-closed"]["visible"]
    assert phases["scale-open"]["visible"] and phases["large-mini-icons"]["visible"]
    normal, large = phases["large-icons"], phases["large-mini-icons"]
    assert large["miniScale"] == 1.6 and large["miniSize"] >= normal["miniSize"]
    assert large["circleSize"] == normal["circleSize"], "Miniature sizing resized the folder circle"
    assert large["width"] == phases["steady"]["width"], "Miniature sizing resized the popup"
    positions = large["miniPositions"]
    for index, item in enumerate(positions):
        for other in positions[index + 1:]:
            assert abs(item["x"] - other["x"]) >= large["miniSize"] or abs(item["y"] - other["y"]) >= large["miniSize"]
    assert len(phases["four-icons"]["miniPositions"]) == 4
    assert len(phases["five-icons"]["miniPositions"]) == 5
    assert phases["wide-folder"]["stacked"]
    assert len(phases["wide-folder"]["miniPositions"]) == 6, "Reveal omitted applications beyond the fifth"
    assert phases["wide-folder"]["renderedMiniatures"] == 6, "Native delegates omitted applications beyond the fifth"
    pair = phases["centered-pair"]
    assert len(pair["miniPositions"]) == 2
    center = sum(item["y"] + pair["miniSize"] / 2 for item in pair["miniPositions"]) / 2
    assert abs(center - pair["groupSize"] / 2) < .01
    assert phases["instant-open"]["visible"] and not phases["instant-open"]["overlayVisible"]
    for phase in ("genie", "rebuilt-source"):
        value = phases[phase]
        assert abs(value["sourceX"] - value["anchorX"]) < 2, value
        assert abs(value["sourceY"] - value["anchorY"]) < 2, value
        assert value["overlayY"] <= value["sourceY"] <= value["overlayY"] + value["overlayHeight"], value
    assert phases["near-end"]["overlayVisible"], phases["near-end"]
    value = phases["steady"]
    box = (value["x"] + 32, value["y"] + 32, value["x"] + value["width"] - 32, value["y"] + value["height"] - 32)
    difference = ImageStat.Stat(ImageChops.difference(pictures["near-end"].crop(box), pictures["steady"].crop(box)))
    assert sum(difference.mean) / 3 < 2, ("animation changed the surface", difference.mean)
    difference = ImageStat.Stat(ImageChops.difference(pictures["transparent"].crop(box), pictures["opaque"].crop(box)))
    assert sum(difference.mean) / 3 > 15, ("opacity slider did not change the surface", difference.mean)
    narrow, wide = phases["narrow-folder"], phases["wide-folder"]
    box = (narrow["x"] + narrow["width"] + 16, narrow["y"] + 40,
           wide["x"] + wide["width"] - 32, narrow["y"] + narrow["height"] - 40)
    difference = ImageStat.Stat(ImageChops.difference(pictures["cleared-folder"].crop(box), pictures["narrow-folder"].crop(box)))
    assert sum(difference.mean) / 3 < 1, ("previous folder left pixels outside the new bounds", difference.mean)
    assert "AUTOSAVE_PASSED" in Path(output.name).read_text(), "General settings did not save immediately"
    from plasma_manage import ID, snapshot
    widget = next(w for p in snapshot() for w in p["widgets"] if w["type"] == ID)
    groups = {tuple(group["path"]):group["values"] for group in widget["configuration"]}
    assert groups.get(("General",)) and groups.get(("ConfigDialog",)), "Snapshot omitted a sibling configuration group"
    print("Native popup UI: focus, opacity, source recreation, scale, genie and surface continuity passed")
    output.seek(0, 2)
    output.write("NATIVE_UI_PASSED\n")
    output.flush()
