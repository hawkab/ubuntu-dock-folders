# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise both global settings tabs and their previews in native GTK."""

import os
import subprocess
import unittest
from pathlib import Path
from backend_build import frontend

ROOT=Path(__file__).resolve().parent.parent


class GeneralSettingsTests(unittest.TestCase):
    def test_close_and_destroy_release_workers_before_python_finalization(self):
        code='''
import gc,json,sys
sys.path.insert(0,sys.argv[1])
import preferences as p
from global_preferences import build_global_window
from gi.repository import GLib
p.Adw.init()
p.SETTINGS.set_string('groups',json.dumps({'demo':{'id':'local.groups.demo','name':'Demo',
 'apps':[{'desktop':'missing.desktop','label':'Missing'}]}}))
def drain():
 loop=GLib.MainLoop()
 GLib.timeout_add(40,lambda:loop.quit() or False)
 loop.run()
for index in range(6):
 app=p.Preferences('demo')
 folder=app.group_window(p.groups()['demo'])
 general=build_global_window()
 workers=[app.core.process,general._settings_previews[0].core.process]
 for window in (folder,general):
  window.present()
  drain()
  (window.close if index%2 else window.destroy)()
 drain()
 assert all(worker.poll() is not None for worker in workers)
 p.SETTINGS.set_int('blur-strength',20+index)
 del window,folder,general,app
 gc.collect()
 drain()
print('PREFERENCES_CLEANUP_PASSED')
'''
        result=subprocess.run(["/usr/bin/python3","-X","faulthandler","-c",code,str(ROOT/"build/extension/app")],
            env=dict(os.environ,LANGUAGE="en",LC_ALL="C.UTF-8",GSETTINGS_BACKEND="memory"),
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("PREFERENCES_CLEANUP_PASSED",result.stdout)
        self.assertNotIn("Traceback",result.stderr)
        self.assertNotIn("CRITICAL",result.stderr)

    def test_live_tabs_preserve_folder_settings_in_gnome_and_xfce(self):
        code='''
import json,sys
sys.path.insert(0,sys.argv[1])
import preferences as p
from preferences_binding import bind_preferences
from settings_preview import attach_previews
from gi.repository import GLib
p.Adw.init()
builder=p.Gtk.Builder()
builder.add_from_file(str(p.ROOT/'preferences.ui'))
window=builder.get_object('preferences_window')
group={'id':'local.groups.demo','name':'Demo','backgroundOpacity':.12,
 'apps':[{'desktop':'missing.desktop','label':'Missing'}]}
p.SETTINGS.set_string('groups',json.dumps({'demo':group}))
saved=p.SETTINGS.get_string('groups')
bind_preferences(builder,p.SETTINGS,window)
attach_previews(builder,p.SETTINGS,window,sys.argv[2])
stack=builder.get_object('settings_stack')
assert stack.get_pages().get_n_items()==3
assert [stack.get_pages().get_item(i).get_title() for i in range(3)]==['On the dock','When opened','Existing folders']
assert builder.get_object('enabled_row').get_next_sibling()==builder.get_object('customization_row')
check=builder.get_object('customization_row')
check.set_active(False)
assert not p.SETTINGS.get_boolean('customization')
check.set_active(True)
window.present()
def drain(milliseconds):
 loop=GLib.MainLoop()
 GLib.timeout_add(milliseconds,lambda:loop.quit() or False)
 loop.run()
drain(250)
dock,popup=window._settings_previews
assert not dock.tick
builder.get_object('orbit_speed_scale').set_value(60)
builder.get_object('hover_orbit_speed_scale').set_value(-999)
builder.get_object('hover_speed_scale').set_value(999)
assert p.SETTINGS.get_int('hover-speed')==999
assert builder.get_object('hover_speed_scale').get_adjustment().get_upper()==999
assert builder.get_object('hover_speed_scale').get_adjustment().get_lower()==-999
builder.get_object('hover_speed_scale').set_value(-999)
assert p.SETTINGS.get_int('hover-speed')==-999
assert p.SETTINGS.get_int('orbit-speed')==60 and p.SETTINGS.get_int('hover-orbit-speed')==-999
assert builder.get_object('hover_orbit_speed_scale').get_adjustment().get_lower()==-999
assert builder.get_object('hover_orbit_speed_scale').get_adjustment().get_upper()==999
drain(180)
assert dock.orbit>0 and dock.tick
p.SETTINGS.set_int('hover-orbit-speed',120)
p.SETTINGS.set_int('orbit-speed',0)
dock.hover_to(1)
phase=dock.orbit
drain(180)
assert dock.orbit>phase
dock.hover_to(0)
assert dock.orbit_velocity>0
drain(1800)
phase=dock.orbit
drain(100)
assert dock.orbit==phase and not dock.tick
p.SETTINGS.set_int('hover-orbit-speed',0)
drain(50)
before=next(item['size'] for item in dock.scene['commands'] if item['type']=='icon')
builder.get_object('mini_icon_size_scale').set_value(300)
builder.get_object('group_icon_size_scale').set_value(200)
drain(150)
after=next(item['size'] for item in dock.scene['commands'] if item['type']=='icon')
assert after>before
p.SETTINGS.set_string('hover-effect','rotate-cards')
dock.hover_to(1)
drain(650)
assert len([item for item in dock.scene['commands'] if item['type']=='icon'])==11
dock.hover_to(0)
stack.set_visible_child_name('popup')
p.SETTINGS.set_string('animation','sheet')
drain(250)
popup.replay()
drain(90)
assert popup.frame and popup.frame['triangles']
drain(1200)
assert not popup.phase and not popup.tick
p.SETTINGS.set_boolean('enabled',False)
assert not check.is_sensitive()
assert p.SETTINGS.get_string('groups')==saved
window.close()
assert not dock.tick and not popup.tick
print('GENERAL_SETTINGS_PASSED')
'''
        for desktop in ("gnome", "xfce"):
            with self.subTest(desktop=desktop):
                app = frontend(self, desktop) / "app"
                result=subprocess.run(["/usr/bin/python3","-c",code,str(app),desktop],
                    env=dict(os.environ,LANGUAGE="en",LC_ALL="C.UTF-8",GSETTINGS_BACKEND="memory"),
                    capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn("GENERAL_SETTINGS_PASSED",result.stdout)
                self.assertNotIn("Traceback",result.stderr)
                self.assertNotIn("CRITICAL",result.stderr)
