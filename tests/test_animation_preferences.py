# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check animation choices and speed persistence in native GTK preferences."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class AnimationPreferencesTests(unittest.TestCase):
    def test_folder_rotation_and_stack_are_saved_without_hiding_gnome_labels(self):
        code = """
import json,sys
sys.path.insert(0,sys.argv[1])
import preferences as p
p.Adw.init()
group={'id':'local.groups.test','name':'Test','colors':['#263d4a','#263d4a'],
       'apps':[{'desktop':'missing.desktop','label':'Missing'}]}
p.SETTINGS.set_string('groups',json.dumps({'test':group}))
app=p.Preferences('test')
app.register(None)
app.activate_window(app)
window=app.get_windows()[0]
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from walk(child)
  child=child.get_next_sibling()
widgets=list(walk(window))
rotation=next(w for w in widgets if isinstance(w,p.Gtk.Scale) and w.get_name()=='icon-rotation')
rotation.set_value(90)
cards=next(w for w in widgets if isinstance(w,p.Adw.SwitchRow) and w.get_title()=='Always use card stack')
cards.set_active(True)
assert p.groups()['test']['iconRotation']==90 and p.groups()['test']['alwaysStack']
assert any(isinstance(w,p.Adw.SwitchRow) and w.get_title()=='Label below the icon' for w in widgets)
blur=next(w for w in widgets if isinstance(w,p.Gtk.Scale) and w.get_name()=='folder-background-blur')
for value in (0,1,25,50,100):
 blur.set_value(value)
 assert p.groups()['test']['blurStrength']==value
 assert app.surface(p.groups()['test'])['blurStrength']==value
window.destroy()
print('OK')
"""
        result = subprocess.run(
            ["/usr/bin/python3", "-c", code, str(ROOT / "build/extension/app")],
            env=dict(os.environ, GSETTINGS_BACKEND="memory", LANGUAGE="en", LC_ALL="C.UTF-8"),
            check=True, capture_output=True, text=True, timeout=15,
        )
        self.assertIn("OK", result.stdout)

    def test_animation_modes_and_speed_are_saved(self):
        code = """
import sys
sys.path.insert(0,sys.argv[1])
import preferences as p
p.Adw.init()
app=p.Preferences(None)
app.register(None)
app.activate_window(app)
window=app.get_windows()[0]
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from walk(child)
  child=child.get_next_sibling()
widgets=list(walk(window))
animation=next(w for w in widgets if isinstance(w,p.Adw.ComboRow) and w.get_title()=='Opening and closing animation')
assert not any(w.get_buildable_id()=='blur_strength_scale' for w in widgets)
assert not any(w.get_buildable_id()=='glass_row' for w in widgets)
for index,mode in enumerate(('none','fade','scale','flow','lamp','fold','sheet','unfold')):
 animation.set_selected(index)
 assert p.SETTINGS.get_string('animation')==mode
rotate=next(w for w in widgets if isinstance(w,p.Gtk.CheckButton) and w.get_buildable_id()=='hover_rotate_check')
cards=next(w for w in widgets if isinstance(w,p.Gtk.CheckButton) and w.get_buildable_id()=='hover_cards_check')
for rotation,fan,mode in ((True,False,'rotate'),(True,True,'rotate-cards'),(False,True,'cards'),(False,False,'none')):
 rotate.set_active(rotation); cards.set_active(fan)
 assert p.SETTINGS.get_string('hover-effect')==mode
angle=next(w for w in widgets if isinstance(w,p.Gtk.Scale) and w.get_buildable_id()=='hover_angle_scale')
hover_speed=next(w for w in widgets if isinstance(w,p.Gtk.Scale) and w.get_buildable_id()=='hover_speed_scale')
angle.set_value(75); hover_speed.set_value(10)
assert p.SETTINGS.get_int('hover-angle')==75 and p.SETTINGS.get_int('hover-speed')==10
speed=next(w for w in widgets if isinstance(w,p.Gtk.Scale) and w.get_buildable_id()=='animation_speed_scale')
for value in (50,100,200):
 speed.set_value(value)
 assert p.SETTINGS.get_int('animation-speed')==value
icons=next(w for w in widgets if isinstance(w,p.Gtk.Scale) and w.get_buildable_id()=='mini_icon_size_scale')
for value in (80,100,160,300):
 icons.set_value(value)
 assert p.SETTINGS.get_int('mini-icon-size')==value
window.destroy()
print('OK')
"""
        result = subprocess.run(
            ["/usr/bin/python3", "-c", code, str(ROOT / "build/extension/app")],
            env=dict(os.environ, GSETTINGS_BACKEND="memory", LANGUAGE="en", LC_ALL="C.UTF-8"),
            check=True, capture_output=True, text=True, timeout=15,
        )
        self.assertIn("OK", result.stdout)
