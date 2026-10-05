# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Check localization and settings behavior without changing the desktop."""

import ast
import gettext
import json
import os
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILT = ROOT / "build/extension"
LANGUAGES = (ROOT / "po/LINGUAS").read_text().split()


class LocalizationTests(unittest.TestCase):
    def test_catalogs_are_complete(self):
        english = gettext.translation("ubuntu-dock-folders", str(BUILT / "locale"), ["en"])
        expected = {key for key in english._catalog if isinstance(key, str) and key}
        source_strings = set()
        for path in (ROOT / "extension").rglob("*"):
            if path.suffix in {".js", ".py"}:
                for match in re.finditer(r"""_\(((["'])(.*?)\2)\)""", path.read_text()):
                    source_strings.add(ast.literal_eval(match[1]))
        for element in ET.parse(ROOT / "extension/preferences.ui").iter():
            if element.get("translatable") == "yes":
                source_strings.add(element.text)
        self.assertFalse(source_strings - expected, source_strings - expected)
        for language in LANGUAGES:
            with self.subTest(language=language):
                translated = gettext.translation(
                    "ubuntu-dock-folders", str(BUILT / "locale"), [language]
                )
                self.assertEqual(
                    expected, {key for key in translated._catalog if isinstance(key, str) and key}
                )
                self.assertTrue(all(translated.gettext(key) for key in expected))

    def test_system_language_and_rtl(self):
        code = """
import json,sys
sys.path.insert(0, sys.argv[1])
import preferences as p
from i18n import set_ui_direction
p.Adw.init()
set_ui_direction()
builder=p.Gtk.Builder()
builder.set_translation_domain('ubuntu-dock-folders')
builder.add_from_file(str(p.ROOT/'preferences.ui'))
print(json.dumps({'title':builder.get_object('preferences_window').get_title(),
 'animation':builder.get_object('animation_row').get_model().get_string(0),
 'rtl':p.Gtk.Widget.get_default_direction()==p.Gtk.TextDirection.RTL}))
builder.get_object('preferences_window').destroy()
"""
        for language in LANGUAGES + ["pt_BR", "zh_CN", "hi_IN", "ms_MY", "tr_TR", "ur_PK"]:
            with self.subTest(language=language):
                env = dict(
                    os.environ, LANGUAGE=language, LC_ALL="C.UTF-8", GSETTINGS_BACKEND="memory"
                )
                result = subprocess.run(
                    ["/usr/bin/python3", "-c", code, str(BUILT / "app")],
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                value = json.loads(result.stdout)
                translator = gettext.translation(
                    "ubuntu-dock-folders", str(BUILT / "locale"), [language]
                )
                self.assertEqual(value["title"], translator.gettext("Dock folders"))
                self.assertEqual(value["animation"], translator.gettext("Scale"))
                self.assertEqual(value["rtl"], language.split("_")[0] in {"ar", "ur"})


class PreferencesTests(unittest.TestCase):
    def test_grid_folder_status_tracks_unpinning_and_repinning(self):
        code = """
import json,sys
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import grid_folders as g
g.Adw.init()
g.GRID.set_strv('folder-children',['Test'])
folder={'name':'Test folder','apps':[{'desktop':'a.desktop'},{'desktop':'b.desktop'}]}
linked={'id':'local.groups.Linked','name':'Custom folder','gridFolder':'Test',
 'apps':[{'desktop':'a.desktop','label':'Custom A','aliases':['alias-a.desktop']},
         {'desktop':'b.desktop','label':'B'}],
 'colors':['#123456','#abcdef'],'dockOpacity':.2,'popupOpacity':.6,
 'wallpaper':'file:///tmp/custom-wallpaper.png'}
saved=json.dumps({'linked':linked})
g.SETTINGS.set_string('groups',saved)
g.SHELL.set_strv('favorite-apps',['files.desktop','alias-a.desktop'])
app=g.GridFolders()
app.register(None)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from walk(child)
  child=child.get_next_sibling()
def drain():
 context=g.GLib.MainContext.default()
 while context.pending(): context.iteration(False)
with patch.object(g,'read_folder',return_value=folder), \
     patch.object(g.Adw.ApplicationWindow,'present'):
 app.activate_window(app)
 window=app.get_windows()[0]
 button=next(w for w in walk(window) if isinstance(w,g.Gtk.Button)
             and w.get_label()=='Pin to dock')
 assert button.get_sensitive()
 g.SHELL.set_strv('favorite-apps',['files.desktop',linked['id']+'.desktop'])
 drain()
 assert button.get_label()=='Pinned' and not button.get_sensitive()
 g.SHELL.set_strv('favorite-apps',['files.desktop','alias-a.desktop'])
 drain()
 assert button.get_label()=='Pin to dock' and button.get_sensitive()
 button.emit('clicked')
 drain()
 assert g.SHELL.get_strv('favorite-apps')==['files.desktop',linked['id']+'.desktop']
 assert g.SETTINGS.get_string('groups')==saved
 assert button.get_label()=='Pinned' and not button.get_sensitive()
 assert not g.pin_folder('Test')
 g.SETTINGS.set_string('groups','{}')
 drain()
 assert button.get_label()=='Pin to dock' and button.get_sensitive()
 g.SETTINGS.set_string('groups',saved)
 drain()
 assert button.get_label()=='Pinned' and not button.get_sensitive()
 window.emit('close-request')
 g.SHELL.set_strv('favorite-apps',['files.desktop'])
 drain()
 assert button.get_label()=='Pinned'
 window.destroy()
print('OK')
"""
        result = subprocess.run(
            ["/usr/bin/python3", "-c", code, str(BUILT / "app")],
            env=dict(os.environ, GSETTINGS_BACKEND="memory", LANGUAGE="en", LC_ALL="C.UTF-8"),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.stdout.strip(), "OK")

    def test_grid_import_respects_exclusions_and_preserves_launcher_metadata(self):
        code = """
import json,sys
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import grid_folders as g
class App:
 def __init__(self,id): self.id=id
 def get_id(self): return self.id
 def should_show(self): return True
 def get_name(self): return self.id.upper()
 def get_categories(self): return 'Utility;'
g.GRID.set_strv('folder-children',['Test'])
s=g.Gio.Settings.new_with_path('org.gnome.desktop.app-folders.folder',g.GRID.props.path+'folders/Test/')
s.set_string('name','Test folder');s.set_boolean('translate',False)
s.set_strv('apps',['a','a','b']);s.set_strv('categories',['Utility']);s.set_strv('excluded-apps',['c','d'])
previous={'id':'local.groups.Old','name':'Old','apps':[
 {'desktop':'a','label':'Custom A','aliases':['alias-a'],'wmClasses':['ClassA']},
 {'desktop':'b','label':'B'},{'desktop':'c','label':'C'}]}
g.SETTINGS.set_string('groups',json.dumps({'old':previous}))
shell=g.Gio.Settings.new('org.gnome.shell')
shell.set_strv('favorite-apps',['local.groups.Old.desktop','b','files'])
with patch.object(g.Gio.AppInfo,'get_all',return_value=[App(id) for id in ['a','b','c','d']]):
 assert [e['desktop'] for e in g.read_folder('Test')['apps']]==['a','b']
 assert g.read_folder('invalid/path') is None
 assert g.pin_folder('Test')
 assert not g.pin_folder('Test')
value=g.groups();assert len(value)==1
folder=next(iter(value.values()))
assert folder['gridFolder']=='Test'
assert folder['apps'][0]==previous['apps'][0]
assert shell.get_strv('favorite-apps')==['c','files',folder['id']+'.desktop']
print('OK')
"""
        result = subprocess.run(
            ["/usr/bin/python3", "-c", code, str(BUILT / "app")],
            env=dict(os.environ, GSETTINGS_BACKEND="memory", LANGUAGE="en"),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.stdout.strip(), "OK")

    def test_autosave_preserves_membership_and_opacity_modes(self):
        code = """
import json,sys
sys.path.insert(0,sys.argv[1])
import preferences as p
p.Adw.init()
group={'id':'local.groups.Test','name':'Original','colors':['#000000','#3584e4'],
 'apps':[{'desktop':'a.desktop','label':'A'},{'desktop':'b.desktop','label':'B'}],
 'popupOpacity':.9,'glassOpacity':.4}
p.SETTINGS.set_string('groups',json.dumps({'test':group}))
app=p.Preferences('test')
window=app.group_window(group)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from walk(child)
  child=child.get_next_sibling()
name=next(w for w in walk(window) if isinstance(w,p.Adw.EntryRow))
name.set_text('Renamed')
current=p.groups()
current['test']['apps'].append({'desktop':'c.desktop','label':'C'})
p.SETTINGS.set_string('groups',json.dumps(current))
app.save('dockOpacity',.2)
p.SETTINGS.set_boolean('glass',True)
app.refresh_previews(p.groups()['test'])
app.popup_adjustment.set_value(70)
value=p.groups()['test']
assert value['name']=='Renamed'
assert len(value['apps'])==3
assert value['popupOpacity']==.9 and value['glassOpacity']==.3
assert value['dockOpacity']==.2
filters,_=p.wallpaper_filters()
assert filters.get_n_items()==8
window.destroy()
print('OK')
"""
        env = dict(os.environ, LANGUAGE="en", LC_ALL="C.UTF-8", GSETTINGS_BACKEND="memory")
        result = subprocess.run(
            ["/usr/bin/python3", "-c", code, str(BUILT / "app")],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.stdout.strip(), "OK")


if __name__ == "__main__":
    unittest.main()
