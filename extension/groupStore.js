// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import {quoteDesktopArgument} from './model.js';
import {folderChanges} from './core/changes.js';

/** Load folder settings, reconcile applications, and synchronize launchers. */
export class GroupStore {
    constructor(host) { this.host = host; }

    _readGroups() {
        const host = this.host;
        const previous = host._groups ?? {};
        host._groups = JSON.parse(host._settings.get_string('groups'));
        if (!host._settings.get_boolean('initialized') && Object.keys(host._groups).length === 0) {
            const [, bytes] = GLib.file_get_contents(`${host.path}/groups.json`);
            host._groups = JSON.parse(new TextDecoder().decode(bytes));
            host._settings.set_string('groups', JSON.stringify(host._groups));
        }
        for (const [key, current] of Object.entries(host._groups)) {
            const old = previous[key];
            if (!old || old.id !== current.id)
                continue;
            const byId = new Map(old.apps.map(app => [app.desktop,app]));
            const apps = current.apps.map(entry => {
                const existing = byId.get(entry.desktop);
                if (!existing) return entry;
                for (const field of Object.keys(existing)) delete existing[field];
                return Object.assign(existing,entry);
            });
            for (const field of Object.keys(old))
                delete old[field];
            Object.assign(old, current, {apps});
            host._groups[key] = old;
        }
        host._settings.set_boolean('initialized', true);
    }

    _groupLayout() {
        const host = this.host;
        return JSON.stringify(Object.entries(host._groups).map(([key, group]) =>
            [key, group.id, group.apps.map(entry => entry.desktop).sort()]).sort());
    }

    _reconcileInstalledApps() {
        const host = this.host;
        if (host._commands._execute({operation:'reconcile'})) host._feedback.clear();
    }

    _indexGroups(force = false) {
        const host = this.host;
        const signature = JSON.stringify(Object.entries(host._groups).map(([key,group]) =>
            [key,group.id,group.apps.map(entry => [entry.desktop,entry.aliases,entry.wmClasses])]));
        if (!force && this.indexed === signature) return;
        this.indexed = signature;
        host._entryIds = new Map();
        host._classes = new Map();
        for (const [key, group] of Object.entries(host._groups)) {
            Object.defineProperty(group, 'key', {value: key, configurable: true});
            Object.defineProperty(group, 'desktopId', {value: `${group.id}.desktop`, configurable: true});
            for (const entry of group.apps) {
                Object.defineProperty(entry, 'group', {value: group, configurable: true});
                for (const id of [entry.desktop, ...(entry.aliases ?? [])])
                    host._entryIds.set(id, entry);
                const wmClass = GioUnix.DesktopAppInfo.new(entry.desktop)?.get_startup_wm_class();
                for (const cls of [...(entry.wmClasses ?? []), ...(wmClass ? [wmClass] : [])])
                    host._classes.set(cls.toLowerCase(), entry);
            }
        }
    }

    _syncFavorites(enabled) {
        const host = this.host;
        const favorites = global.settings.get_strv('favorite-apps');
        const result = [];
        for (const id of favorites) {
            const group = Object.values(host._groups).find(candidate => candidate.desktopId === id);
            if (!enabled && group)
                result.push(...group.apps.map(entry => entry.desktop));
            else if (enabled)
                result.push(host._entryIds.get(id)?.group.desktopId ?? id);
            else
                result.push(id);
        }
        const unique = [...new Set(result)];
        if (JSON.stringify(unique) !== JSON.stringify(favorites))
            global.settings.set_strv('favorite-apps', unique);
    }

    _syncDesktopFiles() {
        const host = this.host;
        const directory = GLib.build_filenamev([GLib.get_user_data_dir(), 'applications']);
        GLib.mkdir_with_parents(directory, 0o755);
        GLib.mkdir_with_parents(host._data, 0o700);
        const registry = Gio.File.new_for_path(`${host._data}/group-desktops.json`);
        const previous = registry.query_exists(null)
            ? JSON.parse(new TextDecoder().decode(registry.load_contents(null)[1])) : [];
        const currentIds = Object.values(host._groups).map(group => `${group.id}.desktop`);
        for (const [key, group] of Object.entries(host._groups)) {
            if (!/^local\.groups\.[A-Za-z0-9_-]+$/.test(group.id))
                throw new Error('Invalid group desktop ID');
            const cleanName = group.name.replaceAll('\n', ' ').replaceAll('\r', ' ');
            const launcher = quoteDesktopArgument(`${host.path}/app/launcher.py`);
            const actions = group.apps.map((entry, i) => `\n[Desktop Action App${i}]\nName=${entry.label.replace(/[\r\n]/g, ' ')}\nExec=/usr/bin/gtk-launch ${quoteDesktopArgument(entry.desktop)}\n`).join('');
            const contents = `[Desktop Entry]\nType=Application\nName=${cleanName}\nComment=${_('Choose an application')}\nExec=/usr/bin/python3 ${launcher} ${quoteDesktopArgument(key)}\nIcon=${group.icon}\nTerminal=false\nStartupNotify=true\nCategories=Utility;\nActions=${group.apps.map((_, i) => `App${i}`).join(';')};\n${actions}`;
            const path = `${directory}/${group.id}.desktop`;
            const file = Gio.File.new_for_path(path);
            let old = '';
            if (file.query_exists(null))
                old = new TextDecoder().decode(file.load_contents(null)[1]);
            if (old !== contents)
                file.replace_contents(new TextEncoder().encode(contents), null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
            const statePath = `${host._data}/state.json`;
            const stateFile = Gio.File.new_for_path(statePath);
            if (stateFile.query_exists(null)) {
                const state = JSON.parse(new TextDecoder().decode(stateFile.load_contents(null)[1]));
                if (!state.created_files.includes(path)) {
                    state.created_files.push(path);
                    GLib.file_set_contents(statePath, JSON.stringify(state, null, 2));
                }
            }
        }
        for (const id of previous) {
            if (!/^local\.groups\.[A-Za-z0-9_-]+\.desktop$/.test(id) || currentIds.includes(id))
                continue;
            const file = Gio.File.new_for_path(`${directory}/${id}`);
            if (file.query_exists(null))
                file.delete(null);
        }
        const ids = JSON.stringify(currentIds);
        if (JSON.stringify(previous) !== ids)
            registry.replace_contents(new TextEncoder().encode(ids), null, false,
                Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        const statePath = `${host._data}/state.json`;
        if (GLib.file_test(statePath, GLib.FileTest.EXISTS)) {
            const [, bytes] = GLib.file_get_contents(statePath);
            const state = JSON.parse(new TextDecoder().decode(bytes));
            const current = new Set(Object.values(host._groups).map(group => `${directory}/${group.id}.desktop`));
            for (const path of state.created_files) {
                if (path.startsWith(`${directory}/local.groups.`) && path.endsWith('.desktop') && !current.has(path)) {
                    const file = Gio.File.new_for_path(path);
                    if (file.query_exists(null))
                        file.delete(null);
                }
            }
        }
    }

    _commitGroups(groups, favorites) {
        const host = this.host;
        const changes = folderChanges(host._groups,groups);
        host._settings.set_string('groups', JSON.stringify(groups));
        host._store._readGroups();
        if (changes.membership) host._store._indexGroups();
        if (changes.launchers) host._store._syncDesktopFiles();
        global.settings.set_strv('favorite-apps', favorites);
    }
}
