// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/** Resolve a launcher URL to a catalog ID, retaining application aliases. */
export function canonicalDesktop(value, aliases = {}) {
    if (typeof value !== 'string' || !value) return '';
    let decoded;
    try { decoded = decodeURIComponent(value); } catch (_) { return ''; }
    let id = decoded.replace(/^applications:/,'').split('?')[0].split('/').pop();
    if (id && !id.endsWith('.desktop')) id += '.desktop';
    return Object.prototype.hasOwnProperty.call(aliases,id) ? aliases[id] : id;
}

/** Expand grouped launchers once while preserving dock order. */
export function expandedFavorites(groups, favorites) {
    const members = new Map(Object.values(groups).map(group => [group.id+'.desktop',group.apps.map(app => app.desktop)]));
    return [...new Set(Array.from(favorites).reduce((list,id) => list.concat(members.get(id) || [id]),[]))];
}

/** List applications represented by folders pinned on this desktop. */
export function groupedDesktops(groups, favorites) {
    const pinned = new Set(favorites);
    return [...new Set(Object.values(groups).filter(group => pinned.has(group.id+'.desktop'))
        .reduce((ids,group) => ids.concat(group.apps.map(app => app.desktop)),[]))];
}

/** Choose a window action from native adapter metadata. */
export function activation(windows, newInstance = false) {
    const index = windows.findIndex(window => window.running !== false);
    if (newInstance || index < 0) return {action:'launch',index};
    return {action:windows[index].active && !windows[index].minimized ? 'minimize' : 'activate',index};
}

/** Select the next running window index for wheel navigation. */
export function cycleWindow(windows, direction) {
    if (!windows.length) return -1;
    const active = windows.findIndex(window => window.active);
    const start = active < 0 ? (direction < 0 ? 0 : -1) : active;
    return (start + (direction < 0 ? -1 : 1) + windows.length) % windows.length;
}
