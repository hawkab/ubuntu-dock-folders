// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';
import {matchPwa, pwaIndex} from '../core/windowIdentity.js';

const source = readFileSync(new URL('../extension/dockWindows.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '')
    .replace('export class DockWindows', 'class DockWindows');

function extensionFor(windows, entries) {
    const DockWindows = runInNewContext(`${source}\nDockWindows`, {
        FolderRenderer: class {},
        matchPwa,
        global: {get_window_actors: () => windows.map(meta_window => ({meta_window})),settings:{get_strv:()=>[]}},
    });
    const extension = {};
    extension._windowsAdapter = new DockWindows(extension);
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
    assert.deepEqual([...extension._windowsAdapter._windows(browsers)], [chromeWindow]);
    assert.deepEqual([...extension._windowsAdapter._windows(messengers)], [tgWindow]);
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
    assert.deepEqual([...extension._windowsAdapter._windows(group)], [firstWindow, secondWindow]);
    assert.deepEqual([...extension._windowsAdapter._windows(group, first)], [firstWindow]);
});

test('PWA classes override Chrome attribution and follow a changed launch profile', () => {
    const id = 'a'.repeat(32), desktop = `chrome-${id}-Default.desktop`;
    const browsers = {}, work = {};
    const chrome = {desktop:'google-chrome.desktop',group:browsers}, pwa = {desktop,group:work};
    const native = windowFor(chrome.desktop,{get_wm_class:()=>`chrome-${id}-Profile_3`});
    const extension = extensionFor([native],[chrome,pwa]);
    extension._pwas = pwaIndex([{desktop,argv:['chrome','--profile-directory=Profile 3',`--app-id=${id}`]}]);
    assert.deepEqual([...extension._windowsAdapter._windows(work)],[native]);
    assert.deepEqual([...extension._windowsAdapter._windows(browsers)],[]);
    extension._pwas = pwaIndex([{desktop,argv:['chrome','--profile-directory=Profile 4',`--app-id=${id}`]}]);
    assert.deepEqual([...extension._windowsAdapter._windows(work)],[]);
});

test('ambiguous X11 PWA classes do not select a profile guessed by the native tracker', () => {
    const id = 'a'.repeat(32), first = {desktop:`chrome-${id}-Default.desktop`,group:{}};
    const second = {desktop:`chrome-${id}-Profile_2.desktop`,group:{}};
    const native = windowFor(first.desktop,{get_wm_class_instance:()=>`crx_${id}`});
    const extension = extensionFor([native],[first,second]);
    extension._pwas = pwaIndex([first,second].map((entry,i)=>({...entry,
        argv:['chrome',`--profile-directory=${i ? 'Profile 2' : 'Default'}`,`--app-id=${id}`]})));
    assert.deepEqual([...extension._windowsAdapter._windows(first.group)],[]);
    assert.deepEqual([...extension._windowsAdapter._windows(second.group)],[]);
});

test('standalone PWA windows are removed from Chrome and use their own running launcher', () => {
    const id = 'a'.repeat(32), desktop = `chrome-${id}-Default.desktop`;
    const browser = windowFor('google-chrome.desktop'), native = windowFor('google-chrome.desktop',{
        get_wm_class:()=>`chrome-${id}-Profile_3`});
    const extension = extensionFor([browser,native],[]);
    extension._pwas = pwaIndex([{desktop,argv:['chrome','--profile-directory=Profile 3',`--app-id=${id}`]}]);
    extension._pwaDesktops = new Set([desktop]);
    const chrome = {get_id:()=> 'google-chrome.desktop',get_windows:()=>[browser,native]};
    const pwa = {get_id:()=>desktop,get_windows:()=>[]};
    extension._getRunning = ()=>[chrome];
    extension._appSystem = {lookup_app:()=>pwa};
    assert.deepEqual([...extension._windowsAdapter.applicationWindows(chrome)],[browser]);
    assert.deepEqual([...extension._windowsAdapter.applicationWindows(pwa)],[native]);
    assert.deepEqual([...extension._windowsAdapter.runningApplications()],[chrome,pwa]);
    extension._windowsAdapter.beginUpdate();
    assert.deepEqual([...extension._windowsAdapter.applicationWindows(chrome)],[browser]);
    assert.deepEqual([...extension._windowsAdapter.applicationWindows(pwa)],[native]);
    extension._windowsAdapter.endUpdate();
    assert.equal(extension._windowsAdapter.applications,null);
});
