// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/** Expand source folders using installed, visible applications and exclusion rules. */
export function resolveFolders(sources, entries, keepEmpty = false) {
    const categoriesById = new Map();
    const order = new Map();
    if (sources.some(source => source.categories?.length))
        for (const [id, entry] of Object.entries(entries)) {
            order.set(id,order.size);
            if (entry.visible === false || id.startsWith('local.groups.')) continue;
            for (const category of entry.categories || []) {
                if (!categoriesById.has(category)) categoriesById.set(category,new Set());
                categoriesById.get(category).add(id);
            }
        }
    return sources.filter(source => typeof source.id === 'string' && source.id && !source.id.includes('/') &&
        !source.id.includes('\0') && typeof source.name === 'string').map(source => {
        const categories = new Set(source.categories || []), excluded = new Set(source.excludedApps || []);
        const members = new Set();
        for (const category of categories) for (const id of categoriesById.get(category) || []) members.add(id);
        const automatic = [...members].sort((a,b) => order.get(a)-order.get(b));
        const apps = [...new Set([...(source.apps || []), ...automatic])].filter(id =>
            entries[id] && entries[id].visible !== false && !excluded.has(id) && !id.startsWith('local.groups.'));
        return {id:source.id, name:source.name, automatic, apps:apps.map(id => ({desktop:id,label:entries[id].label || id}))};
    }).filter(source => keepEmpty || source.apps.length);
}

/** List saved groups and available source folders with this desktop's pin state. */
export function folderCatalog({groups = {}, favorites = [], sources = [], entries = {}}) {
    const linked = new Set(), rows = [];
    for (const [key,group] of Object.entries(groups)) {
        if (group.gridFolder) linked.add(group.gridFolder);
        const apps = group.apps.filter(app => entries[app.desktop]);
        rows.push({id:'group:'+key, key, gridFolder:group.gridFolder || null, name:group.name, apps,
            pinned:favorites.includes(group.id+'.desktop'), enabled:apps.length > 0});
    }
    for (const source of resolveFolders(sources,entries)) {
        if (linked.has(source.id)) continue;
        rows.push({id:'gnome-grid:'+source.id, gridFolder:source.id, name:source.name,
            apps:source.apps, pinned:false, enabled:true});
    }
    return rows;
}

/** Resolve a selected row to an idempotent pin command, or null if unavailable. */
export function folderCommand({catalog, id, pinned}) {
    if (typeof pinned !== 'boolean') return null;
    const row = catalog.find(item => item.id === id);
    if (!row || (!row.enabled && pinned)) return null;
    if (row.key) return {operation:'setFolderPinned',key:row.key,pinned};
    if (!pinned) return null;
    return {operation:'importFolder',gridFolder:row.gridFolder,name:row.name,apps:row.apps.map(app => app.desktop)};
}
