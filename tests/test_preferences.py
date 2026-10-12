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
    def test_every_desktop_adapter_has_valid_translations(self):
        from scripts.localization import validate
        self.assertEqual(validate()["languages"], len(LANGUAGES))

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
from settings import ROOT
builder.add_from_file(str(ROOT/'preferences.ui'))
from preferences_binding import bind_preferences
bind_preferences(builder,p.SETTINGS,builder.get_object('preferences_window'))
folder={'id':'local.groups.Test','name':'Test','colors':['#000000','#3584e4'],
 'apps':[{'desktop':'a.desktop','label':'A'},{'desktop':'b.desktop','label':'B'}]}
p.SETTINGS.set_string('groups',json.dumps({'test':folder}))
app=p.Preferences('test')
window=app.group_window(folder)
dialog=app.confirm_apply_to_all(window)
print(json.dumps({'title':builder.get_object('preferences_window').get_title(),
 'animation':builder.get_object('animation_row').get_model().get_string(0),
 'customization':builder.get_object('customization_row').get_title(),
 'tabs':[builder.get_object('settings_stack').get_pages().get_item(i).get_title() for i in range(3)],
 'bulk_title':dialog.get_heading(),'bulk_body':dialog.get_body(),
 'apply':dialog.get_response_label('apply'),'cancel':dialog.get_response_label('cancel'),
 'rtl':p.Gtk.Widget.get_default_direction()==p.Gtk.TextDirection.RTL}))
dialog.response('cancel')
window.destroy()
builder.get_object('preferences_window').destroy()
"""
        for language in LANGUAGES + ["pt_BR", "zh_CN", "hi_IN", "ms_MY", "tr_TR", "ur_PK"]:
            with self.subTest(language=language):
                env = dict(
                    os.environ, LANGUAGE=language, LC_ALL="en_US.UTF-8", GSETTINGS_BACKEND="memory"
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
                self.assertEqual(value["animation"], translator.gettext("No animation"))
                self.assertEqual(value["customization"],translator.gettext("Allow customizing each folder separately"))
                self.assertEqual(value["tabs"],[translator.gettext(item) for item in ("On the dock","When opened","Existing folders")])
                for field, message in (("bulk_title", "Replace other folders’ appearance?"),
                                       ("bulk_body", "This will overwrite the custom appearance settings of all other folders. Names and applications will stay the same."),
                                       ("apply", "Apply to all folders"), ("cancel", "Cancel")):
                    self.assertEqual(value[field], translator.gettext(message))
                self.assertEqual(value["rtl"], language.split("_")[0] in {"ar", "ur"})


class PreferencesTests(unittest.TestCase):
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
assert window.get_title().endswith(' — Original')
name.set_text('Renamed')
assert window.get_title().endswith(' — Renamed')
assert app.get_application_id() == 'io.github.hawkab.UbuntuDockFolders'
assert p.Gtk.Window.get_default_icon_name() == app.get_application_id()
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
assert value['popupOpacity']==.9 and value['glassOpacity']==.4 and value['backgroundOpacity']==.3
assert value['dockOpacity']==.2
for blur in (0,1,25,50,100):
 p.SETTINGS.set_int('blur-strength',blur)
 app.refresh_previews(p.groups()['test'])
 assert app.popup_adjustment.get_value()==70
 assert app.folder_previews[1].appearance['blurAmount']==blur/100
from folder_wallpaper import wallpaper_filters
filters,_=wallpaper_filters()
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
