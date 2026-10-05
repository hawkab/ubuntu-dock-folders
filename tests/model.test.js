// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {moveEntry, pruneGroups} from '../extension/model.js';

const app = desktop => ({desktop, label: desktop});
const group = (id, desktops) => ({id, apps: desktops.map(app)});

test('reordering a folder keeps it intact and retains unrelated favorites', () => {
    const groups = {one: group('local.groups.One', ['a', 'b', 'c'])};
    const favorites = ['terminal', 'local.groups.One.desktop', 'files'];
    moveEntry(groups, favorites, app('c'), 'one', 'a');
    pruneGroups(groups, favorites);
    assert.deepEqual(groups.one.apps.map(entry => entry.desktop), ['c', 'a', 'b']);
    assert.deepEqual(favorites, ['terminal', 'local.groups.One.desktop', 'files']);
});

test('moving between folders dissolves a single-app source at its dock position', () => {
    const groups = {one: group('local.groups.One', ['a', 'b']), two: group('local.groups.Two', ['c', 'd'])};
    const favorites = ['terminal', 'local.groups.One.desktop', 'local.groups.Two.desktop'];
    moveEntry(groups, favorites, app('b'), 'two', 'd');
    pruneGroups(groups, favorites);
    assert.equal(groups.one, undefined);
    assert.deepEqual(groups.two.apps.map(entry => entry.desktop), ['c', 'b', 'd']);
    assert.deepEqual(favorites, ['terminal', 'a', 'local.groups.Two.desktop']);
});

test('adding a pinned app removes its aliases without duplicating folder membership', () => {
    const groups = {one: group('local.groups.One', ['a', 'b'])};
    const favorites = ['a', 'alias-a', 'files', 'local.groups.One.desktop'];
    moveEntry(groups, favorites, {...app('a'), aliases: ['alias-a']}, 'one');
    assert.deepEqual(groups.one.apps.map(entry => entry.desktop), ['b', 'a']);
    assert.deepEqual(favorites, ['files', 'local.groups.One.desktop']);
});

test('missing targets leave settings unchanged', () => {
    const groups = {one: group('local.groups.One', ['a', 'b'])};
    const favorites = ['local.groups.One.desktop'];
    const before = JSON.stringify({groups, favorites});
    moveEntry(groups, favorites, app('a'), 'removed-folder');
    assert.equal(JSON.stringify({groups, favorites}), before);
});

test('empty folders vanish without disturbing surrounding dock items', () => {
    const groups = {empty: group('local.groups.Empty', [])};
    const favorites = ['files', 'local.groups.Empty.desktop', 'terminal'];
    pruneGroups(groups, favorites);
    assert.deepEqual(groups, {});
    assert.deepEqual(favorites, ['files', 'terminal']);
});

test('linked grid folders stay pinned when their last application is moved out', () => {
    const groups = {linked: {...group('local.groups.Linked', ['a']), gridFolder: 'Utilities'},
        target: group('local.groups.Target', ['b', 'c'])};
    const favorites = ['local.groups.Linked.desktop', 'local.groups.Target.desktop'];
    moveEntry(groups, favorites, app('a'), 'target');
    pruneGroups(groups, favorites);
    assert.deepEqual(groups.linked.apps, []);
    assert.equal(groups.linked.gridFolder, 'Utilities');
    assert.deepEqual(favorites, ['local.groups.Linked.desktop', 'local.groups.Target.desktop']);
});
