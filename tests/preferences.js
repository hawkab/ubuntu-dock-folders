// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import GLib from 'gi://GLib';

/** Exercise the extension's actual preference entry point in an isolated process. */
const directory = ARGV[0];
Gio.resources_register(Gio.Resource.load('/usr/share/gnome-shell/org.gnome.Shell.Extensions.src.gresource'));
const {default: Preferences} = await import(Gio.File.new_for_path(directory + '/prefs.js').get_uri());
const metadata = JSON.parse(new TextDecoder().decode(Gio.File.new_for_path(directory + '/metadata.json').load_contents(null)[1]));
metadata.path = directory;
metadata.dir = Gio.File.new_for_path(directory);
Adw.init();
const window = new Adw.PreferencesWindow();
const preferences = new Preferences(metadata);
preferences.fillPreferencesWindow(window);
const widgets = [];
function walk(widget) {
    widgets.push(widget);
    for (let child=widget.get_first_child(); child; child=child.get_next_sibling()) walk(child);
}
walk(window);
const settings = window._settings;
const row = widgets.find(widget => widget instanceof Adw.ComboRow && widget.title === 'Opening and closing animation');
for (const [index,mode] of ['none','fade','scale','flow','lamp','fold','sheet','unfold'].entries()) {
    row.selected = index;
    if (settings.get_string('animation') !== mode) throw new Error('Preference did not persist: '+mode);
}
const slider = widgets.find(widget => widget instanceof Gtk.Scale && widget.get_buildable_id() === 'popup_icon_size_scale');
slider.set_value(80);
if (settings.get_int('popup-icon-size') !== 80) throw new Error('Icon size did not persist');
const find = id => widgets.find(widget => widget.get_buildable_id?.() === id);
if (Gio.ListModel.prototype.get_n_items.call(find('settings_stack').get_pages())!==3)
    throw new Error('Expected three settings tabs');
if (find('customization_row').title!=='Allow customizing each folder separately'
    || find('enabled_row').get_next_sibling()!==find('customization_row'))
    throw new Error('Customization is not immediately below the main switch');
find('customization_row').active=false;
if(settings.get_boolean('customization'))throw new Error('Customization checkbox did not persist');
find('customization_row').active=true;
if (find('blur_strength_scale')) throw new Error('Blur remains in general settings');
if (find('glass_row')) throw new Error('Legacy glass switch remains visible');
find('hover_rotate_check').active = true;
find('hover_cards_check').active = true;
if (settings.get_string('hover-effect') !== 'rotate-cards') throw new Error('Hover controls are not independent');
find('hover_angle_scale').set_value(75);
find('hover_speed_scale').set_value(10);
find('mini_icon_size_scale').set_value(300);
find('group_icon_size_scale').set_value(200);
if (settings.get_int('hover-angle') !== 75 || settings.get_int('hover-speed') !== 10
    || settings.get_int('mini-icon-size') !== 300 || settings.get_int('group-icon-size') !== 200)
    throw new Error('Hover sliders did not persist');
find('hover_rotate_check').active = false;
if (settings.get_string('hover-effect') !== 'cards' || find('hover_angle_row').sensitive)
    throw new Error('Card-only hover did not disable the rotation angle');
window.present();
const drain=milliseconds => {
    const loop=new GLib.MainLoop(null,false);
    GLib.timeout_add(GLib.PRIORITY_DEFAULT,milliseconds,()=>{loop.quit();return GLib.SOURCE_REMOVE;});
    loop.run();
};
drain(180);
const before=window._settingsPreviews[0].scene.commands.find(item=>item.type==='icon').size;
find('group_icon_size_scale').set_value(80);
find('mini_icon_size_scale').set_value(80);
drain(180);
if(window._settingsPreviews[0].scene.commands.find(item=>item.type==='icon').size>=before)
    throw new Error('Dock preview did not update');
find('settings_stack').set_visible_child_name('popup');
drain(180);
settings.set_string('animation','sheet');
drain(100);
window._settingsPreviews[1].replay();
drain(70);
if(!window._settingsPreviews[1].frame?.triangles.length)throw new Error('Animation preview did not draw');
drain(1200);
if(window._settingsPreviews[1].tick)throw new Error('Preview animation kept ticking');
const appDirectory=GLib.build_filenamev([GLib.get_user_data_dir(),'applications']);
GLib.mkdir_with_parents(appDirectory,0o755);
for(const id of ['a','b','c','d'])GLib.file_set_contents(appDirectory+'/test.'+id+'.desktop',
    '[Desktop Entry]\nType=Application\nName='+id.toUpperCase()+'\nExec=true\nIcon=utilities-terminal\nCategories=Utility;\n');
const savedGroup={id:'local.groups.Tools',name:'Tools',dockColor:'#123456',blurStrength:23,
    apps:['a','b'].map(id=>({desktop:'test.'+id+'.desktop',label:id.toUpperCase()}))};
settings.set_string('groups',JSON.stringify({tools:savedGroup}));
const favorites=new Gio.Settings({schema_id:'org.gnome.shell'});
favorites.set_strv('favorite-apps',[]);
const grid=new Gio.Settings({schema_id:'org.gnome.desktop.app-folders'});
grid.set_strv('folder-children',['Imported']);
const source=new Gio.Settings({schema_id:'org.gnome.desktop.app-folders.folder',path:grid.path+'folders/Imported/'});
source.set_string('name','Imported');
source.set_boolean('translate',false);
source.set_strv('apps',['test.c.desktop','test.d.desktop']);
source.set_strv('categories',[]);source.set_strv('excluded-apps',[]);
find('settings_stack').set_visible_child_name('folders');
drain(250);
const pinButton=id=>{
    const current=[];
    const collect=widget=>{current.push(widget);for(let child=widget.get_first_child();child;child=child.get_next_sibling())collect(child);};
    collect(window);
    const row=current.find(widget=>widget.get_name()===id);
    if(!row)throw new Error('Missing folder row '+id);
    const children=[];const visit=widget=>{children.push(widget);for(let child=widget.get_first_child();child;child=child.get_next_sibling())visit(child);};
    visit(row);return children.find(widget=>widget instanceof Gtk.ToggleButton);
};
pinButton('group:tools').active=true;drain(120);
if(!favorites.get_strv('favorite-apps').includes('local.groups.Tools.desktop'))throw new Error('Folder did not pin');
favorites.set_strv('favorite-apps',[]);drain(120);
if(pinButton('group:tools').active)throw new Error('Pin state did not refresh');
if(JSON.stringify(JSON.parse(settings.get_string('groups')).tools)!==JSON.stringify(savedGroup))throw new Error('Pinning changed appearance');
pinButton('gnome-grid:Imported').active=true;drain(150);
const imported=Object.values(JSON.parse(settings.get_string('groups'))).find(group=>group.gridFolder==='Imported');
if(!imported || imported.apps.length!==2 || !favorites.get_strv('favorite-apps').includes(imported.id+'.desktop'))
    throw new Error('Source folder did not import');
find('settings_stack').set_visible_child_name('dock');drain(100);
const disposedPreview=window._settingsPreviews[0];
const retainedScene=disposedPreview.scene;
window.destroy();
settings.set_int('group-icon-size',111);
favorites.set_strv('favorite-apps',[]);
grid.set_strv('folder-children',[]);
drain(70);
if(disposedPreview.scene!==retainedScene || disposedPreview.tick)
    throw new Error('Destroyed preferences retained settings listeners or animation callbacks');
print('GNOME preference entry point passed');
