// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const source = readFileSync(new URL('../extension/extension.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '')
    .replace('export default class DockGroups', 'class DockGroups');

function extensionFor(windows, entries) {
    const DockGroups = runInNewContext(`${source}\nDockGroups`, {
        FolderRenderer: class {},
        global: {get_window_actors: () => windows.map(meta_window => ({meta_window}))},
    });
    const extension = new DockGroups();
    extension._entryIds = new Map(entries.map(entry => [entry.desktop, entry]));
    extension._classes = new Map();
    extension._tracker = {get_window_app: window => window.app};
    extension._getRunning = () => [];
    return extension;
}

function windowFor(desktop, properties = {}) {
    return {
        app: {get_id: () => desktop, state: 'STARTING'},
        get_wm_class_instance: () => null,
        get_wm_class: () => null,
        skip_taskbar: false,
        ...properties,
    };
}

test('Chrome and tg windows count during STARTING before they enter get_running()', () => {
    const browsers = {};
    const messengers = {};
    const chrome = {desktop: 'google-chrome.desktop', group: browsers};
    const tg = {desktop: 'org.tg.desktop.desktop', group: messengers};
    const chromeWindow = windowFor(chrome.desktop);
    const tgWindow = windowFor(tg.desktop);
    const extension = extensionFor([chromeWindow, tgWindow], [chrome, tg]);
    assert.deepEqual([...extension._windows(browsers)], [chromeWindow]);
    assert.deepEqual([...extension._windows(messengers)], [tgWindow]);
});

test('window counts include minimized members and exclude unrelated or taskbar-skipped windows', () => {
    const group = {};
    const first = {desktop: 'first.desktop', group};
    const second = {desktop: 'second.desktop', group};
    const firstWindow = windowFor(first.desktop, {minimized: true});
    const secondWindow = windowFor(second.desktop);
    const skipped = windowFor(first.desktop, {skip_taskbar: true});
    const unrelated = windowFor('unrelated.desktop');
    const extension = extensionFor([firstWindow, secondWindow, skipped, unrelated], [first, second]);
    assert.deepEqual([...extension._windows(group)], [firstWindow, secondWindow]);
    assert.deepEqual([...extension._windows(group, first)], [firstWindow]);
});
