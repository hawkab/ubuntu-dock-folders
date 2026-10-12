// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {transact, referencedDesktops} from '../core/engine.js';
import {folderChanges} from '../core/changes.js';
import {contract} from '../core/contract.js';

const folder = () => ({id:'local.groups.One',name:'Tools',apps:[{desktop:'a'},{desktop:'b'},{desktop:'c'}]});
const entries = Object.fromEntries(['a','b','c'].map(desktop => [desktop,{desktop}]));

test('appearance commands do not request application metadata', () => {
    const state = {groups:{one:folder()},favorites:['local.groups.One.desktop','d.desktop'],undo:null};
    assert.deepEqual(referencedDesktops(state,{operation:'appearance'}),[]);
    assert.deepEqual(referencedDesktops(state,{operation:'applyAppearance'}),[]);
    assert.ok(referencedDesktops(state,{operation:'reconcile'}).includes('d.desktop'));
});
function freeze(value) {
    if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
    return value;
}

test('appearance changes preserve frozen inputs and record explicit default overrides', () => {
    const state = freeze({groups:{one:folder()},favorites:['local.groups.One.desktop'],undo:null});
    const result = transact({state,command:{operation:'appearance',key:'one',property:'dockOpacity',value:contract.appearance.dockOpacity}});
    assert.ok(result.changed);
    assert.equal(state.groups.one.dockOpacity,undefined);
    assert.equal(result.state.groups.one.dockOpacity,contract.appearance.dockOpacity);
    assert.equal(transact({state:result.state,command:{operation:'appearance',key:'one',property:'dockOpacity',value:contract.appearance.dockOpacity}}).changed,false);
});

test('undo owns an independent membership snapshot and retains later appearance', () => {
    const state = {groups:{one:folder()},favorites:['local.groups.One.desktop'],undo:null};
    const moved = transact({state,entries,command:{operation:'move',desktop:'c',key:'one',before:'a'}}).state;
    state.groups.one.apps[0].desktop = 'changed outside';
    const named = transact({state:freeze(moved),command:{operation:'appearance',key:'one',property:'name',value:'Renamed'}}).state;
    const restored = transact({state:named,entries,command:{operation:'undo'}}).state;
    assert.deepEqual(restored.groups.one.apps.map(app => app.desktop),['a','b','c']);
    assert.equal(restored.groups.one.name,'Renamed');
});

test('change classification separates visuals from launchers and removed aliases', () => {
    const original = {one:folder()};
    const visual = {one:{...original.one,iconRotation:45,dockColor:'#123456'}};
    assert.deepEqual(folderChanges(original,visual),{changed:['one'],removed:[],membership:false,launchers:false});
    assert.equal(folderChanges(original,{one:{...original.one,name:'Renamed'}}).launchers,true);
    const aliased = {one:{...original.one,apps:[{desktop:'a',aliases:['alias']},...original.one.apps.slice(1)]}};
    assert.equal(folderChanges(aliased,original).membership,true);
    assert.deepEqual(folderChanges(original,{}),{changed:[],removed:['one'],membership:true,launchers:true});
});
