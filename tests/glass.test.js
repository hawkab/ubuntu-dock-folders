// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
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
        Extension: class {},
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
        actor: {x: 0, y: 0, get_allocation_box: () => ({x1: 66, y1: 38})}};
    menu._glass = {
        visible: false, width: 0, height: 0, x: 6, y: 0,
        get_allocation_box: () => ({x1: 6, y1: 0, get_size: () => allocation}),
        get_parent: () => menu.actor,
        add_child: () => {},
        add_effect_with_name: (name, effect) => effects.set(name, effect),
        remove_effect_by_name: name => effects.delete(name),
    };
    return {renderer, menu, effects, laters};
}

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
