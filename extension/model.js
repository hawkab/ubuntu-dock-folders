// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

export function quoteDesktopArgument(value) {
    const quoted = `"${value.replaceAll('%', '%%').replace(/["`$\\]/g, char => `\\${char}`)}"`;
    return quoted.replaceAll('\\', '\\\\').replaceAll('\n', '\\n')
        .replaceAll('\r', '\\r').replaceAll('\t', '\\t');
}

export function pruneGroups(groups, favorites) {
    for (const [key, group] of Object.entries(groups)) {
        if (group.apps.length > 1 || group.gridFolder)
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
    const ids = new Set(removed.flatMap(entry => [entry.desktop, ...(entry.aliases ?? [])]));
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
