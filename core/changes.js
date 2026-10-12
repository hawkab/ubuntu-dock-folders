// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/** Describe folder changes that require catalog indexes, launchers, or visual refresh. */
export function folderChanges(previous = {}, next = {}) {
    const keys = new Set([...Object.keys(previous),...Object.keys(next)]);
    const changed = [], removed = [];
    let membership = false, launchers = false;
    const members = group => group && [group.id,group.gridFolder,group.apps.map(app =>
        [app.desktop,app.aliases,app.wmClasses])];
    const launcher = group => group && [group.id,group.name,group.icon,
        group.apps.map(app => [app.desktop,app.label])];
    for (const key of keys) {
        const before = previous[key], after = next[key];
        if (JSON.stringify(before) === JSON.stringify(after)) continue;
        if (after) changed.push(key); else removed.push(key);
        membership = membership || JSON.stringify(members(before)) !== JSON.stringify(members(after));
        launchers = launchers || JSON.stringify(launcher(before)) !== JSON.stringify(launcher(after));
    }
    return {changed,removed,membership,launchers};
}
