// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';
import {transact, membership, referencedDesktops} from '../core/engine.js';

/** Exercise Shell catalog metadata through the portable transaction API. */
function adapter() {
    const source = readFileSync(new URL('../extension/folderCommands.js', import.meta.url), 'utf8')
        .replace(/^import .*;\n/gm, '').replace('export class ', 'class ');
    const Commands = runInNewContext(`${source}\nFolderCommands`, {transact, membership, referencedDesktops});
    const state = {groups: {one: {id:'local.groups.One',name:'Tools',apps:[
        {desktop:'a.desktop',label:'Custom A'}, {desktop:'b.desktop',label:'B'}]}}, favorites:['local.groups.One.desktop','timer.desktop']};
    const host = {_settings:{get_string:()=>JSON.stringify(state.groups)},
        _store:{_commitGroups:(groups,favorites)=>Object.assign(state,{groups,favorites})},
        _view:{_closeMenus:()=>{}}};
    const catalog = new Map([['a.desktop','Application A'],['b.desktop','Application B'],['timer.desktop','Named Timer']]);
    const commands = new Commands(host, {favorites:()=>state.favorites,isAvailable:id=>catalog.has(id),
        resolveEntry:id=>catalog.has(id) ? {desktop:id,label:catalog.get(id)} : null,
        makeSuffix:()=>'test',feedback:{show:()=>{},clear:()=>{}}});
    return {commands,state};
}

test('moving an ungrouped application resolves its name instead of its desktop filename', () => {
    const {commands,state} = adapter();
    commands._execute({operation:'move',desktop:'timer.desktop',key:'one'});
    assert.equal(state.groups.one.apps[2].label,'Named Timer');
    assert.equal(state.groups.one.apps[0].label,'Custom A');
});

test('a dragged tile retains its supplied label when moved into another group', () => {
    const {commands,state} = adapter();
    commands._moveEntry({desktop:'timer.desktop',label:'Timers'},'one');
    assert.equal(state.groups.one.apps[2].label,'Timers');
});

test('a stale drag payload cannot restore an uninstalled application', () => {
    const {commands,state} = adapter();
    commands._moveEntry({desktop:'removed.desktop',label:'Removed Timer'},'one');
    assert.equal(state.groups.one.apps.length,2);
});
