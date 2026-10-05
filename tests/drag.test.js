// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const source = readFileSync(new URL('../extension/extension.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '')
    .replace('export default class DockGroups', 'class DockGroups');

function extensionFor(onFavorites = () => {}) {
    const DockGroups = runInNewContext(`${source}\nDockGroups`, {
        FolderRenderer: class {},
        Gio: {DesktopAppInfo: {new: () => null}},
        global: {settings: {set_strv: onFavorites}},
        St: {Side: {LEFT: 0, RIGHT: 1}},
        DND: {DragMotionResult: {CONTINUE: 0, MOVE_DROP: 1}},
    });
    const extension = new DockGroups();
    let groups = '{}';
    extension._groups = {};
    extension._settings = {
        get_string: () => groups,
        set_string: (_key, value) => { groups = value; },
        get_boolean: () => true,
        set_boolean: () => {},
    };
    extension._syncDesktopFiles = () => {};
    extension._dropIcons = new Set();
    extension._indexGroups();
    return extension;
}

const app = id => ({get_id: () => id, get_name: () => 'Terminal', is_window_backed: () => false});

test('favorites observe the committed folder and membership before a synchronous dock rebuild', () => {
    const extension = extensionFor((_key, favorites) => {
        const group = extension._groups.messengers;
        assert.equal(group.desktopId, favorites[0]);
        assert.equal(group.key, 'messengers');
        assert.equal(extension._sourceEntry({app: app('org.gnome.Terminal.desktop')}).group,
            group.apps.length ? group : undefined);
    });
    extension._commitGroups({messengers: {id: 'local.groups.Messengers', name: 'Messengers',
        apps: [{desktop: 'org.gnome.Terminal.desktop', label: 'Terminal'}]}},
    ['local.groups.Messengers.desktop']);
    extension._commitGroups({messengers: {id: 'local.groups.Messengers', name: 'Messengers', apps: []}},
        ['local.groups.Messengers.desktop']);
    assert.equal(extension._sourceEntry({app: app('org.gnome.Terminal.desktop')}).group, undefined);
});

test('retired folder launchers cannot be treated as applications or nested into a new folder', () => {
    const extension = extensionFor();
    assert.equal(extension._sourceEntry({app: app('local.groups.Retired.desktop')}), null);
    const icon = {app: app('local.groups.Retired.desktop'), width: 100, height: 100,
        remove_style_class_name: () => {}, connect: () => {}};
    extension._decorateDrop(icon, null, {_position: 0});
    const terminal = {app: app('org.gnome.Terminal.desktop')};
    assert.equal(icon.handleDragOver(terminal, null, 50, 50), 0);
    assert.equal(icon.acceptDrop(terminal, null, 50, 50), false);
});
