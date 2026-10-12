# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Validate Plasma mutations and missing-launcher cleanup with private settings."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from backend_build import frontend

ROOT = Path(__file__).resolve().parent.parent


class PlasmaServiceTests(unittest.TestCase):
    def setUp(self):
        frontend(self, "plasma")

    def test_worker_is_reused_and_closes_after_a_transport_failure(self):
        code = '''
import sys,time
sys.path.insert(0,sys.argv[1])
import core_bridge as bridge
request={'state':{'groups':{},'favorites':[],'undo':None},'command':{'operation':'reconcile'},'entries':{}}
bridge.invoke('transaction',request)
first=bridge._worker
bridge.invoke('transaction',request)
assert bridge._worker is first and first.process.poll() is None
first.process.kill();first.process.wait()
try:bridge.invoke('transaction',request)
except RuntimeError:pass
else:raise AssertionError('Expected a failed worker reply')
assert first.closed
assert bridge.invoke('transaction',request)['changed'] is False
assert bridge._worker is not first
bridge.close()
assert bridge._worker.closed and bridge._worker.process.poll() is not None
'''
        result = subprocess.run(['/usr/bin/python3','-c',code,str(ROOT/'build/plasma/contents/code')],
                                capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_failed_refresh_allows_a_later_change_to_recover(self):
        code = '''
import importlib.util,sys
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
spec=importlib.util.spec_from_file_location('source_service',sys.argv[2])
service=importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
state=service.FolderService.__new__(service.FolderService)
state.timer=123
state.load=lambda:None
def failure():raise RuntimeError('Qt worker stopped')
state.clean=failure
try:state.flush()
except RuntimeError:pass
else:raise AssertionError('Expected worker failure')
assert state.timer==0
with patch.object(service.GLib,'idle_add',return_value=124) as schedule:
 state.queue()
 schedule.assert_called_once_with(state.flush)
assert state.timer==124
state.clean=lambda:False
state.state=lambda:'recovered'
state.folder_revision=0
state.connection=None
state.last_state='previous'
assert state.flush()==service.GLib.SOURCE_REMOVE
assert state.timer==0 and state.last_state=='recovered' and state.folder_revision==1
print('REFRESH_RECOVERY_PASSED')
'''
        result = subprocess.run(["/usr/bin/python3", "-c", code, str(ROOT / "build/plasma/contents/code"),
                                 str(ROOT / "plasma/contents/code/service.py")],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REFRESH_RECOVERY_PASSED", result.stdout)

    def test_failed_core_returns_a_terminal_dbus_error(self):
        code = '''
import importlib.util,sys
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
spec=importlib.util.spec_from_file_location('source_service',sys.argv[2])
service=importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
FolderService,BUS=service.FolderService,service.BUS
def failure(*_args):raise RuntimeError('Qt worker stopped')
state=FolderService.__new__(FolderService)
state.edit=failure
state.library=SimpleNamespace(catalog=failure,pin=failure)
class Invocation:
 def __init__(self):self.reply=None
 def return_dbus_error(self,name,message):self.reply=(name,message)
 def return_value(self,value):raise AssertionError('Expected an error reply')
for method,args in [('Edit',['{}']),('ListFolders',[]),('PinFolder',['group:demo',True])]:
 invocation=Invocation()
 state.method(None,None,None,None,method,SimpleNamespace(unpack=lambda:args),invocation)
 assert invocation.reply==(BUS+'.CoreError','Qt worker stopped'),(method,invocation.reply)
print('CORE_ERROR_REPLY_PASSED')
'''
        result = subprocess.run(["/usr/bin/python3", "-c", code, str(ROOT / "build/plasma/contents/code"),
                                 str(ROOT / "plasma/contents/code/service.py")],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CORE_ERROR_REPLY_PASSED", result.stdout)

    def test_mutations_and_missing_launchers(self):
        code = r'''
import copy,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from service import FolderService,app_info
from gi.repository import GLib
apps=Path(GLib.get_user_data_dir())/'applications'
apps.mkdir(parents=True)
for name in ('a','b','c'):
 (apps/f'test.{name}.desktop').write_text(f'[Desktop Entry]\nType=Application\nName={name}\nExec=true\n')
group={'id':'local.groups.test','name':'Tools','icon':'folder','colors':['#40505c','#263d4a'],
       'apps':[{'desktop':f'test.{name}.desktop','label':name} for name in ('a','b','c')]}
from service import CONTENTS,SCHEMA,Gio
source=Gio.SettingsSchemaSource.new_from_directory(str(CONTENTS/'schemas'),Gio.SettingsSchemaSource.get_default(),False)
saved=Gio.Settings.new_full(source.lookup(SCHEMA,False),None,None)
offline=copy.deepcopy(group)
offline['apps'].append({'desktop':'test.removed.desktop','label':'Removed while offline','aliases':['test.a.desktop']})
saved.set_string('groups',json.dumps({'test':offline}))
saved.set_strv('plasma-favorites',['local.groups.test.desktop'])
state=FolderService()
assert len(state.groups['test']['apps'])==3
assert all(entry['desktop']!='test.removed.desktop' for entry in state.groups['test']['apps'])
rows=state.library.catalog();assert rows[0]['id']=='group:test' and rows[0]['pinned']
saved=state.settings.get_string('groups')
assert state.library.pin('group:test',False)
assert not state.library.pin('group:test',False)
assert not state.library.catalog()[0]['pinned']
assert state.library.pin('group:test',True)
assert state.settings.get_string('groups')==saved
grid=state.library.sources.grid
if grid:
 grid.set_strv('folder-children',['Test'])
 source=Gio.Settings.new_with_path('org.gnome.desktop.app-folders.folder',grid.props.path+'folders/Test/')
 source.set_string('name','Imported');source.set_boolean('translate',False)
 source.set_strv('apps',['test.a.desktop','test.b.desktop']);source.set_strv('categories',[])
 row=next(row for row in state.library.catalog() if row['id']=='gnome-grid:Test')
 assert state.library.pin(row['id'],True)
 assert len(state.library.catalog())==1
 grid.set_strv('folder-children',[])
 assert len(state.library.catalog())==1
 assert not state.library.pin('gnome-grid:Test',True)
state.load()
state.groups={'test':copy.deepcopy(group)}
state.favorites=['local.groups.test.desktop']
state.write()
assert state.edit({'operation':'move','desktop':'test.c.desktop','key':'test','before':'test.a.desktop'})
assert state.groups['test']['apps'][0]['desktop']=='test.c.desktop'
assert state.edit({'operation':'appearance','key':'test','property':'name','value':'Renamed'})
assert state.edit({'operation':'appearance','key':'test','property':'iconRotation','value':90})
assert state.edit({'operation':'appearance','key':'test','property':'alwaysStack','value':True})
assert not state.edit({'operation':'appearance','key':'test','property':'iconRotation','value':True})
assert not state.edit({'operation':'appearance','key':'test','property':'iconRotation','value':-1})
assert state.edit({'operation':'undo'})
assert state.groups['test']['name']=='Renamed'
assert state.groups['test']['iconRotation']==90 and state.groups['test']['alwaysStack']
assert state.groups['test']['apps'][0]['desktop']=='test.a.desktop'
assert state.edit({'operation':'extract','desktop':'test.c.desktop'})
assert state.favorites==['local.groups.test.desktop','test.c.desktop']
assert state.edit({'operation':'move','desktop':'test.c.desktop','key':'test'})
(apps/'test.c.desktop').unlink()
assert state.clean()
assert len(state.groups['test']['apps'])==2
assert not state.edit({'operation':'move','desktop':'test.c.desktop','key':'test'})
(apps/'test.b.desktop').unlink()
assert state.clean()
assert state.groups=={}
assert state.favorites==['test.a.desktop']
(apps/'test.b.desktop').symlink_to(apps/'removed.desktop')
assert app_info('test.b.desktop') is None
assert not state.edit({'operation':'create','desktop':'test.b.desktop','target':'test.a.desktop'})
assert not state.edit([])
assert not state.edit({'operation':'pin','desktop':'/tmp/untrusted.desktop'})
state.close()
assert state.timer==0
print('Plasma service checks passed')
'''
        with tempfile.TemporaryDirectory(prefix="dock-folders-model-") as directory:
            env = dict(os.environ, GSETTINGS_BACKEND="memory", XDG_DATA_HOME=directory,
                       XDG_CONFIG_HOME=str(Path(directory) / "config"), GIO_USE_VFS="local")
            result = subprocess.run(["/usr/bin/python3", "-c", code, str(ROOT / "build/plasma/contents/code")],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Plasma service checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
