// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveFolders, folderCatalog, folderCommand} from '../core/folders.js';
import {transact} from '../core/engine.js';
import {groupedDesktops} from '../core/applications.js';

const entries = {
    a:{desktop:'a',label:'A',categories:['Utility']}, b:{desktop:'b',label:'B',categories:[]},
    hidden:{desktop:'hidden',label:'Hidden',visible:false,categories:['Utility']},
    excluded:{desktop:'excluded',label:'Excluded',categories:['Utility']},
    'local.groups.Test.desktop':{categories:['Utility']},
};
const sources = [{id:'Tools',name:'Tools',apps:['b','b','missing','hidden'],categories:['Utility'],excludedApps:['excluded']}];
const groups = {one:{id:'local.groups.One',name:'Custom',gridFolder:'Tools',
    dockOpacity:.2,blurStrength:25,apps:[{desktop:'a',label:'Custom A',aliases:['alias']},{desktop:'b',label:'B'}]}};

test('sources obey visibility, categories, exclusions and missing applications', () => {
    assert.deepEqual(resolveFolders(sources,entries)[0].apps,[{desktop:'b',label:'B'},{desktop:'a',label:'A'}]);
    assert.equal(resolveFolders([{id:'bad/path',name:'Bad'},{id:'empty',name:'Empty'}],entries).length,0);
    assert.equal(resolveFolders([{id:'empty',name:'Empty'}],entries,true).length,1);
});

test('catalog deduplicates linked sources and resolves each desktop pin state', () => {
    for (const favorites of [[],['local.groups.One.desktop']]) {
        const catalog=folderCatalog({groups,favorites,sources,entries});
        assert.equal(catalog.length,1);
        assert.equal(catalog[0].name,'Custom');
        assert.equal(catalog[0].pinned,Boolean(favorites.length));
        assert.deepEqual(catalog[0].apps,groups.one.apps);
    }
    const catalog=folderCatalog({groups,entries:{}});
    assert.equal(catalog[0].enabled,false);
    assert.equal(folderCommand({catalog,id:'group:one',pinned:true}),null);
    assert.equal(folderCommand({catalog,id:'unknown',pinned:true}),null);
});

test('explicit pin commands are idempotent and preserve saved appearance and aliases', () => {
    const catalog=folderCatalog({groups,sources,entries});
    const command=folderCommand({catalog,id:'group:one',pinned:true});
    let state={groups,favorites:['alias','a','files'],undo:null};
    const request=command => ({state,entries,command,token:'test'});
    let result=transact(request(command));
    assert.equal(result.changed,true); state=result.state;
    assert.deepEqual(state.groups,groups);
    assert.deepEqual(state.favorites,['files','local.groups.One.desktop']);
    assert.deepEqual(groupedDesktops(groups,state.favorites),['a','b']);
    assert.equal(transact(request(command)).changed,false);
    result=transact(request({...command,pinned:false})); state=result.state;
    assert.equal(result.changed,true);
    assert.deepEqual(state.groups,groups);
    assert.deepEqual(groupedDesktops(groups,state.favorites),[]);
    assert.equal(transact(request({...command,pinned:false})).changed,false);
    assert.deepEqual(transact(request(command)).state.groups,groups);
});

test('imported folders use the same transaction and appear once in the catalog', () => {
    const catalog=folderCatalog({sources,entries});
    const command=folderCommand({catalog,id:'gnome-grid:Tools',pinned:true});
    const result=transact({state:{groups:{},favorites:['a','b']},entries,command,token:'test'});
    assert.equal(result.changed,true);
    assert.deepEqual(result.state.groups['folder-test'].apps.map(app => app.desktop),['b','a']);
    assert.equal(folderCatalog({...result.state,sources,entries}).length,1);
    assert.equal(folderCommand({catalog,id:'gnome-grid:Tools',pinned:false}),null);
});
