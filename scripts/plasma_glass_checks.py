# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check backdrop text sharpness and native blur near full transparency."""

import json
import os
import time
from pathlib import Path
from probe_log import records

PROBE = '''
    property Window backgroundProbe: Window {
        visible: true; x:0; y:0; width:1100; height:760
        flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint | Qt.WindowDoesNotAcceptFocus
        title: "Folder glass review backdrop"
        color: "#eeeeee"
        Repeater {
            model:138
            Rectangle { required property int index; x:index*8; width:4; height:760; color:"#222222" }
        }
        Repeater {
            model:26
            Rectangle {
                required property int index
                x:0; y:index*30; width:1100; height:30; color:index%2 ? "#111111" : "#eeeeee"
                Text {
                    x:8; y:3; color:parent.index%2 ? "#eeeeee" : "#222222"; font.pixelSize:16; font.family:"monospace"
                    text:"Ubuntu Dock Folders — background text 0123456789   ".repeat(3)
                }
            }
        }
    }
    property Window glassHeartbeat: Window {
        visible:true; x:1000; y:16; width:4; height:4
        flags:Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        property bool tick:false
        color:tick ? "#ffffff" : "#111111"
        Timer { interval:60; running:true; repeat:true; onTriggered:glassHeartbeat.tick=!glassHeartbeat.tick }
    }
    property int glassStep: 0
    function setOpacity(value) { root.appearance("backgroundOpacity", value); }
    function glassProbe(phase) {
        const transition = popup.transition;
        console.log("GLASS_PROBE", JSON.stringify({phase, x:popup.x, y:popup.y, width:popup.mainItem.width,
            height:popup.mainItem.height, visible:popup.visible, blur:popup.blur.enabled,
            available:popup.blur.blurAvailable(), ready:transition.compositor.ready,
            strength:transition.blurAmount, background:transition.blur.enabled,
            foregroundOpacity:transition.opacity, tint:Core.surface(root.currentGroup,root.blurStrength).backgroundOpacity, title:transition.title}));
    }
    Timer {
        interval:300; running:true; repeat:true
        onTriggered: {
            if (!root.state.groups.test || !root.fullRepresentationItem) return;
            root.glassStep++;
            switch(root.glassStep) {
            case 1: root.currentKey = "test"; Plasmoid.configuration.animation = 1; root.appearance("blurStrength", 100); root.setOpacity(.42); break;
            case 4:
                popup.sourceDesktop = "local.groups.test.desktop";
                const anchor = popup.findAnchor(root.fullRepresentationItem);
                if (!anchor) { root.glassStep--; return; }
                root.openFolder(popup.sourceDesktop, anchor.parent); break;
            case 8: root.glassProbe("58"); break;
            case 9: root.setOpacity(.2); break;
            case 12: root.glassProbe("80"); break;
            case 13: root.setOpacity(.19); break;
            case 16: root.glassProbe("81"); break;
            case 17: root.setOpacity(.18); break;
            case 20: root.glassProbe("82"); break;
            case 21: root.setOpacity(.17); break;
            case 24: root.glassProbe("83"); break;
            case 25: root.setOpacity(.16); break;
            case 28: root.glassProbe("84"); break;
            case 29: root.setOpacity(.01); break;
            case 32: root.glassProbe("99"); break;
            case 33: root.setOpacity(0); break;
            case 36: root.glassProbe("100"); break;
            case 37: root.appearance("blurStrength", 96); break;
            case 40: root.glassProbe("blur96"); break;
            case 41: root.appearance("blurStrength", 75); break;
            case 44: root.glassProbe("blur75"); break;
            case 45: root.appearance("blurStrength", 50); break;
            case 48: root.glassProbe("blur50"); break;
            case 49: root.appearance("blurStrength", 25); break;
            case 52: root.glassProbe("blur25"); break;
            case 53: root.appearance("blurStrength", 1); break;
            case 56: root.glassProbe("blur1"); break;
            case 57: root.appearance("blurStrength", 0); break;
            case 60: root.glassProbe("blur0"); break;
            case 61: root.appearance("blurStrength", 100); break;
            case 64: root.glassProbe("100-return"); break;
            case 65: popup.close(); break;
            case 68: root.glassProbe("closed"); break;
            case 69:
                root.setOpacity(.42);
                root.openFolder(popup.sourceDesktop, popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 73: root.glassProbe("reopened"); break;
            case 74: root.setOpacity(1); break;
            case 77: root.glassProbe("opaque"); break;
            case 78: root.setOpacity(.42); break;
            case 81: root.glassProbe("opacity-return"); break;
            case 82: folderSettings.show(); break;
            case 85: folderSettings.setTestTransparency(0); break;
            case 88: folderSettings.hide(); root.openFolder(popup.sourceDesktop,popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 92: root.glassProbe("slider-opaque"); folderSettings.show(); break;
            case 95: folderSettings.setTestTransparency(58); break;
            case 98: folderSettings.hide(); root.openFolder(popup.sourceDesktop,popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 102: root.glassProbe("slider-return"); break;
            case 103: popup.dismiss(); break;
            case 105: root.glassProbe("done"); if (root.animationReviewDelay) root.animationReviewDelay.start(); stop(); break;
            }
        }
    }
'''


def instrument(source):
    return source.replace("    Component.onCompleted: {\n        properties.updateAll();",
                          PROBE + "    Component.onCompleted: {\n        properties.updateAll();")


def capture():
    """Read a private presented output or invoke its offscreen screenshot API."""
    if os.environ.get("DOCK_FOLDERS_TEST_PRESENTED") == "1":
        from gi.repository import Gio, GLib
        from PIL import Image
        file = Path(os.environ["XDG_CACHE_HOME"]) / "presented-frame.png"
        file.unlink(missing_ok=True)
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync("org.kde.KWin", "/Effects",
            "org.kde.kwin.Effects", "debug", GLib.Variant("(ss)",("presentedframe","capture")),
            None, Gio.DBusCallFlags.NONE, 1000, None)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                return Image.open(file).convert("RGB")
            except (OSError, ValueError, SyntaxError):
                time.sleep(.01)
        raise RuntimeError("No ordinary compositor frame was painted")
    from gi.repository import Gio, GLib
    from PIL import Image

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    fd = os.memfd_create("dock-folders-glass-review", os.MFD_CLOEXEC)
    try:
        descriptors = Gio.UnixFDList.new()
        index = descriptors.append(fd)
        options = {"hide-caller-windows":GLib.Variant("b",False)}
        reply, _fds = connection.call_with_unix_fd_list_sync("org.kde.KWin.ScreenShot2", "/org/kde/KWin/ScreenShot2",
            "org.kde.KWin.ScreenShot2", "CaptureArea", GLib.Variant("(iiuua{sv}h)", (0,0,1100,760,options,index)),
            GLib.VariantType.new("(a{sv})"), Gio.DBusCallFlags.NONE, 3000, descriptors, None)
        metadata = reply.unpack()[0]
        size = metadata["height"] * metadata["stride"]
        deadline = time.monotonic() + 2
        while os.fstat(fd).st_size < size and time.monotonic() < deadline:
            time.sleep(.01)
        data = os.pread(fd, size, 0)
        assert len(data) == size and size < 8 * 1024 * 1024, metadata
        mode = "RGBA" if metadata["format"] in (17,18) else "BGRA"
        return Image.frombytes("RGBA", (metadata["width"],metadata["height"]), data,
                               "raw", mode, metadata["stride"]).convert("RGB")
    finally:
        os.close(fd)


def verify(output, destination):
    from PIL import ImageChops, ImageStat, ImageFilter

    phases, pictures = {}, {}
    deadline = time.monotonic() + 39
    destination = Path(destination)
    backend = os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"]
    while time.monotonic() < deadline:
        for value in records(output.name, "GLASS_PROBE"):
            phase = value["phase"]
            if phase in phases:
                continue
            phases[phase] = value
            pictures[phase] = capture()
            pictures[phase].save(destination / f"plasma-glass-{backend}-{phase}.png")
        if "done" in phases:
            break
        time.sleep(.03)
    tint_phases = ("58","80","81","82","83","84","99","100")
    blur_phases = ("100","blur96","blur75","blur50","blur25","blur1")
    assert phases.keys() >= {*tint_phases, *blur_phases, "blur0", "100-return", "closed", "reopened", "done"}, phases
    for phase in (*tint_phases, *blur_phases, "100-return"):
        assert phases[phase]["available"] and phases[phase]["ready"] and phases[phase]["blur"], phases[phase]
        assert phases[phase]["foregroundOpacity"] == 1, "Blur faded foreground controls"
    for phase in tint_phases:
        assert phases[phase]["strength"] == 1, "Transparency changed the blur amount"
    assert not phases["blur0"]["background"] and not phases["blur0"]["blur"]
    assert not phases["closed"]["background"] and not phases["closed"]["visible"]
    value = phases["100"]
    box = (value["x"]+40, value["y"]+value["height"]-56, value["x"]+value["width"]-40, value["y"]+value["height"]-40)
    def difference(a, b):
        return sum(ImageStat.Stat(ImageChops.difference(pictures[a].crop(box), pictures[b].crop(box))).mean) / 3
    def sharpness(phase):
        patch = pictures[phase].crop(box).convert("L")
        details = ImageChops.difference(patch,patch.filter(ImageFilter.GaussianBlur(3)))
        return ImageStat.Stat(details).stddev[0]
    sharpness_ratio = sharpness("100") / sharpness("blur0")
    assert sharpness_ratio < .1, ("Blur retained sharp background text", sharpness_ratio)
    blurred_mean = ImageStat.Stat(pictures["100"].crop(box)).mean
    source_mean = ImageStat.Stat(pictures["closed"].filter(ImageFilter.GaussianBlur(48)).crop(box)).mean
    assert max(abs(a-b) for a,b in zip(blurred_mean,source_mean)) < 25, "Blur lost the captured background colors"
    tint_steps = {f"{a}-{b}":difference(a,b) for a,b in zip(tint_phases[1:5],tint_phases[2:6])}
    assert all(value < 3 for value in tint_steps.values()), ("Transparency jumped around 82–83%",tint_steps)
    assert difference("99","100") < 3, "Transparency jumped at 100%"
    differences = {phase:difference(phase,"blur0") for phase in blur_phases}
    assert differences["100"] > 20, ("Compositor blur was not rendered", differences)
    details = {phase:sharpness(phase) for phase in (*blur_phases,"blur0")}
    assert details["blur25"] < details["blur0"] * .1, ("Blur left sharp text contours",details)
    assert details["blur1"] > details["blur25"] * 5, ("Slider did not change the blur radius",details)
    assert differences["blur1"] < 12, ("Blur jumped at its zero endpoint",differences)
    outside = (value["x"]+value["width"]+24,value["y"]+32,value["x"]+value["width"]+64,value["y"]+72)
    assert sum(ImageStat.Stat(ImageChops.difference(pictures["100"].crop(outside),pictures["blur0"].crop(outside))).mean)/3 < 1, "Blur escaped the folder's boundary"
    assert difference("100", "100-return") < 2, "Re-enabling blur changed its placement or opacity"
    header = (value["x"]+32,value["y"]+32,value["x"]+180,value["y"]+72)
    foreground = ImageStat.Stat(ImageChops.difference(pictures["100"].crop(header),pictures["100-return"].crop(header)))
    assert sum(foreground.mean) / 3 < 2, "Re-enabling blur covered the foreground controls"
    assert difference("58", "reopened") < 2, "Animated reopening lost or changed the blur"
    assert difference("58", "opacity-return") < 2, "Returning from full opacity changed the folder material"
    assert difference("58", "slider-return") < 2, "Folder transparency slider did not restore its material"
    from gi.repository import Gio, GLib
    from plasma_manage import evaluate

    plugin = (Path(__file__).resolve().parent.parent / "build" /
              ("kwin-backdrop-" + backend) / "plugin-name.txt").read_text().strip()

    if os.environ.get("DOCK_FOLDERS_TEST_PRESENTED") == "1":
        import plasma_animation_checks
        plasma_animation_checks.verify(output, destination)

    evaluate("for(var p of panels()){for(var w of p.widgets()){if(w.type==='io.github.hawkab.DockFolders')w.remove();}}")
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    deadline = time.monotonic() + 3
    while True:
        loaded = connection.call_sync("org.kde.KWin", "/Effects", "org.kde.kwin.Effects", "isEffectLoaded",
            GLib.Variant("(s)",(plugin,)), None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
        if not loaded:
            break
        assert time.monotonic() < deadline, "Removing the widget left its compositor effect loaded"
        time.sleep(.05)
    output.seek(0, 2)
    output.write("NATIVE_GLASS_PASSED " + json.dumps({"blur":differences, "tintSteps":tint_steps, "textSharpness":sharpness_ratio}) + "\n")
    output.flush()
    print("Native glass transparency:", backend, differences)
