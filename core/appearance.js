// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {contract} from './contract.js';

/** Validate one appearance change; return undefined for unsupported values. */
export function appearanceValue(name, value) {
    const setting = contract.appearancePreferences.find(item => item.name === name);
    if (!setting) return undefined;
    if (setting.type === 'bool') return typeof value === 'boolean' ? value : undefined;
    if (setting.type === 'color') return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value : undefined;
    if (setting.range) {
        if (!Number.isFinite(value) || (setting.type === 'int' && !Number.isInteger(value))) return undefined;
        if (name === 'iconRotation' && (value < setting.range[0] || value > setting.range[1])) return undefined;
        const bounded = Math.max(setting.range[0], Math.min(setting.range[1], value));
        return name === 'iconRotation' ? bounded % 360 : bounded;
    }
    if (typeof value !== 'string' || value.includes('\0') || value.length > setting.maxLength) return undefined;
    if (setting.type === 'path') return !value || value.startsWith('/') ? value : undefined;
    return setting.type === 'name' ? value.trim() || undefined : value;
}

/** Store a validated appearance change; return whether the value is supported. */
export function setAppearance(group, property, value) {
    const validated = appearanceValue(property,value);
    if (validated === undefined) return false;
    group[property] = validated;
    return true;
}

/** Resolve appearance without replacing existing or legacy user settings. */
export function appearance(group = {}) {
    group = group || {};
    const value = Object.assign({},group);
    const defaults = Object.assign({},contract.appearance,group.id ? contract.legacy.appearance : {});
    for (const [name, fallback] of Object.entries(defaults))
        value[name] = appearanceValue(name,group[name]) ?? fallback;
    if (group.dockColor === undefined && /^#[0-9a-f]{6}$/i.test(group.colors?.[1]))
        value.dockColor = group.colors[1];
    if (group.dockOpacity === undefined && typeof group.transparentDock === 'boolean')
        value.dockOpacity = group.transparentDock ? 0 : 1;
    if (Number.isFinite(group.iconRotation)) value.iconRotation = ((group.iconRotation % 360) + 360) % 360;
    return value;
}

/** Create a new folder using common defaults and caller-owned identity metadata. */
export function newFolder(id, name, apps, gridFolder = null) {
    const group = Object.assign({},contract.appearance,{id,
        name:String(name || 'New Folder').trim().slice(0,80) || 'New Folder',
        icon:'folder-symbolic',colors:[contract.appearance.dockColor,contract.appearance.dockColor],apps});
    if (gridFolder) group.gridFolder = gridFolder;
    return group;
}
