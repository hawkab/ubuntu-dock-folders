// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const source = readFileSync(new URL('../extension/folderAnimation.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '').replace('export class FolderAnimation', 'class FolderAnimation');

function fixture() {
    class Actor {
        constructor(parent = null) {
            this.parent = parent;
            this.mapped = true;
            this.allocated = true;
            this.signals = new Map();
            this.nextSignal = 1;
            this.allocation = {x1: 0, y1: 0, x2: 48, y2: 48, get_width: () => 48, get_height: () => 48};
        }
        connect(name, callback) { const id = this.nextSignal++; this.signals.set(id, {name, callback}); return id; }
        disconnect(id) { this.signals.delete(id); }
        emit(name) { for (const signal of [...this.signals.values()]) if (signal.name === name) signal.callback(); }
        get_parent() { return this.parent; }
        get_stage() { return this.parent ? this.parent.get_stage() : this; }
        has_allocation() { return this.allocated; }
        get_allocation_box() { throw new Error('Layout was forced'); }
        set_scale() {}
        remove_all_transitions() {}
    }
    const stage = new Actor();
    stage.allocated = false;
    const parent = new Actor(stage), anchor = new Actor(parent);
    const menu = {sourceActor: anchor, actor: new Actor(stage), opened: 0, open() { this.opened++; }};
    const host = {_enabled: true};
    const FolderAnimation = runInNewContext(`${source}\nFolderAnimation`, {
        global: {stage}, BoxPointer: {PopupAnimation: {NONE: 0}},
    });
    const animation = new FolderAnimation(host);
    host._animation = animation;
    host._view = {_closeMenus: () => animation._cancelOpen(menu)};
    animation._animate = () => {};
    return {animation, menu, anchor, parent, stage, host};
}

test('a valid anchor opens immediately without forcing layout', () => {
    const {animation, menu, stage} = fixture();
    animation._expand(menu, 0);
    assert.equal(menu.opened, 1);
    assert.equal(stage.signals.size, 0);
});

test('reconstructed anchors open only after their ancestors finish allocating', () => {
    const {animation, menu, anchor, parent, stage} = fixture();
    anchor.allocated = false;
    parent.allocated = false;
    animation._expand(menu, 0);
    assert.equal(menu.opened, 0);
    stage.emit('after-update');
    assert.equal(menu.opened, 0);
    assert.equal(stage.signals.size, 0);
    anchor.allocated = true;
    anchor.emit('notify::allocation');
    stage.emit('after-update');
    assert.equal(menu.opened, 0);
    parent.allocated = true;
    parent.emit('notify::allocation');
    stage.emit('after-update');
    assert.equal(menu.opened, 1);
    assert.equal(menu._pendingOpen, null);
    assert.equal(stage.signals.size + parent.signals.size + anchor.signals.size, 0);
});

test('invalid geometry waits passively and does not schedule a frame loop', () => {
    const {animation, menu, anchor, stage} = fixture();
    anchor.allocation.x1 = NaN;
    animation._expand(menu, 0);
    stage.emit('after-update');
    stage.emit('after-update');
    assert.equal(menu.opened, 0);
    assert.equal(stage.signals.size, 0);
    anchor.allocation.x1 = 12;
    anchor.emit('notify::allocation');
    stage.emit('after-update');
    assert.equal(menu.opened, 1);
});

test('closing or stopping a deferred menu releases every callback', () => {
    const {animation, menu, anchor, parent, stage} = fixture();
    anchor.allocated = false;
    animation._expand(menu, 0);
    animation._stopAnimation(menu);
    anchor.allocated = true;
    anchor.emit('notify::allocation');
    stage.emit('after-update');
    assert.equal(menu.opened, 0);
    assert.equal(menu._pendingOpen, null);
    assert.equal(stage.signals.size + parent.signals.size + anchor.signals.size, 0);
});

test('disabling or destroying a pending menu cannot open it later', () => {
    for (const destroyed of [false, true]) {
        const {animation, menu, anchor, stage, host} = fixture();
        anchor.allocated = false;
        animation._expand(menu, 0);
        if (destroyed) menu._destroying = true;
        else host._enabled = false;
        anchor.allocated = true;
        stage.emit('after-update');
        assert.equal(menu.opened, 0);
        assert.equal(stage.signals.size + anchor.signals.size, 0);
    }
});
