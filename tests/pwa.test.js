// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {pwaIndex, matchPwa} from '../core/windowIdentity.js';

const id = 'a'.repeat(32), other = 'b'.repeat(32);
const app = (profile, file = profile, appId = id) => ({
    desktop: `chrome-${appId}-${file.replaceAll(' ', '_')}.desktop`,
    argv: ['/opt/google/chrome/chrome', `--profile-directory=${profile}`, `--app-id=${appId}`],
});
const wm = profile => `chrome-${id}-${profile.replaceAll(' ', '_')}`;

test('a changed profile matches the existing launcher without rewriting it', () => {
    const entry = app('Profile 3', 'Default');
    const index = pwaIndex([entry]);
    assert.equal(matchPwa(index, [wm('Profile 3')]), entry.desktop);
    assert.equal(matchPwa(index, [`${wm('Profile 3')}.desktop`]), entry.desktop);
    assert.equal(matchPwa(index, [`crx_${id}`, 'Google-chrome']), entry.desktop);
    assert.equal(matchPwa(index, [wm('Default')]), '');
    assert.equal(matchPwa(index, ['google-chrome']), '');
});

test('separate profiles remain separate and a profile-less X11 class stays ambiguous', () => {
    const first = app('Profile 3', 'Default'), second = app('Profile 4');
    const index = pwaIndex([first, second]);
    assert.equal(matchPwa(index, [wm('Profile 3')]), first.desktop);
    assert.equal(matchPwa(index, [wm('Profile 4')]), second.desktop);
    assert.equal(matchPwa(index, [`crx_${id}`]), '');
    assert.equal(matchPwa(index, [wm('Profile 9')]), '');
    assert.equal(matchPwa(index, [wm('profile 3')]), '');
    assert.equal(matchPwa(index, [`crx_${id}`, wm('Profile 4')]), second.desktop);
    assert.equal(matchPwa(index, [`crx_${id}`], 'google-chrome.desktop'), '');
});

test('canonical launchers win over duplicates for the same app and profile', () => {
    const old = app('Profile 3', 'Default'), current = app('Profile 3');
    for (const entries of [[old,current],[current,old]]) {
        assert.equal(matchPwa(pwaIndex(entries), [wm('Profile 3')]), current.desktop);
        assert.equal(matchPwa(pwaIndex(entries), [`crx_${id}`]), current.desktop);
    }
    const collision = app('Profile 3', 'Renamed');
    assert.equal(matchPwa(pwaIndex([old,collision]), [wm('Profile 3')]), '');
});

test('catalog replacement drops stale identities after profile changes or uninstall', () => {
    const entry = app('Profile 3', 'Default');
    assert.equal(matchPwa(pwaIndex([entry]), [wm('Profile 3')]), entry.desktop);
    entry.argv[1] = '--profile-directory=Profile 7';
    const index = pwaIndex([entry]);
    assert.equal(matchPwa(index, [wm('Profile 3')]), '');
    assert.equal(matchPwa(index, [wm('Profile 7')]), entry.desktop);
    assert.equal(matchPwa(pwaIndex([]), [wm('Profile 7')]), '');
});

test('a grouped legacy launcher keeps its windows when Chrome creates a canonical duplicate', () => {
    const old = {...app('Profile 3', 'Default'),preferred:true}, current = app('Profile 3');
    const index = pwaIndex([old,current,app('Profile 4')]);
    assert.equal(matchPwa(index, [wm('Profile 3')]), old.desktop);
    assert.equal(matchPwa(index, [wm('Profile 4')]), app('Profile 4').desktop);
    assert.equal(matchPwa(index, [`crx_${id}`]), '');
});

test('split arguments, spaces and unicode profiles retain their identity', () => {
    const entry = app('Рабочий профиль', 'Default');
    entry.argv = ['chrome', '--profile-directory', 'Рабочий профиль', '--app-id', id];
    assert.equal(matchPwa(pwaIndex([entry]), [wm('Рабочий профиль')]), entry.desktop);
});

test('malformed or unrelated commands do not create browser aliases', () => {
    for (const argv of [[],['chrome',`--app-id=${other}`],['chrome',`--app-id=${id}`,'--profile-directory=../other'],
        ['chrome','--',`--app-id=${id}`],['chrome',`--app-id=${id}`,'--profile-directory='],
        ['chrome',`--app-id=${id}`,'--profile-directory'],
        ['chrome',`--app-id=${id}`,'--profile-directory=Default','--profile-directory=Other']]) {
        const entry = {...app('Default'),argv};
        assert.deepEqual(Object.keys(pwaIndex([entry])), []);
    }
});
