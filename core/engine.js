// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {applicationIds, moveEntry, pruneGroups, removeUnavailableEntries} from './model.js';
import {contract} from './contract.js';
export {folderCatalog, folderCommand} from './folders.js';
export {folderInteraction} from './folderInteraction.js';
import {folderChanges} from './changes.js';
import {surface} from './preferences.js';
import {appearanceValue, setAppearance, newFolder} from './appearance.js';

const clone = value => JSON.parse(JSON.stringify(value));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** Classify a pair of folder snapshots supplied by a JSON adapter. */
export function describeChanges(value) { return folderChanges(value.previous,value.next); }

/** Identify membership and order without including appearance. */
export function membership(groups) {
    return Object.entries(groups).map(([key, group]) =>
        [key, group.id, group.gridFolder || null, group.apps.map(entry => entry.desktop)]).sort();
}

/** Return whether the retained undo step still describes the current membership. */
export function canUndo(state) {
    return Boolean(state.undo && same(membership(state.groups),state.undo.membership)
        && same(state.favorites,state.undo.favorites));
}

function findEntry(groups, entries, desktop) {
    for (const group of Object.values(groups)) {
        const entry = group.apps.find(app => app.desktop === desktop);
        if (entry) return clone(entry);
    }
    return clone(entries[desktop] || null);
}

/** Change one saved property without copying unrelated folders or the undo snapshot. */
function editAppearance(input) {
    const {key,property,value} = input.command;
    const state = Object.assign({},input.state);
    if (state.undo && !canUndo(state)) state.undo = null;
    const group = Object.prototype.hasOwnProperty.call(state.groups,key) ? state.groups[key] : null;
    const validated = appearanceValue(property,value);
    const changed = Boolean(group && validated !== undefined && group[property] !== validated);
    if (changed) state.groups = Object.assign({},state.groups,{[key]:Object.assign({},group,{[property]:validated})});
    return {version:contract.version,changed,state};
}

/** Apply one command to a JSON state; return changed state and undo availability. */
export function transact(input) {
    if (input.command?.operation === 'appearance') return editAppearance(input);
    const state = Object.assign({},input.state,{groups:clone(input.state.groups),favorites:[...input.state.favorites]}), request = input.command, entries = input.entries || {};
    const groups = state.groups, favorites = state.favorites;
    const hasGroup = key => Object.prototype.hasOwnProperty.call(groups,key);
    const operation = request?.operation, desktop = request?.desktop, key = request?.key;
    const result = changed => ({version:contract.version, changed, state});
    if (!contract.commands.includes(operation)) return result(false);
    const before = {groups:input.state.groups, favorites:input.state.favorites};
    if (state.undo && !canUndo(state)) state.undo = null;
    const available = id => Object.prototype.hasOwnProperty.call(entries,id) && !id.startsWith('local.groups.');
    const folder = Object.values(groups).some(group => group.id+'.desktop' === desktop);
    if (['move','create','extract','pin'].includes(operation) && !available(desktop) && !(operation === 'pin' && folder)) return result(false);
    if (operation === 'reconcile') {
        const removed = removeUnavailableEntries(groups,favorites,available);
        const known = new Set(Object.values(groups).map(group => group.id+'.desktop'));
        state.favorites = [...new Set(favorites.filter(id => known.has(id) || available(id)))];
        if (removed.length || !same(state.favorites,before.favorites)) state.undo = null;
        return result(!same(before,{groups,favorites:state.favorites}));
    }
    if (operation === 'applyAppearance') {
        if (!hasGroup(key)) return result(false);
        const source = groups[key];
        const values = surface(source,request.blurStrength,request.legacyGlass);
        values.dockColor = source.dockColor || source.colors?.[1] || contract.appearance.dockColor;
        if (!Number.isFinite(source.dockOpacity) && typeof source.transparentDock === 'boolean')
            values.dockOpacity = source.transparentDock ? 0 : 1;
        for (const [targetKey,group] of Object.entries(groups)) {
            if (targetKey === key) continue;
            delete group.transparentDock;
            for (const property of Object.keys(contract.appearance))
                if (!setAppearance(group,property,values[property]))
                    setAppearance(group,property,contract.appearance[property]);
            for (const property of ['wallpaperName','wallpaperFolder'])
                if (!setAppearance(group,property,source[property] || ''))
                    setAppearance(group,property,'');
        }
        return result(!same(before.groups,groups));
    }
    if (operation === 'undo') {
        const undo = state.undo;
        state.undo = null;
        if (!undo || !same(membership(groups),undo.membership) || !same(favorites,undo.favorites)) return result(false);
        const restored = clone(undo.before.groups);
        for (const [key,group] of Object.entries(restored))
            if (groups[key]) Object.assign(group,groups[key],{apps:group.apps});
        state.groups = restored; state.favorites = [...undo.before.favorites];
        removeUnavailableEntries(state.groups,state.favorites,available);
        return result(true);
    }
    if (operation === 'move') {
        if (!hasGroup(key)) return result(false);
        moveEntry(groups,favorites,findEntry(groups,entries,desktop),key,request.before);
    } else if (operation === 'create') {
        if (desktop === request.target || !available(request.target) || !/^[a-zA-Z0-9_-]{1,64}$/.test(input.token || '')) return result(false);
        const target = findEntry(groups,entries,request.target), source = findEntry(groups,entries,desktop);
        const previous = Object.values(groups).find(group => group.apps.some(entry => entry.desktop === target.desktop));
        const anchor = previous ? previous.id+'.desktop' : target.desktop;
        const position = favorites.includes(anchor) ? favorites.indexOf(anchor) : favorites.length;
        const key = 'folder-'+input.token, id = 'local.groups.Folder_'+input.token;
        if (Object.prototype.hasOwnProperty.call(groups,key)) return result(false);
        const ids = new Set([desktop,request.target,...(source.aliases || []),...(target.aliases || [])]);
        for (const group of Object.values(groups)) group.apps = group.apps.filter(entry => !ids.has(entry.desktop));
        groups[key] = newFolder(id,request.name,[target,source]);
        favorites.splice(position,0,id+'.desktop');
        state.favorites = favorites.filter(item => !ids.has(item));
    } else if (operation === 'importFolder') {
        if (typeof request.gridFolder !== 'string' || !request.gridFolder || request.gridFolder.includes('/') ||
            !Array.isArray(request.apps) || !/^[a-zA-Z0-9_-]{1,64}$/.test(input.token || '')) return result(false);
        const linked = Object.values(groups).find(group => group.gridFolder === request.gridFolder);
        const apps = linked ? linked.apps : [...new Set(request.apps)].filter(available).map(id => findEntry(groups,entries,id));
        if (!apps.length) return result(false);
        const ids = applicationIds(apps);
        if (!linked) {
            const key = 'folder-'+input.token;
            if (hasGroup(key)) return result(false);
            for (const group of Object.values(groups)) group.apps = group.apps.filter(entry => !ids.has(entry.desktop));
            groups[key] = newFolder('local.groups.Folder_'+input.token,request.name,apps,request.gridFolder);
        }
        const group = linked || groups['folder-'+input.token];
        const launcher = group.id+'.desktop';
        if (linked && favorites.includes(launcher)) return result(false);
        state.favorites = favorites.filter(id => !ids.has(id)).concat(launcher);
    } else if (operation === 'setFolderPinned') {
        if (!hasGroup(key) || typeof request.pinned !== 'boolean') return result(false);
        const group = groups[key], id = group.id+'.desktop';
        const pinned = favorites.includes(id);
        if (pinned === request.pinned) return result(false);
        if (request.pinned) {
            const members = applicationIds(group.apps);
            state.favorites = favorites.filter(item => !members.has(item)).concat(id);
        } else state.favorites = favorites.filter(item => item !== id);
    } else if (operation === 'extract') {
        const owner = Object.values(groups).find(group => group.apps.some(entry => entry.desktop === desktop));
        for (const group of Object.values(groups)) group.apps = group.apps.filter(entry => entry.desktop !== desktop);
        state.favorites = favorites.filter(item => item !== desktop);
        if (request.pin !== false) {
            const position = request.before ? state.favorites.indexOf(request.before) : owner ? state.favorites.indexOf(owner.id+'.desktop')+1 : -1;
            state.favorites.splice(position < 0 ? state.favorites.length : position,0,desktop);
        }
    } else if (operation === 'pin') {
        if (favorites.includes(desktop)) favorites.splice(favorites.indexOf(desktop),1); else favorites.push(desktop);
    } else if (operation === 'reorder') {
        if (!favorites.includes(desktop)) return result(false);
        favorites.splice(favorites.indexOf(desktop),1);
        const position = favorites.indexOf(request.before);
        favorites.splice(position < 0 ? favorites.length : position,0,desktop);
    }
    pruneGroups(groups,state.favorites);
    state.favorites = [...new Set(state.favorites)];
    const changed = !same(before,{groups:state.groups,favorites:state.favorites});
    if (changed) state.undo = {before:clone(before),membership:membership(groups),favorites:[...state.favorites]};
    return result(changed);
}

/** List application IDs a catalog adapter must resolve for a transaction. */
export function referencedDesktops(state, command) {
    if (['appearance','applyAppearance'].includes(command.operation)) return [];
    const ids = [];
    for (const snapshot of [state,state.undo?.before]) if (snapshot) {
        ids.push(...snapshot.favorites);
        for (const group of Object.values(snapshot.groups)) ids.push(...group.apps.map(entry => entry.desktop));
    }
    for (const key of ['desktop','target']) if (typeof command[key] === 'string') ids.push(command[key]);
    if (Array.isArray(command.apps)) ids.push(...command.apps);
    return Array.from(new Set(ids.filter(id => !id.startsWith('local.groups.'))));
}
