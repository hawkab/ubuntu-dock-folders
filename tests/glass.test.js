// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {contract} from '../core/contract.js';
import {surface, blurLevel} from '../core/preferences.js';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const source = readFileSync(new URL('../extension/rendering.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '')
    .replace('export class FolderRenderer', 'class FolderRenderer');

function fixture(allocation = [290, 253]) {
    const effects = new Map();
    const laters = new Map();
    let nextLater = 1;
    class Actor {
        constructor(properties = {}) {
            Object.assign(this, properties);
            this.children = [];
        }

        add_child(child) { this.children.push(child); }
        set_position(x, y) { Object.assign(this, {x, y}); }
        destroy() { this.destroyed = true; }
    }
    const FolderRenderer = runInNewContext(`${source}\nFolderRenderer`, {
        Extension: class {}, contract,
        RoundedBackdrop: class {},
        Shell: {BlurEffect: Actor, BlurMode: {ACTOR: 0}},
        Clutter: {Actor, Clone: Actor},
        GLib: {SOURCE_REMOVE: false},
        Meta: {LaterType: {BEFORE_REDRAW: 1}},
        global: {
            stage: {width: 800, height: 600},
            window_group: {get_children: () => []},
            compositor: {get_laters: () => ({
                add: (_type, callback) => {
                    const id = nextLater++;
                    laters.set(id, callback);
                    return id;
                },
                remove: id => laters.delete(id),
            })},
        },
    });
    const renderer = new FolderRenderer();
    const menu = {isOpen: true, _useGlass: true,
        sourceActor: {has_allocation: () => true},
        actor: {x: 0, y: 0, allocation: {x1: 66, y1: 38},
            get_allocation_box: () => { throw new Error('Parent layout was forced'); }}};
    menu._glass = {
        visible: false, width: 0, height: 0, x: 6, y: 0,
        has_allocation: () => true,
        allocation: {x1: 6, y1: 0, get_size: () => allocation},
        get_allocation_box: () => { throw new Error('Glass layout was forced'); },
        get_parent: () => menu.actor,
        add_child: () => {},
        add_effect_with_name: (name, effect) => effects.set(name, effect),
        remove_effect_by_name: name => effects.delete(name),
    };
    return {renderer, menu, effects, laters};
}

test('cached glass allocation never forces a pending dock or popup layout', () => {
    const {renderer, menu, effects} = fixture();
    menu.sourceActor.has_allocation = () => false;
    menu._glass.has_allocation = () => false;
    renderer._syncGlass(menu);
    assert.ok(menu._glassClone);
    assert.equal(effects.size, 2);
    assert.equal(menu._glassClone.x, -72);
    assert.equal(menu._glassClone.y, -38);
});

test('backdrop positioning ignores invalid cached geometry until allocation recovers', () => {
    const {renderer, menu} = fixture();
    renderer._syncGlass(menu);
    menu.actor.allocation = {x1: NaN, y1: Infinity};
    renderer._positionGlass(menu);
    assert.equal(menu._glassClone.x, -72);
    assert.equal(menu._glassClone.y, -38);
    menu.actor.allocation = {x1: 80, y1: 45};
    renderer._positionGlass(menu);
    assert.equal(menu._glassClone.x, -86);
    assert.equal(menu._glassClone.y, -45);
});

test('glass is restored when a reopened popup has its previous allocation but zero preferred size', () => {
    const {renderer, menu, effects, laters} = fixture();
    renderer._syncGlass(menu);
    const firstClone = menu._glassClone;
    assert.ok(firstClone);
    assert.equal(effects.size, 2);
    assert.equal(firstClone.x, -72);
    assert.equal(firstClone.y, -38);
    menu.isOpen = false;
    renderer._syncGlass(menu);
    assert.ok(firstClone.destroyed);
    assert.equal(menu._glassClone, null);
    assert.equal(effects.size, 0);
    assert.equal(laters.size, 0);
    menu.isOpen = true;
    renderer._syncGlass(menu);
    assert.ok(menu._glassClone);
    assert.notEqual(menu._glassClone, firstClone);
    assert.equal(effects.size, 2);
    assert.equal(laters.size, 1);
});

test('the first opening waits for a finite, positive allocation', () => {
    for (const allocation of [[0, 0], [NaN, NaN], [290, 0], [Infinity, 253]]) {
        const {renderer, menu, effects} = fixture(allocation);
        renderer._syncGlass(menu);
        assert.equal(menu._glassClone, undefined);
        assert.equal(effects.size, 0);
    }
    const allocation = [0, 0];
    const {renderer, menu, effects} = fixture(allocation);
    renderer._syncGlass(menu);
    allocation.splice(0, 2, 290, 253);
    renderer._syncGlass(menu);
    assert.ok(menu._glassClone);
    assert.equal(effects.size, 2);
});

test('disabling glass removes its backdrop and pending redraw', () => {
    const {renderer, menu, effects, laters} = fixture();
    renderer._syncGlass(menu);
    const clone = menu._glassClone;
    menu._useGlass = false;
    renderer._syncGlass(menu);
    assert.equal(menu._glass.visible, false);
    assert.ok(clone.destroyed);
    assert.equal(effects.size, 0);
    assert.equal(laters.size, 0);
});

test('transparency never changes the independently selected blur', () => {
    for (const blur of [0, 1, 25, 50, 75, 100])
        for (let transparency = 0; transparency <= 100; transparency++) {
            const value = surface({backgroundOpacity: 1 - transparency / 100},blur);
            assert.equal(value.blurAmount, blur / 100);
            assert.equal(value.backgroundOpacity, 1 - transparency / 100);
        }
});

test('legacy appearance is retained until its transparency is adjusted', () => {
    const group = {glassOpacity:.24, popupOpacity:.9};
    assert.equal(surface(group,100,true).backgroundOpacity,.24);
    assert.equal(surface(group,0,false).backgroundOpacity,.9);
    assert.equal(surface({...group,backgroundOpacity:.17},0,true).backgroundOpacity,.17);
    assert.equal(surface({...group,backgroundOpacity:.17},100,false).backgroundOpacity,.17);
    assert.equal(blurLevel(-1,true),100);
    assert.equal(blurLevel(-1,false),0);
    assert.equal(blurLevel(50,false),50);
});

test('GNOME adjusts the backdrop radius while retaining full backdrop opacity', () => {
    const {renderer, menu} = fixture();
    menu._blurAmount = surface({backgroundOpacity: 0},50).blurAmount;
    renderer._syncGlass(menu);
    assert.equal(menu._glass.opacity, 255);
    assert.equal(menu._blurEffect.radius, contract.layout.blurRadius / 2);
    assert.ok(menu._glass.visible);
    menu._blurAmount = 0;
    menu._useGlass = false;
    renderer._syncGlass(menu);
    assert.equal(menu._glass.opacity, 255);
    assert.equal(menu._glass.visible, false);
});
