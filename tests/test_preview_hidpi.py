# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Compare animation meshes with direct native rendering at normal and 2x scale."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops
from backend_build import frontend

SCENE = {"commands": [
    {"type": "round", "x": 0, "y": 0, "width": 64, "height": 64, "radius": 0, "color": "#112233", "alpha": 1},
    {"type": "circle", "x": 12.25, "y": 12.25, "radius": 7.25, "color": "#ffffff", "alpha": 1},
    {"type": "icon", "x": 26, "y": 4, "size": 32, "app": {"icon": "folder"}, "alpha": 1},
    {"type": "text", "x": 0, "y": 40, "size": 10, "width": 64, "value": "HiDPI", "color": "#ffffff"},
]}

PYTHON = """
import json,sys,cairo
sys.path.insert(0,sys.argv[1])
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from preview_paint import PreviewPaint
widget=Gtk.DrawingArea(content_width=64,content_height=64)
window=Gtk.Window(child=widget)
window.present()
loop=GLib.MainLoop();GLib.timeout_add(150,lambda:loop.quit() or False);loop.run()
scale=int(sys.argv[4]);assert widget.get_scale_factor()==scale
paint=PreviewPaint(widget);scene=json.loads(sys.argv[3])
reference=cairo.ImageSurface(cairo.FORMAT_ARGB32,64*scale,64*scale);reference.set_device_scale(scale,scale)
paint.commands(cairo.Context(reference),scene['commands'])
card=paint.surface(scene,64,64)
result=cairo.ImageSurface(cairo.FORMAT_ARGB32,64*scale,64*scale);result.set_device_scale(scale,scale)
points=[{'x':0,'y':0},{'x':64,'y':0},{'x':64,'y':64},{'x':0,'y':64}]
paint.mesh(cairo.Context(result),card,{'opacity':1,'triangles':[
 {'points':[points[0],points[1],points[2]],'matrix':[1,0,0,1,0,0]},
 {'points':[points[0],points[2],points[3]],'matrix':[1,0,0,1,0,0]}]})
reference.write_to_png(sys.argv[2]+'/reference.png');result.write_to_png(sys.argv[2]+'/card.png')
print('NATIVE_HIDPI_OK',widget.get_scale_factor(),next(iter(paint.icons.values())).get_width())
window.destroy()
"""

JAVASCRIPT = """
import Cairo from 'cairo';
import Gtk from 'gi://Gtk?version=4.0';
import GLib from 'gi://GLib';
import {PreviewPaint} from MODULE;
Gtk.init();
const widget=new Gtk.DrawingArea({content_width:64,content_height:64});
const window=new Gtk.Window({child:widget});window.present();
const loop=new GLib.MainLoop(null,false);
GLib.timeout_add(GLib.PRIORITY_DEFAULT,150,()=>{loop.quit();return GLib.SOURCE_REMOVE;});loop.run();
const scale=Number(ARGV[2]);
if (widget.get_scale_factor()!==scale) throw new Error('The native window is on the wrong display scale');
const paint=new PreviewPaint(widget),scene=JSON.parse(ARGV[1]);
const reference=new Cairo.ImageSurface(Cairo.Format.ARGB32,64*scale,64*scale);reference.setDeviceScale(scale,scale);
let context=new Cairo.Context(reference);paint.commands(context,scene.commands);context.$dispose();
const card=paint.surface(scene,64,64);
const result=new Cairo.ImageSurface(Cairo.Format.ARGB32,64*scale,64*scale);result.setDeviceScale(scale,scale);
const points=[{x:0,y:0},{x:64,y:0},{x:64,y:64},{x:0,y:64}];
context=new Cairo.Context(result);paint.mesh(context,card,{opacity:1,triangles:[
 {points:[points[0],points[1],points[2]],transform:[0,0,0,1,1,0]},
 {points:[points[0],points[2],points[3]],transform:[0,0,0,1,1,0]}]});context.$dispose();
reference.writeToPNG(ARGV[0]+'/reference.png');result.writeToPNG(ARGV[0]+'/card.png');
print('NATIVE_HIDPI_OK',widget.get_scale_factor(),paint.icons.values().next().value.width);
window.destroy();
"""


class PreviewHiDpiTests(unittest.TestCase):
    def compare(self, command, directory, scale):
        env = dict(os.environ, GDK_SCALE=str(scale), GSK_RENDERER="cairo", GTK_A11Y="none")
        result = subprocess.run(command, env=env, text=True, capture_output=True, check=True, timeout=15)
        self.assertIn(f"NATIVE_HIDPI_OK {scale} {96*scale}", result.stdout)
        with Image.open(directory / "reference.png") as expected, Image.open(directory / "card.png") as actual:
            difference = ImageChops.difference(expected.convert("RGB"), actual.convert("RGB"))
            self.assertIsNone(difference.getbbox(), "The animated card loses detail compared with direct 2x rendering")

    def test_python_animation_card_keeps_native_detail(self):
        for desktop in ("gnome", "xfce"):
            with self.subTest(desktop=desktop):
                app = frontend(self, desktop) / "app"
                for scale in (1, 2):
                    with self.subTest(scale=scale), tempfile.TemporaryDirectory(prefix="preview-hidpi-") as directory:
                        self.compare(["/usr/bin/python3", "-c", PYTHON, str(app), directory, json.dumps(SCENE), str(scale)], Path(directory), scale)

    def test_gjs_animation_card_keeps_native_detail(self):
        module = frontend(self, "gnome") / "previewPaint.js"
        for scale in (1, 2):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory(prefix="preview-hidpi-") as directory:
                path = Path(directory)
                script = path / "check.mjs"
                script.write_text(JAVASCRIPT.replace("MODULE", json.dumps(module.as_uri())))
                self.compare(["gjs", "-m", str(script), directory, json.dumps(SCENE), str(scale)], path, scale)


if __name__ == "__main__":
    unittest.main()
