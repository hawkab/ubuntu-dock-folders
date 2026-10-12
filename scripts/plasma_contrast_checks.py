# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check adaptive labels against changing windows using ordinary compositor frames."""

import json
import os
import re
import time
from pathlib import Path

PROBE = '''
    property Window contrastBackground: Window {
        visible:true; x:0; y:0; width:1100; height:760; color:"#ffffff"
        flags:Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint | Qt.WindowDoesNotAcceptFocus
        title:"Folder contrast backdrop"
    }
    property Window contrastHeartbeat: Window {
        visible:true; x:1050; y:10; width:4; height:4
        flags:Qt.Window | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        property bool beat:false
        color:beat ? "white" : "black"
        Timer { interval:120; repeat:true; running:true; onTriggered:contrastHeartbeat.beat=!contrastHeartbeat.beat }
    }
    property int contrastTick:-24
    function contrastProbe(phase) {
        console.log("CONTRAST_PROBE",JSON.stringify({phase,foreground:popup.transition.foreground.toString(),
            sample:popup.transition.compositor.background,visible:popup.transition.visible,
            x:popup.x,y:popup.y,width:popup.mainItem.width,height:popup.mainItem.height,
            blur:popup.transition.blurAmount}));
    }
    Timer {
        interval:250; repeat:true; running:true
        onTriggered: {
            if(!root.state.groups.test || !root.fullRepresentationItem) return;
            switch(++root.contrastTick) {
            case 1:
                root.currentKey="test";
                Plasmoid.configuration.animation=3;
                root.appearance("popupColor","#26262a");
                root.appearance("backgroundOpacity",.01);
                root.appearance("blurStrength",100); break;
            case 4:
                popup.sourceDesktop="local.groups.test.desktop";
                root.openFolder(popup.sourceDesktop,popup.findAnchor(root.fullRepresentationItem).parent); break;
            case 10: root.contrastProbe("white"); break;
            case 16: root.contrastProbe("white-idle"); break;
            case 17: contrastBackground.color="#080808"; break;
            case 23: root.contrastProbe("dark"); break;
            case 24: root.appearance("blurStrength",0); break;
            case 25: contrastBackground.color="#ffffff"; break;
            case 31: root.contrastProbe("white-without-blur"); break;
            case 32: root.appearance("backgroundOpacity",1); break;
            case 36: root.contrastProbe("opaque-dark"); break;
            case 37: root.appearance("popupColor","#ffffff"); break;
            case 41: root.contrastProbe("opaque-white"); break;
            case 42: popup.dismiss(); break;
            case 44: root.contrastProbe("closed");stop();break;
            }
        }
    }
'''


def instrument(source):
    return source.replace("    Component.onCompleted: {\n        properties.updateAll();",
                          PROBE + "    Component.onCompleted: {\n        properties.updateAll();")


def verify(output, destination):
    """Require actual label colors and no continuous idle sampling."""
    from gi.repository import Gio, GLib
    from PIL import Image
    from plasma_glass_checks import capture
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    plugin = (Path(__file__).resolve().parent.parent / "build" /
              ("kwin-backdrop-" + os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"]) / "plugin-name.txt").read_text().strip()
    phases, counters = {}, {}
    deadline = time.monotonic() + 23
    while time.monotonic() < deadline:
        for payload in re.findall(r"CONTRAST_PROBE (\{.*\})", Path(output.name).read_text()):
            value = json.loads(payload)
            phase = value["phase"]
            if phase in phases: continue
            phases[phase] = value
            counters[phase] = bus.call_sync("org.kde.KWin", "/Effects", "org.kde.kwin.Effects", "debug",
                GLib.Variant("(ss)", (plugin,"contrast")),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
            if phase != "closed":
                capture().save(Path(destination) / ("contrast-" + phase + "-" + os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"] + ".png"))
        if "closed" in phases: break
        time.sleep(.03)
    expected = {"white":"#000000","white-idle":"#000000","dark":"#ffffff",
                "white-without-blur":"#000000","opaque-dark":"#ffffff","opaque-white":"#000000"}
    for phase,color in expected.items():
        assert phases[phase]["visible"] and phases[phase]["foreground"] == color, (phase,phases.get(phase))
        image = Image.open(Path(destination) / ("contrast-" + phase + "-" + os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"] + ".png")).convert("RGB")
        value = phases[phase]
        title = image.crop((value["x"]+38,value["y"]+42,value["x"]+92,value["y"]+63))
        pixels = title.getdata()
        count = sum(max(pixel)<50 if color=="#000000" else min(pixel)>220 for pixel in pixels)
        assert count > 30, ("Rendered heading has the wrong foreground",phase,count)
    assert not phases["closed"]["visible"]
    assert counters["white"] == counters["white-idle"], ("Idle backdrop kept sampling",counters)
    assert int(re.search(r"reads=(\d+)",counters["white"])[1]) <= 6,counters
    Path(destination,"contrast-results-"+os.environ["DOCK_FOLDERS_TEST_PLASMA_BACKEND"]+".json").write_text(
        json.dumps({"phases":phases,"counters":counters},indent=2))
    output.seek(0,2);output.write("NATIVE_CONTRAST_PASSED\n");output.flush()
    print("Adaptive labels: light/dark windows, blur disabled, opaque colors and idle sampling passed")
