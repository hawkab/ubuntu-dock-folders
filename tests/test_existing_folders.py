# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Verify shared folder selection and native GTK pin controls with private settings."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from backend_build import frontend

ROOT = Path(__file__).resolve().parent.parent

SETUP = r'''
import json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import existing_folders as g
from folder_sources import settings
apps=Path(sys.argv[2])/'applications';apps.mkdir()
for name in ('a','b','c','d'):
 (apps/f'test.{name}.desktop').write_text(f'[Desktop Entry]\nType=Application\nName={name.upper()}\nExec=true\nCategories=Utility;\n')
patch.object(g.Gio.AppInfo,'get_all',return_value=[g.Gio.DesktopAppInfo.new(f'test.{name}.desktop') for name in ('a','b','c','d')]).start()
grid=settings('org.gnome.desktop.app-folders')
grid.set_strv('folder-children',['Test'])
source=settings('org.gnome.desktop.app-folders.folder',grid.props.path+'folders/Test/')
source.set_string('name','Test folder');source.set_boolean('translate',False)
source.set_strv('apps',['test.a.desktop','test.a.desktop','test.b.desktop'])
source.set_strv('categories',['Utility']);source.set_strv('excluded-apps',['test.c.desktop','test.d.desktop'])
shell=settings('org.gnome.shell')
group={'id':'local.groups.Linked','name':'Custom folder','gridFolder':'Test',
 'apps':[{'desktop':'test.a.desktop','label':'Custom A','aliases':['alias-a.desktop']},
         {'desktop':'test.b.desktop','label':'B'}],
 'colors':['#123456','#abcdef'],'dockOpacity':.2,'blurStrength':25,
 'wallpaper':'file:///tmp/custom-wallpaper.png'}
g.SETTINGS.set_string('groups',json.dumps({'linked':group}))
g.SETTINGS.set_strv('plasma-favorites',['test.c.desktop'])
g.SETTINGS.set_strv('xfce-favorites',['test.d.desktop'])
shell.set_strv('favorite-apps',['test.a.desktop','alias-a.desktop'])
'''


class ExistingFolderTests(unittest.TestCase):
    def run_check(self, code, desktop="gnome"):
        with tempfile.TemporaryDirectory(prefix="dock-folder-library-") as directory:
            env=dict(os.environ,GSETTINGS_BACKEND="memory",LANGUAGE="en",LC_ALL="C.UTF-8",
                     XDG_DATA_HOME=directory,DOCK_FOLDERS_DESKTOP=desktop,XDG_CURRENT_DESKTOP=desktop.upper())
            app=frontend(self, desktop) / "app"
            result=subprocess.run(["/usr/bin/python3","-c",SETUP+code,str(app),directory],
                                  env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("OK",result.stdout)

    def test_library_is_independent_of_desktop_and_preserves_saved_folders(self):
        self.run_check(r'''
core=g.CoreRuntime(g.ROOT)
saved=g.SETTINGS.get_string('groups')
for desktop in ('gnome','plasma','xfce'):
 library=g.FolderLibrary(g.SETTINGS,desktop,core.call)
 before=[shell.get_strv('favorite-apps'),g.SETTINGS.get_strv('plasma-favorites'),g.SETTINGS.get_strv('xfce-favorites')]
 rows=library.catalog();assert len(rows)==1 and rows[0]['id']=='group:linked'
 assert not rows[0]['pinned']
 assert library.pin('group:linked',True)
 assert not library.pin('group:linked',True)
 assert library.catalog()[0]['pinned']
 assert library.pin('group:linked',False)
 assert not library.pin('group:linked',False)
 assert library.pin('group:linked',True)
 assert g.SETTINGS.get_string('groups')==saved
 after=[shell.get_strv('favorite-apps'),g.SETTINGS.get_strv('plasma-favorites'),g.SETTINGS.get_strv('xfce-favorites')]
 index=('gnome','plasma','xfce').index(desktop)
 for other in range(3):
  if other!=index: assert before[other]==after[other]
 library.sources.close()
with patch('folder_sources.settings',return_value=None):
 library=g.FolderLibrary(g.SETTINGS,'xfce',core.call)
 assert library.sources.read()==[] and library.catalog()[0]['pinned']
 library.sources.watch(lambda:None);library.sources.close()
core.close();print('OK')
''')

    def test_import_uses_exclusions_and_keeps_launcher_metadata(self):
        self.run_check(r'''
group.pop('gridFolder')
group['apps'].append({'desktop':'test.c.desktop','label':'C'})
g.SETTINGS.set_string('groups',json.dumps({'old':group}))
shell.set_strv('favorite-apps',[group['id']+'.desktop','test.b.desktop','files.desktop'])
core=g.CoreRuntime(g.ROOT);library=g.FolderLibrary(g.SETTINGS,'gnome',core.call)
row=next(row for row in library.catalog() if row['id']=='gnome-grid:Test')
assert [app['desktop'] for app in row['apps']]==['test.a.desktop','test.b.desktop']
assert not library.pin('gnome-grid:invalid/path',True)
assert library.pin(row['id'],True)
value=json.loads(g.SETTINGS.get_string('groups'));assert len(value)==1
folder=next(iter(value.values()))
assert folder['gridFolder']=='Test' and folder['apps'][0]==group['apps'][0]
assert shell.get_strv('favorite-apps')==['test.c.desktop','files.desktop',folder['id']+'.desktop']
assert len(library.catalog())==1
core.close();print('OK')
''')

    def test_native_selector_tracks_pin_changes_and_cleans_watchers(self):
        code=r'''
g.Adw.init()
from preferences import Preferences
app=Preferences(None,tab="folders");app.register(None)
def drain():
 context=g.GLib.MainContext.default()
 while context.pending():context.iteration(False)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from walk(child);child=child.get_next_sibling()
def button():
 return next(widget for widget in walk(window) if isinstance(widget,g.Gtk.ToggleButton) and widget.get_label() in ('Pinned','Pin to panel'))
app.activate_window(app);window=app.get_windows()[0];drain()
assert window.get_visible() and not button().get_active()
assert button().get_sensitive()
button().set_active(True);drain();assert button().get_active()
desktop=sys.argv[3] if len(sys.argv)>3 else 'gnome'
store=shell if desktop=='gnome' else g.SETTINGS
key='favorite-apps' if desktop=='gnome' else 'xfce-favorites'
store.set_strv(key,[]);drain();assert not button().get_active()
button().set_active(True);drain();assert button().get_label()=='Pinned'
button().set_active(False);drain();assert not button().get_active()
assert json.loads(g.SETTINGS.get_string('groups'))['linked']==group
window.emit('close-request');store.set_strv(key,[]);drain();window.destroy()
print('OK')
'''
        for desktop in ("gnome","xfce"):
            with self.subTest(desktop=desktop):
                self.run_check(code.replace("desktop=sys.argv[3] if len(sys.argv)>3 else 'gnome'",f"desktop={desktop!r}"),desktop)
