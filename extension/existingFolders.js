// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {FolderLibrary} from './adapters/folder_library.js';
import {onWindowClose} from './windowLifecycle.js';

/** Embed live folder pin controls; fetch catalogs only while the tab is mapped. */
export function attachExistingFolders(builder,settings,window,translate) {
    const group=builder.get_object('existing_folders_group'),library=new FolderLibrary(settings);
    let rows=[],timer=0,closed=false,error='';
    const refresh=()=>{
        timer=0;
        if(closed || !group.get_mapped())return GLib.SOURCE_REMOVE;
        for(const row of rows)group.remove(row);
        rows=[];
        const add=row=>{group.add(row);rows.push(row);};
        if(error)add(new Adw.ActionRow({title:error,use_markup:false}));
        let catalog;
        try { catalog=library.catalog(); }
        catch(exception){add(new Adw.ActionRow({title:exception.message,use_markup:false}));return GLib.SOURCE_REMOVE;}
        if(!catalog.length)add(new Adw.ActionRow({title:translate('No folders available'),use_markup:false}));
        for(const item of catalog) {
            const row=new Adw.ActionRow({title:item.name,subtitle:item.apps.slice(0,3).map(app=>app.label).join(' · '),use_markup:false});
            row.set_name(item.id);row.add_prefix(new Gtk.Image({icon_name:'folder-symbolic'}));
            const button=new Gtk.ToggleButton({label:translate(item.pinned ? 'Pinned':'Pin to panel'),active:item.pinned,
                sensitive:(item.enabled && settings.get_boolean('enabled')) || item.pinned,valign:Gtk.Align.CENTER});
            button.set_tooltip_text(translate(item.pinned ? 'Unpin from panel':'Pin to panel'));
            button.connect('toggled',()=>{
                try {library.pin(item.id,button.active);error='';}
                catch(exception){error=exception.message;}
                queue();
            });
            row.add_suffix(button);add(row);
        }
        return GLib.SOURCE_REMOVE;
    };
    const queue=()=>{if(!closed && !timer && group.get_mapped())timer=GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE,refresh);};
    group.connect('map',queue);
    const monitor=Gio.AppInfoMonitor.get();
    const signals=[[settings,settings.connect('changed::groups',queue)],
        [settings,settings.connect('changed::enabled',queue)],[monitor,monitor.connect('changed',queue)]];
    if(library.favoritesStore)signals.push([library.favoritesStore,library.favoritesStore.connect('changed::favorite-apps',queue)]);
    library.sources.watch(queue);
    onWindowClose(window,()=>{
        closed=true;
        if(timer)GLib.source_remove(timer);
        timer=0;
        for(const [store,signal] of signals)store.disconnect(signal);
        library.sources.close();
    });
}
