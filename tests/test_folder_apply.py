# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check confirmation, cancellation and bulk appearance without changing user settings."""

import os
import subprocess
import unittest
from pathlib import Path
from backend_build import frontend

ROOT = Path(__file__).resolve().parent.parent


class FolderApplyTests(unittest.TestCase):
    def test_confirmed_apply_preserves_names_apps_and_favorites(self):
        code = '''
import json,sys
sys.path.insert(0,sys.argv[1])
import preferences as p
p.Adw.init()
source={'id':'local.groups.One','name':'Source','colors':['#000000','#3584e4'],
 'apps':[{'desktop':'a.desktop','label':'A'},{'desktop':'b.desktop','label':'B'}],
 'backgroundOpacity':.18,'blurStrength':37,'dockOpacity':.25,'showLabel':True,
 'iconRotation':120,'alwaysStack':True,'wallpaper':'/tmp/source.png'}
target={'id':'local.groups.Two','name':'Target','colors':['#000000','#123456'],
 'apps':[{'desktop':'c.desktop','label':'C'},{'desktop':'d.desktop','label':'D'}],
 'wallpaper':'/tmp/target.bmp','wallpaperName':'target.bmp','blurStrength':100}
p.SETTINGS.set_string('groups',json.dumps({'one':source,'two':target}))
p.SETTINGS.set_strv('plasma-favorites',['local.groups.Two.desktop'])
shell=p.Gio.Settings.new('org.gnome.shell')
shell.set_strv('favorite-apps',['local.groups.One.desktop'])
app=p.Preferences('one')
window=app.group_window(source)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from walk(child)
  child=child.get_next_sibling()
button=next(w for w in walk(window) if w.get_name()=='apply-appearance-to-all')
assert button.get_label()=='Apply to all folders…'
before=p.SETTINGS.get_string('groups')
dialog=app.confirm_apply_to_all(window)
assert dialog.get_default_response()==dialog.get_close_response()=='cancel'
assert dialog.get_response_appearance('apply')==p.Adw.ResponseAppearance.DESTRUCTIVE
assert 'overwrite' in dialog.get_body() and 'Names and applications' in dialog.get_body()
assert p.SETTINGS.get_string('groups')==before
dialog.response('cancel')
assert p.SETTINGS.get_string('groups')==before
dialog=app.confirm_apply_to_all(window)
app.save('blurStrength',75)
dialog.response('apply')
current=p.groups()
assert current['one']==dict(source,blurStrength=75)
copied=current['two']
assert copied['name']=='Target' and copied['id']==target['id'] and copied['apps']==target['apps']
assert copied['blurStrength']==75 and copied['backgroundOpacity']==.18
assert copied['showLabel'] and copied['alwaysStack'] and copied['iconRotation']==120
assert copied['wallpaper']=='/tmp/source.png' and copied['wallpaperName']==''
assert shell.get_strv('favorite-apps')==['local.groups.One.desktop']
assert p.SETTINGS.get_strv('plasma-favorites')==['local.groups.Two.desktop']
dialog=app.confirm_apply_to_all(window)
p.SETTINGS.set_string('groups',json.dumps({'two':copied}))
dialog.response('apply')
assert p.groups()=={'two':copied}
window.destroy()
print('OK')
'''
        for desktop in ("gnome", "xfce"):
            with self.subTest(desktop=desktop):
                app = frontend(self, desktop) / "app"
                result = subprocess.run(["/usr/bin/python3", "-c", code, str(app)],
                                        env=dict(os.environ, LANGUAGE="en", LC_ALL="C.UTF-8", GSETTINGS_BACKEND="memory"),
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), "OK")
