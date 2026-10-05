// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {pruneGroups} from './model.js';

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// Synchronize linked dock folders with GNOME's application-grid folders.
export class AppGridFolders {
    constructor(settings, commit) {
        this.settings = settings;
        this.commit = commit;
        this.root = new Gio.Settings({schema_id: 'org.gnome.desktop.app-folders'});
        this.records = new Map();
        this.rootSignal = this.root.connect('changed::folder-children', () => this.pull());
        this.pull();
    }

    destroy() {
        this.root.disconnect(this.rootSignal);
        for (const {settings, signal} of this.records.values())
            settings.disconnect(signal);
        this.records.clear();
    }

    _bind(groups) {
        const ids = new Set(Object.values(groups).map(group => group.gridFolder).filter(Boolean));
        const children = this.root.get_strv('folder-children');
        for (const [id, record] of this.records) {
            if (!ids.has(id) || !children.includes(id)) {
                record.settings.disconnect(record.signal);
                this.records.delete(id);
            }
        }
        for (const id of ids) {
            if (this.records.has(id) || !children.includes(id) || id.includes('/'))
                continue;
            const settings = new Gio.Settings({schema_id: 'org.gnome.desktop.app-folders.folder',
                path: `${this.root.path}folders/${id}/`});
            const signal = settings.connect('changed', () => {
                if (!this.writing)
                    this.pull();
            });
            this.records.set(id, {settings, signal});
        }
    }

    _read(settings) {
        const categories = settings.get_strv('categories');
        const excluded = settings.get_strv('excluded-apps');
        const infos = Gio.AppInfo.get_all().filter(info => info.should_show() &&
            !info.get_id()?.startsWith('local.groups.'));
        const byId = new Map(infos.map(info => [info.get_id(), info]));
        const automatic = infos.filter(info =>
            (info.get_categories?.() ?? '').split(';').some(category => categories.includes(category)))
            .map(info => info.get_id());
        const apps = [...new Set([...settings.get_strv('apps'), ...automatic])]
            .filter(id => byId.has(id) && !excluded.includes(id));
        const raw = settings.get_string('name');
        const name = settings.get_boolean('translate')
            ? Shell.util_get_translated_folder_name(raw) ?? raw : raw;
        return {name, apps, automatic, byId};
    }

    pull() {
        const groups = JSON.parse(this.settings.get_string('groups'));
        this._bind(groups);
        let changed = false;
        for (const group of Object.values(groups)) {
            if (!group.gridFolder)
                continue;
            const record = this.records.get(group.gridFolder);
            if (!record) {
                delete group.gridFolder;
                changed = true;
                continue;
            }
            const source = this._read(record.settings);
            record.last = {name: source.name, apps: source.apps};
            if (group.name === source.name && same(group.apps.map(entry => entry.desktop), source.apps))
                continue;
            const existing = new Map(Object.values(groups).flatMap(folder =>
                folder.apps.map(entry => [entry.desktop, entry])));
            group.name = source.name;
            group.apps = source.apps.map(id => existing.get(id) ??
                {desktop: id, label: source.byId.get(id).get_name()});
            const members = new Set(source.apps);
            for (const other of Object.values(groups)) {
                if (other !== group)
                    other.apps = other.apps.filter(entry => !members.has(entry.desktop));
            }
            changed = true;
        }
        if (changed) {
            let favorites = global.settings.get_strv('favorite-apps');
            pruneGroups(groups, favorites);
            if (this.settings.get_boolean('enabled')) {
                const owners = new Map(Object.values(groups).flatMap(group => group.apps.flatMap(entry =>
                    [entry.desktop, ...(entry.aliases ?? [])].map(id => [id, `${group.id}.desktop`]))));
                favorites = [...new Set(favorites.map(id => owners.get(id) ?? id))];
            }
            this.commit(groups, favorites);
        }
    }

    push(groups) {
        this._bind(groups);
        this.writing = true;
        try {
            for (const group of Object.values(groups)) {
                const record = this.records.get(group.gridFolder);
                if (!record)
                    continue;
                const source = this._read(record.settings);
                const last = record.last ?? source;
                const apps = group.apps.map(entry => entry.desktop);
                record.settings.delay();
                if (group.name !== last.name) {
                    record.settings.set_string('name', group.name);
                    record.settings.set_boolean('translate', false);
                }
                if (!same(apps, last.apps)) {
                    record.settings.set_strv('apps', apps);
                    const excluded = record.settings.get_strv('excluded-apps').filter(id => !apps.includes(id));
                    record.settings.set_strv('excluded-apps', [...new Set([...excluded,
                        ...source.automatic.filter(id => !apps.includes(id))])]);
                }
                record.settings.apply();
                record.last = {name: group.name, apps};
            }
        } finally {
            this.writing = false;
        }
    }
}
