// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';

import * as geometry from '../core/animationGeometry.js';
const rect = {x: 40, y: 30, width: 330, height: 180};
const anchors = [{x: 110, y: 240}, {x: 110, y: 0}, {x: 0, y: 90}, {x: 400, y: 90}];

test('animations collapse onto the correct icon and end at the original card on every edge', () => {
    for (let edge = 0; edge < 4; edge++) {
        for (const genie of [1, 4, 5, 7]) {
            for (const point of [{x: 40, y: 30}, {x: 370, y: 210}, {x: 110, y: 95}]) {
                const closed = geometry.deform(point, rect, anchors[edge], 0, edge, genie);
                const opened = geometry.deform(point, rect, anchors[edge], 1, edge, genie);
                assert.ok(Math.hypot(closed.x - anchors[edge].x, closed.y - anchors[edge].y) < 1e-6);
                assert.ok(Math.hypot(opened.x - point.x, opened.y - point.y) < 1e-6);
            }
        }
    }
});

test('genie holds its neck at the icon while the far edge unfolds', () => {
    const neck = geometry.deform({x: 205, y: 210}, rect, anchors[0], .5, 0, 1);
    const head = geometry.deform({x: 205, y: 30}, rect, anchors[0], .5, 0, 1);
    assert.equal(neck.y, anchors[0].y);
    assert.equal(neck.x, anchors[0].x);
    assert.ok(head.y < anchors[0].y - 150);
});

test('sheet preserves width while a tilted plane grows along its dock axis', () => {
    const center = {x: rect.x+rect.width/2, y: rect.y+rect.height/2};
    const left = geometry.deform({x: rect.x, y: center.y}, rect, anchors[0], .5, 0, 8);
    const right = geometry.deform({x: rect.x+rect.width, y: center.y}, rect, anchors[0], .5, 0, 8);
    assert.equal(right.x-left.x, rect.width);
    const top = geometry.deform({x:center.x,y:rect.y},rect,anchors[0],.5,0,8);
    const bottom = geometry.deform({x:center.x,y:rect.y+rect.height},rect,anchors[0],.5,0,8);
    assert.ok(bottom.y-top.y < rect.height*.5);
    assert.ok(bottom.y > top.y);
});

test('sheet starts as a full-width edge and ends at the original card on every dock side', () => {
    for (let edge=0; edge<4; edge++) {
        const vertical=edge<2;
        const a=geometry.deform({x:rect.x,y:rect.y},rect,anchors[edge],0,edge,8);
        const b=geometry.deform({x:rect.x+rect.width,y:rect.y+rect.height},rect,anchors[edge],0,edge,8);
        assert.equal(vertical ? b.x-a.x : b.y-a.y, vertical ? rect.width : rect.height);
        assert.equal(vertical ? a.y : a.x, vertical ? anchors[edge].y : anchors[edge].x);
        for (const point of [{x:rect.x,y:rect.y},{x:rect.x+rect.width,y:rect.y+rect.height}])
            assert.ok(Math.hypot(...Object.values(geometry.deform(point,rect,anchors[edge],1,edge,8)).map((v,index)=>v-Object.values(point)[index]))<1e-8);
    }
});

test('fade keeps its geometry fixed throughout opening and closing', () => {
    for (let edge=0;edge<4;edge++) for (let frame=0;frame<=100;frame++) {
        const point={x:rect.x+150,y:rect.y+50};
        const mapped=geometry.deform(point,rect,anchors[edge],frame/100,edge,10);
        assert.equal(mapped.x,point.x); assert.equal(mapped.y,point.y);
    }
});

test('blur follows a finite rounded outline throughout opening and closing', () => {
    for (let edge = 0; edge < 4; edge++) {
        for (const style of [0, 1, 4, 5, 7, 8, 10]) for (let frame = 0; frame <= 100; frame++) {
            const points = geometry.outline(rect, anchors[edge], frame / 100, edge, style, 20);
            assert.ok(points.length >= 60);
            assert.ok(points.every(p => Number.isFinite(p.x) && Number.isFinite(p.y)));
        }
    }
});


test('unfold hinges a plane, unlike the curved genie and axial sheet', () => {
    const point = {x: 300, y: 40};
    const results = [1, 7, 8].map(style => geometry.deform(point, rect, anchors[0], .5, 0, style));
    for (let a = 0; a < results.length; a++) for (let b = a + 1; b < results.length; b++)
        assert.ok(Math.hypot(results[a].x - results[b].x, results[a].y - results[b].y) > 10);
});
