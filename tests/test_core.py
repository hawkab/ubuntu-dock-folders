# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify portable transactions and geometry across Node, GJS and Qt runtimes."""

import json
import subprocess
import unittest
from pathlib import Path
from adapters.runtime import CoreRuntime
from backend_build import frontend

ROOT = Path(__file__).resolve().parent.parent


def entry(desktop):
    return {"desktop": desktop, "label": desktop}


def rounded(value):
    if isinstance(value, float): return round(value, 8)
    if isinstance(value, list): return [rounded(item) for item in value]
    if isinstance(value, dict): return {key: rounded(item) for key, item in value.items()}
    return value


class CoreTests(unittest.TestCase):
    def orbital_request(self):
        return {"args":[56,5,2.3,90,False,"orbit",20,False,0,True],
                "angle":350,"velocity":180,"elapsed":100,"hovered":True,"values":{"orbitSpeed":180,"hoverOrbitSpeed":30}}

    def test_orbital_motion_matches_node_and_gjs(self):
        request = self.orbital_request()
        result=self.runtime.call("orbitMiniatures",request)
        self.assertGreater(result["velocity"],30)
        self.assertLess(result["velocity"],180)
        command="import {orbitMiniatures} from './core/orbit.js'; console.log(JSON.stringify(orbitMiniatures(JSON.parse(process.argv[1]))));"
        output=subprocess.run(["node","--input-type=module","-e",command,json.dumps(request)],cwd=ROOT,
                              capture_output=True,text=True,check=True,timeout=3)
        self.assertEqual(rounded(result),rounded(json.loads(output.stdout)))

    def test_orbital_motion_matches_qt(self):
        runner = frontend(self, "plasma") / "code/dock-folders-core-runner"
        request = self.orbital_request()
        result = self.runtime.call("orbitMiniatures", request)
        output=subprocess.run([str(runner),str(ROOT/"core/orbit.js"),"orbitMiniatures"],input=json.dumps(request),
                              capture_output=True,text=True,check=True,timeout=3)
        self.assertEqual(rounded(result),rounded(json.loads(output.stdout)))

    def setUp(self):
        self.runtime = CoreRuntime(ROOT)
        self.addCleanup(self.runtime.close)

    def transaction(self, groups, favorites, command, entries=None, undo=None):
        request = {"state": {"groups": groups, "favorites": favorites, "undo": undo},
                   "command": command, "entries": entries or {name: entry(name) for name in ("a", "b", "c", "files")}, "token": "test"}
        result = self.runtime.call("transaction", request)
        node = "import {transact} from './core/engine.js'; import fs from 'node:fs'; console.log(JSON.stringify(transact(JSON.parse(fs.readFileSync(0,'utf8')))));"
        output = subprocess.run(["node", "--input-type=module", "-e", node], input=json.dumps(request),
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=3)
        self.assertEqual(result, json.loads(output.stdout))
        runner = ROOT / "build/plasma/contents/code/dock-folders-core-runner"
        if runner.exists():
            output = subprocess.run([str(runner), str(ROOT / "core/engine.js")], input=json.dumps(request),
                capture_output=True, text=True, check=True, timeout=3)
            self.assertEqual(result, json.loads(output.stdout))
        return result

    def group(self, *names):
        return {"one": {"id": "local.groups.One", "name": "Tools", "dockColor": "#123456",
                        "apps": [entry(name) for name in names]}}

    def test_folder_switch_decisions_match_node_gjs_and_qt(self):
        anchors=[{"key":"a","x":40,"y":500,"width":48,"height":60},
                 {"key":"b","x":90,"y":500,"width":48,"height":60}]
        for payload,opened in (({"target":"a"},"a"),({"current":"a","target":"b"},"b"),
                               ({"current":"b","target":"b"},None),
                               ({"current":"a","anchors":anchors,"point":{"x":91,"y":501}},"b")):
            result=self.runtime.call("folderInteraction",payload)
            self.assertEqual(result["open"],opened)
            command="import {folderInteraction} from './core/folderInteraction.js'; import fs from 'node:fs'; console.log(JSON.stringify(folderInteraction(JSON.parse(fs.readFileSync(0,'utf8')))));"
            output=subprocess.run(["node","--input-type=module","-e",command],input=json.dumps(payload),
                                  cwd=ROOT,capture_output=True,text=True,check=True,timeout=3)
            self.assertEqual(result,json.loads(output.stdout))
            runner=ROOT/"build/plasma/contents/code/dock-folders-core-runner"
            if runner.exists():
                output=subprocess.run([str(runner),str(ROOT/"core/engine.js"),"folderInteraction"],
                    input=json.dumps(payload),capture_output=True,text=True,check=True,timeout=3)
                self.assertEqual(result,json.loads(output.stdout))

    def test_create_keeps_target_position_and_members(self):
        result = self.transaction({}, ["a", "b", "files"], {"operation": "create", "desktop": "a", "target": "b", "name": "工具 أدوات"})
        state = result["state"]
        self.assertTrue(result["changed"])
        self.assertEqual(state["favorites"], ["local.groups.Folder_test.desktop", "files"])
        self.assertEqual(state["groups"]["folder-test"]["apps"], [entry("b"), entry("a")])
        self.assertEqual(state["groups"]["folder-test"]["name"], "工具 أدوات")

    def test_reorder_undo_preserves_new_appearance(self):
        result = self.transaction(self.group("a", "b", "c"), ["local.groups.One.desktop"],
            {"operation": "move", "desktop": "c", "key": "one", "before": "a"})
        state = result["state"]
        self.assertEqual(state["groups"]["one"]["apps"], [entry("c"), entry("a"), entry("b")])
        for property, value in (("name", "Renamed"), ("iconRotation", 90), ("alwaysStack", True), ("blurStrength",25)):
            result = self.transaction(state["groups"], state["favorites"],
                {"operation": "appearance", "key": "one", "property": property, "value": value}, undo=state["undo"])
            state = result["state"]
        result = self.transaction(state["groups"], state["favorites"], {"operation": "undo"}, undo=state["undo"])
        self.assertEqual(result["state"]["groups"]["one"]["apps"], [entry("a"), entry("b"), entry("c")])
        self.assertEqual(result["state"]["groups"]["one"]["iconRotation"], 90)
        self.assertEqual(result["state"]["groups"]["one"]["blurStrength"], 25)
        self.assertEqual(result["state"]["groups"]["one"]["name"], "Renamed")

    def test_extract_returns_launcher_and_promotes_remaining_member(self):
        result = self.transaction(self.group("a", "b"), ["files", "local.groups.One.desktop", "c"],
            {"operation": "extract", "desktop": "a", "before": "c"})
        self.assertEqual(result["state"]["groups"], {})
        self.assertEqual(result["state"]["favorites"], ["files", "b", "a", "c"])

    def test_missing_app_and_alias_are_removed_once(self):
        groups = self.group("a", "removed", "b")
        groups["one"]["apps"][1]["aliases"] = ["alias"]
        result = self.transaction(groups, ["files", "local.groups.One.desktop", "alias"], {"operation": "reconcile"})
        state = result["state"]
        self.assertTrue(result["changed"])
        self.assertEqual(state["groups"]["one"]["apps"], [entry("a"), entry("b")])
        self.assertEqual(state["favorites"], ["files", "local.groups.One.desktop"])
        self.assertFalse(self.transaction(state["groups"], state["favorites"], {"operation": "reconcile"})["changed"])
        result = self.transaction(state["groups"], state["favorites"], {"operation": "reconcile"}, {"a": entry("a"), "files": entry("files")})
        self.assertEqual(result["state"]["favorites"], ["files", "a"])
        self.assertEqual(result["state"]["groups"], {})

    def test_invalid_commands_do_not_change_folders(self):
        for command in ({"operation": "appearance", "key": "one", "property": "iconRotation", "value": True},
                        {"operation": "appearance", "key": "__proto__", "property": "name", "value": "invalid"},
                        {"operation": "move", "desktop": "missing", "key": "one"},
                        {"operation": "create", "desktop": "a", "target": "a"},
                        {"operation": "unknown"}):
            with self.subTest(command=command):
                result = self.transaction(self.group("a", "b"), ["local.groups.One.desktop"], command)
                self.assertFalse(result["changed"])
                self.assertEqual(result["state"]["groups"], self.group("a", "b"))

    def test_pin_and_reorder_folder(self):
        result = self.transaction(self.group("a", "b"), ["local.groups.One.desktop", "files"],
            {"operation": "pin", "desktop": "local.groups.One.desktop"})
        self.assertEqual(result["state"]["favorites"], ["files"])
        result = self.transaction(result["state"]["groups"], result["state"]["favorites"],
            {"operation": "pin", "desktop": "local.groups.One.desktop"})
        self.assertEqual(result["state"]["favorites"], ["files", "local.groups.One.desktop"])

    def test_large_folder_catalog_matches_gjs_and_qt(self):
        payload={"groups":self.group("a","b"),"favorites":[],
                 "sources":[{"id":"Utilities","name":"Utilities","categories":["Utility"]}],
                 "entries":{f"app-{index}.desktop":{"label":"Utility application "+str(index),"categories":["Utility"]}
                            for index in range(2000)}}
        result=self.runtime.call("folderCatalog",payload)
        self.assertEqual(len(result),2)
        self.assertEqual(len(result[1]["apps"]),2000)
        runner=ROOT/"build/plasma/contents/code/dock-folders-core-runner"
        if runner.exists():
            output=subprocess.run([str(runner),str(ROOT/"core/engine.js"),"folderCatalog"],
                input=json.dumps(payload),text=True,capture_output=True,check=True,timeout=3)
            self.assertEqual(result,json.loads(output.stdout))

    def test_hover_speed_uses_the_common_range(self):
        self.assertEqual(self.runtime.call("hoverDuration",10),1800)
        self.assertEqual(self.runtime.call("hoverDuration",50),360)
        self.assertEqual(self.runtime.call("hoverDuration",100),180)
        self.assertEqual(self.runtime.call("hoverDuration",200),90)
        self.assertEqual(self.runtime.call("hoverDuration",-999),self.runtime.call("hoverDuration",999))
        self.assertEqual(self.runtime.call("hoverDuration",0),0)
        self.assertEqual(self.runtime.call("hoverRotation",{"hoverEffect":"rotate","hoverAngle":45,"hoverSpeed":-999}),-45)
        self.assertEqual(self.runtime.call("preferences",{"hoverSpeed":-1000})["hoverSpeed"],-999)
        self.assertEqual(self.runtime.call("preferences",{"hoverAngle":999,"hoverSpeed":1})["hoverAngle"],180)
        self.assertEqual(self.runtime.call("preferences",{"hoverSpeed":1})["hoverSpeed"],1)

    def test_transparency_and_blur_are_independent_in_native_previews(self):
        for opacity in (0, .01, .17, .18, .19, .42, 1):
            for blur in (0, 1, 50, 100):
                value = self.runtime.call("surface", {"group":{"backgroundOpacity":opacity},"blurStrength":blur})
                self.assertAlmostEqual(value["backgroundOpacity"], opacity)
                self.assertAlmostEqual(value["blurAmount"], blur / 100)
                self.assertAlmostEqual(value["blurRadius"], 48 * blur / 100)

    def test_each_folder_keeps_its_blur_and_legacy_fallback(self):
        groups = self.group("a", "b")
        groups["two"] = {"id":"local.groups.Two", "name":"Second", "apps":[entry("c"),entry("files")]}
        for key, strength in (("one",0),("two",75)):
            result = self.transaction(groups, [], {"operation":"appearance", "key":key,
                "property":"blurStrength", "value":strength})
            self.assertTrue(result["changed"])
            groups = result["state"]["groups"]
        for key, strength in (("one",0),("two",75)):
            self.assertEqual(self.runtime.call("surface",{"group":groups[key],"blurStrength":50})["blurStrength"],strength)
        self.assertEqual(self.runtime.call("surface",{"group":{},"blurStrength":37})["blurStrength"],37)
        self.assertEqual(self.runtime.call("surface",{"group":{"blurStrength":0},"blurStrength":100})["blurAmount"],0)
        result = self.transaction(groups, [], {"operation":"appearance", "key":"one", "property":"blurStrength", "value":123})
        self.assertEqual(result["state"]["groups"]["one"]["blurStrength"],100)
        result = self.transaction(groups, [], {"operation":"appearance", "key":"one", "property":"blurStrength", "value":"bad"})
        self.assertFalse(result["changed"])

    def test_geometry_animations_preserve_material_opacity(self):
        animations = {item["key"]:item for item in self.runtime.call("contract")["animations"]}
        for mode in ("scale","flow","lamp","fold","sheet","unfold"):
            self.assertFalse(animations[mode]["fade"])

    def test_bulk_appearance_preserves_identity_membership_and_undo(self):
        groups = self.group("a", "b", "c")
        source = groups["one"]
        source.update(dockOpacity=.25, popupColor="#abcdef", backgroundOpacity=.17,
                      blurStrength=96, wallpaper="/tmp/wallpaper.webp", wallpaperName="wallpaper.webp",
                      wallpaperFolder="/tmp", iconRotation=135, alwaysStack=True, showLabel=True)
        groups["two"] = {"id":"local.groups.Two", "name":"Second", "gridFolder":"Imported",
                         "apps":[entry("files")], "dockColor":"#000000", "transparentDock":True}
        moved = self.transaction(groups, ["local.groups.One.desktop", "files"],
                                 {"operation":"move", "desktop":"c", "key":"one", "before":"a"})["state"]
        result = self.transaction(moved["groups"], moved["favorites"],
                                  {"operation":"applyAppearance", "key":"one"}, undo=moved["undo"])
        self.assertTrue(result["changed"])
        state = result["state"]
        self.assertEqual(state["groups"]["one"], moved["groups"]["one"])
        target = state["groups"]["two"]
        self.assertEqual((target["id"],target["name"],target["gridFolder"],target["apps"]),
                         ("local.groups.Two","Second","Imported",[entry("files")]))
        self.assertNotIn("transparentDock", target)
        for field in source.keys() - {"id","name","apps"}:
            self.assertEqual(target[field], source[field], field)
        self.assertEqual(state["favorites"], moved["favorites"])
        self.assertEqual(state["undo"], moved["undo"])
        repeated = self.transaction(state["groups"], state["favorites"],
            {"operation":"applyAppearance", "key":"one"}, undo=state["undo"])
        self.assertFalse(repeated["changed"])
        restored = self.transaction(state["groups"], state["favorites"], {"operation":"undo"}, undo=state["undo"])
        self.assertEqual(restored["state"]["groups"]["one"]["apps"], groups["one"]["apps"])
        self.assertEqual(restored["state"]["groups"]["two"]["blurStrength"],96)

    def test_bulk_appearance_clears_overrides_and_resolves_legacy_values(self):
        groups = self.group("a", "b")
        groups["one"].update(transparentDock=True, popupOpacity=.73)
        groups["two"] = {"id":"local.groups.Two", "name":"Second", "apps":[entry("c"),entry("files")],
                         "alwaysStack":True, "showLabel":True, "iconRotation":90, "blurStrength":100,
                         "wallpaper":"/tmp/other.gif", "wallpaperFolder":"/tmp", "wallpaperName":"other.gif"}
        for glass, strength in ((False,0),(True,37)):
            result = self.transaction(groups, [], {"operation":"applyAppearance", "key":"one",
                                                   "blurStrength":37 if glass else -1,"legacyGlass":glass})
            target = result["state"]["groups"]["two"]
            self.assertEqual(target["blurStrength"],strength)
            self.assertEqual(target["backgroundOpacity"],.42 if glass else .73)
            self.assertEqual(target["dockOpacity"],0)
            self.assertFalse(target["alwaysStack"] or target["showLabel"])
            self.assertEqual(target["iconRotation"],0)
            self.assertEqual([target[k] for k in ("wallpaper","wallpaperFolder","wallpaperName")],["","",""])
        for key in ("missing","__proto__"):
            result = self.transaction(groups, [], {"operation":"applyAppearance", "key":key})
            self.assertFalse(result["changed"])
            self.assertEqual(result["state"]["groups"],groups)

    def test_geometry_and_defaults_match_node(self):
        contract = self.runtime.call("contract")
        preferences = self.runtime.call("preferences", {})
        self.assertEqual(preferences, {item["name"]: item["default"] for item in contract["preferences"]})
        self.assertEqual(self.runtime.call("preferences", {"fontSize": 10.5})["fontSize"], 10.5)
        self.assertEqual([item["key"] for item in contract["animations"]],
                         ["none", "fade", "scale", "flow", "lamp", "fold", "sheet", "unfold"])
        for effect in contract["animations"]:
            for edge in range(4):
                value = {"mode": effect["key"], "speed": 125, "time": .45, "opening": True, "edge": edge,
                         "rect": {"x": 20, "y": 40, "width": 500, "height": 300},
                         "anchor": {"x": 5, "y": 180}, "points": [{"x": 20, "y": 40}, {"x": 520, "y": 340}]}
                result = self.runtime.call("frame", value)
                node = "import {deform} from './core/animationGeometry.js'; import {animation,duration,frame} from './core/preferences.js'; const v=JSON.parse(process.argv[1]), f=frame(v.mode,v.time,v.opening); console.log(JSON.stringify({animation:animation(v.mode),duration:duration(v.mode,v.speed),frame:f,points:v.points.map(p=>deform(p,v.rect,v.anchor,f.progress,v.edge,animation(v.mode).id))}));"
                output = subprocess.run(["node", "--input-type=module", "-e", node, json.dumps(value)], cwd=ROOT,
                    capture_output=True, text=True, check=True, timeout=3)
                expected = json.loads(output.stdout)
                self.assertEqual(result["animation"], expected["animation"])
                self.assertEqual(result["duration"], expected["duration"])
                for actual, point in zip(result["points"], expected["points"]):
                    self.assertAlmostEqual(actual["x"], point["x"], places=8)
                    self.assertAlmostEqual(actual["y"], point["y"], places=8)
