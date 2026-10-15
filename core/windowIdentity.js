// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

function option(argv, name) {
    let found;
    for (let i = 1; i < argv.length && argv[i] !== '--'; i++) {
        const value = argv[i];
        if (value === name || value.startsWith(name + '=')) {
            if (found !== undefined) return null;
            found = value === name ? argv[++i] : value.slice(name.length + 1);
            if (found === undefined || found.startsWith('--')) return null;
        }
    }
    return found;
}

/** Index installed Chrome PWA identities by their declared launch profile. */
export function pwaIndex(entries) {
    const candidates = new Map();
    const add = (key, desktop, score) => {
        const previous = candidates.get(key);
        if (!previous || previous.score < score) candidates.set(key, {desktop,score});
        else if (previous.score === score && previous.desktop !== desktop) previous.desktop = '';
    };
    for (const entry of entries) {
        const match = /^chrome-([a-p]{32})-(.+)\.desktop$/.exec(entry.desktop || '');
        if (!match || !Array.isArray(entry.argv) || entry.argv.some(value => typeof value !== 'string')) continue;
        const appId = option(entry.argv,'--app-id');
        const declared = option(entry.argv,'--profile-directory');
        if (declared === null) continue;
        const profile = declared ?? 'Default';
        if (appId !== match[1] || !profile || /[/\\\x00-\x1f]/.test(profile)) continue;
        const nativeId = `chrome-${appId}-${profile.replace(/ /g, '_')}`;
        add(nativeId,entry.desktop,(entry.preferred ? 4 : 0) + (entry.desktop === nativeId + '.desktop' ? 2 : 1));
    }
    const result = Object.create(null);
    for (const [key,value] of candidates) result[key] = value.desktop;
    for (const [nativeId,value] of candidates) {
        const key = 'crx_' + nativeId.split('-')[1];
        result[key] = Object.prototype.hasOwnProperty.call(result,key) ? '' : value.desktop;
    }
    return result;
}

/** Resolve compositor classes to an unambiguous installed PWA launcher. */
export function matchPwa(index, classes, fallback = '') {
    let weak = fallback;
    for (const value of classes) {
        if (typeof value !== 'string') continue;
        const key = value.replace(/\.desktop$/, '');
        if (Object.prototype.hasOwnProperty.call(index,key)) {
            if (!key.startsWith('crx_')) return index[key];
            weak = index[key];
        }
    }
    return weak;
}
