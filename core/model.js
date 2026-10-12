// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {contract} from './contract.js';

export function quoteDesktopArgument(value) {
    const quoted = `"${value.replaceAll('%', '%%').replace(/["`$\\]/g, char => `\\${char}`)}"`;
    return quoted.replaceAll('\\', '\\\\').replaceAll('\n', '\\n')
        .replaceAll('\r', '\\r').replaceAll('\t', '\\t');
}

/** Collect desktop IDs and aliases without copying cumulative arrays. */
export function applicationIds(apps) {
    const ids = new Set();
    for (const app of apps) {
        ids.add(app.desktop);
        for (const alias of app.aliases || []) ids.add(alias);
    }
    return ids;
}

export function pruneGroups(groups, favorites) {
    for (const [key, group] of Object.entries(groups)) {
        if (group.apps.length >= contract.layout.minimumMembers || group.gridFolder)
            continue;
        const position = favorites.indexOf(`${group.id}.desktop`);
        if (position !== -1)
            favorites.splice(position, 1, ...group.apps.map(entry => entry.desktop));
        delete groups[key];
    }
}

export function removeUnavailableEntries(groups, favorites, available) {
    const removed = [];
    for (const group of Object.values(groups)) {
        group.apps = group.apps.filter(entry => {
            if (available(entry.desktop))
                return true;
            removed.push(entry);
            return false;
        });
    }
    if (!removed.length)
        return removed;
    const ids = applicationIds(removed);
    for (let index = favorites.length - 1; index >= 0; index--) {
        if (ids.has(favorites[index]))
            favorites.splice(index, 1);
    }
    pruneGroups(groups, favorites);
    return removed;
}

export function moveEntry(groups, favorites, entry, key, before = null) {
    const target = groups[key];
    if (!target)
        return;
    for (const group of Object.values(groups))
        group.apps = group.apps.filter(member => member.desktop !== entry.desktop);
    const position = target.apps.findIndex(member => member.desktop === before);
    target.apps.splice(position < 0 ? target.apps.length : position, 0,
        JSON.parse(JSON.stringify(entry)));
    const aliases = [entry.desktop, ...(entry.aliases ?? [])];
    for (let i = favorites.length - 1; i >= 0; i--) {
        if (aliases.includes(favorites[i]))
            favorites.splice(i, 1);
    }
}
