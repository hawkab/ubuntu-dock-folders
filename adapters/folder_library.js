// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {folderCatalog,folderCommand} from '../core/folders.js';
import {transact} from '../core/engine.js';
import {GnomeFolders,applicationEntries,settings} from './folder_sources.js';

/** Adapt shared folder selection to GNOME's settings and favorites. */
export class FolderLibrary {
    constructor(store) {
        this.store=store;
        this.favoritesStore=settings('org.gnome.shell');
        this.sources=new GnomeFolders();
    }
    favorites() { return this.favoritesStore?.get_strv('favorite-apps') || []; }
    catalog() {
        return folderCatalog({groups:JSON.parse(this.store.get_string('groups')),favorites:this.favorites(),
            sources:this.sources.read(),entries:applicationEntries()});
    }
    pin(id,pinned) {
        if(!this.favoritesStore)return false;
        const command=folderCommand({catalog:this.catalog(),id,pinned});
        if(!command)return false;
        const groups=JSON.parse(this.store.get_string('groups'));
        const entries=Object.fromEntries(Object.entries(applicationEntries()).map(([id,entry])=>
            [id,{desktop:id,label:entry.label}]));
        const result=transact({state:{groups,favorites:this.favorites(),undo:null},command,entries,
            token:GLib.uuid_string_random().replaceAll('-','').slice(0,12)});
        if(!result.changed)return false;
        if(JSON.stringify(result.state.groups)!==JSON.stringify(groups))
            this.store.set_string('groups',JSON.stringify(result.state.groups));
        if(JSON.stringify(result.state.favorites)!==JSON.stringify(this.favorites()))
            this.favoritesStore.set_strv('favorite-apps',result.state.favorites);
        for(const store of [this.store,this.favoritesStore])if(store.get_has_unapplied())store.apply();
        Gio.Settings.sync();return true;
    }
}
