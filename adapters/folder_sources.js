// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';

/** Open optional desktop schemas without requiring GNOME Shell in preferences. */
export function settings(schema, path=null) {
    const declaration=Gio.SettingsSchemaSource.get_default()?.lookup(schema,true);
    return declaration ? Gio.Settings.new_full(declaration,null,path) : null;
}

/** Read installed application metadata for the common folder catalog. */
export function applicationEntries() {
    return Object.fromEntries(Gio.AppInfo.get_all().filter(info=>info.get_id() && !info.get_id().startsWith('local.groups.'))
        .map(info=>[info.get_id(),{desktop:info.get_id(),label:info.get_name(),visible:info.should_show(),
            categories:(info instanceof GioUnix.DesktopAppInfo ? info.get_categories() || '' : '').split(';')}]));
}

/** Read source folders and release all watches when the settings window closes. */
export class GnomeFolders {
    constructor() { this.grid=settings('org.gnome.desktop.app-folders');this.signals=[];this.folders=[]; }
    read() {
        if(!this.grid)return [];
        return this.grid.get_strv('folder-children').filter(id=>id && !id.includes('/')).flatMap(id=>{
            const folder=settings('org.gnome.desktop.app-folders.folder',this.grid.path+'folders/'+id+'/');
            if(!folder)return [];
            let name=folder.get_string('name');
            if(folder.get_boolean('translate') && !name.includes('/')) {
                for(const directory of GLib.get_system_data_dirs()) {
                    const file=new GLib.KeyFile();
                    try {
                        file.load_from_file(directory+'/desktop-directories/'+name,GLib.KeyFileFlags.NONE);
                        name=file.get_locale_string('Desktop Entry','Name',null);break;
                    }catch(_exception) {}
                }
            }
            return [{id,name,apps:folder.get_strv('apps'),categories:folder.get_strv('categories'),
                excludedApps:folder.get_strv('excluded-apps')}];
        });
    }
    watch(changed) {
        this.close();
        this.changed=changed;
        if(!this.grid)return;
        this.signals.push([this.grid,this.grid.connect('changed::folder-children',()=>this.rebind())]);
        this.rebind();
    }
    rebind() {
        for(const [store,signal] of this.folders)store.disconnect(signal);
        this.folders=this.read().map(source=>{
            const store=settings('org.gnome.desktop.app-folders.folder',this.grid.path+'folders/'+source.id+'/');
            return [store,store.connect('changed',()=>this.changed())];
        });
        this.changed();
    }
    close() {
        for(const [store,signal] of [...this.signals,...this.folders])store.disconnect(signal);
        this.signals=[];this.folders=[];this.changed=null;
    }
}
