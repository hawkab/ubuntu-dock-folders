// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {miniIconLayout, folderOrientation} from '../extension/iconGeometry.js';

test('layout results remain independent after a caller mutation and cache eviction', () => {
    const args = [48,3,2.3,60,false,'folder-test',45];
    const expected = miniIconLayout(...args);
    const edited = miniIconLayout(...args);
    edited.items[0].x = 100000;
    for (let index=0;index<400;index++) miniIconLayout(48,3,1+index/1000,60,false,'folder-'+index);
    assert.deepEqual(miniIconLayout(...args),expected);
});

function corners(item,size) {
    const t=item.rotation*Math.PI/180,cx=item.x+size/2,cy=item.y+size/2;
    return [-size/2,size/2].flatMap(x=>[-size/2,size/2].map(y=>
        [cx+x*Math.cos(t)-y*Math.sin(t),cy+x*Math.sin(t)+y*Math.cos(t)]));
}

function separate(a,b,size) {
    const t=a.rotation*Math.PI/180,dx=a.x-b.x,dy=a.y-b.y;
    return Math.abs(dx*Math.cos(t)+dy*Math.sin(t))>=size-1e-8
        || Math.abs(-dx*Math.sin(t)+dy*Math.cos(t))>=size-1e-8;
}

test('rigid miniatures remain separate and their rotated corners fit the panel', () => {
    for(const vertical of [false,true]) for(const body of [24,44,72,96]) {
        for(let count=1;count<=5;count++) for(const scale of [.8,1,1.3,1.6,2,3]) {
            const cross=body+12;
            for(let rotation=0;rotation<360;rotation+=15) {
                const layout=miniIconLayout(body,count,scale,cross,vertical,"test",rotation);
                assert.equal(layout.items.length,count);
                for(let a=0;a<count;a++) {
                    for(const point of corners(layout.items[a],layout.size)) {
                        const coordinate=point[vertical ? 0 : 1];
                        assert.ok(coordinate >= (body-cross)/2-1e-8);
                        assert.ok(coordinate <= (body+cross)/2+1e-8);
                    }
                    for(let b=a+1;b<(count === 5 ? 4 : count);b++) assert.ok(separate(layout.items[a],layout.items[b],layout.size));
                }
            }
        }
    }
});

test('two mini-icons are centered as a pair rather than occupying the upper row', () => {
    for (const vertical of [false, true]) for (const scale of [.8, 1, 1.6]) {
        const {items, size} = miniIconLayout(48, 2, scale, 60, vertical);
        assert.ok(Math.abs((items[0].x + items[1].x + size) / 2 - 24) < 1e-8);
        assert.ok(Math.abs((items[0].y + items[1].y + size) / 2 - 24) < 1e-8);
    }
});

test('enlargement expands the miniature cluster beyond an unchanged folder circle', () => {
    const normal = miniIconLayout(48, 4, 1, 84, false);
    const large = miniIconLayout(48, 4, 3, 84, false);
    assert.ok(large.size > normal.size);
    assert.ok(large.width > 48);
    assert.ok(large.items.some(item => item.x < 0));
    assert.ok(large.items.some(item => item.x + large.size > 48));
    const empty = miniIconLayout(48, 0, 1, 60, false);
    assert.deepEqual(empty.items, []);
    assert.equal(empty.width, 48);
});


test('folder identity chooses a stable triangle orientation and rotation remains editable', () => {
    const angles = new Set(Array.from({length: 32}, (_, index) => folderOrientation('folder-' + index)));
    assert.equal(angles.size, 4);
    const triangle = miniIconLayout(48, 3, 1, 60, false, 'folder-1');
    assert.deepEqual(triangle, miniIconLayout(48, 3, 1, 60, false, 'folder-1'));
    assert.notDeepEqual(triangle.items, miniIconLayout(48, 3, 1, 60, false, 'folder-1', 90).items);
    const [a, b, c] = triangle.items;
    assert.ok(Math.abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)) > 1);
});

test('four and five applications form dice faces with a centered fifth icon', () => {
    for (const count of [4, 5]) {
        const {items, size} = miniIconLayout(48, count, 1, 80, false);
        assert.equal(items[0].y, items[1].y);
        assert.equal(items[2].y, items[3].y);
        assert.equal(items[0].x, items[2].x);
        assert.equal(items[1].x, items[3].x);
        if (count === 5) assert.ok(Math.hypot(items[4].x + size/2 - 24, items[4].y + size/2 - 24) < 1e-8);
    }
});

test('large folders use a bounded card stack, which can also be forced on smaller folders', () => {
    for (const count of [2, 3, 4, 5, 6, 10000]) for (const vertical of [false, true]) {
        const layout = miniIconLayout(48, count, 1.6, 60, vertical, 'test', 45, true);
        assert.ok(layout.stacked);
        assert.equal(layout.items.length, Math.min(count, 5));
        assert.ok(layout.items.some(item => item.rotation !== 0));
        assert.ok((vertical ? layout.width : layout.height) <= 60);
    }
    assert.ok(miniIconLayout(48, 6, 1, 60, false).stacked);
});

test('continuous rotation keeps clusters finite and prevents nearly aligned icons from spreading indefinitely', () => {
    for (let count=2;count<=5;count++) for (let rotation=0;rotation<360;rotation++) {
        const layout=miniIconLayout(52,count,3,46,false,'test',rotation);
        assert.ok(layout.width <= 3*52, JSON.stringify({count,rotation,layout}));
        for (let a=0;a<count;a++) for (let b=a+1;b<(count === 5 ? 4 : count);b++) {
            assert.ok(separate(layout.items[a],layout.items[b],layout.size));
        }
    }
});


test('rotation preserves miniature size, orbit radius, pair distances and reserved hit area', () => {
    for (const vertical of [false,true]) for (const count of [2,3,4,5,6]) for (const cards of [false,true]) {
        const base=miniIconLayout(48,count,1.2,60,vertical,'test',0,cards);
        const center=item=>[item.x+base.size/2-24,item.y+base.size/2-24];
        for(let angle=0;angle<360;angle++) {
            const turned=miniIconLayout(48,count,1.2,60,vertical,'test',angle,cards);
            assert.equal(turned.size,base.size);
            assert.equal(turned.width,base.width); assert.equal(turned.height,base.height);
            base.items.forEach((item,index)=> {
                const a=center(item),b=center(turned.items[index]);
                assert.ok(Math.abs(Math.hypot(...a)-Math.hypot(...b))<1e-8);
                for(let other=0;other<index;other++) {
                    const c=center(base.items[other]),d=center(turned.items[other]);
                    assert.ok(Math.abs(Math.hypot(a[0]-c[0],a[1]-c[1])-Math.hypot(b[0]-d[0],b[1]-d[1]))<1e-8);
                }
            });
        }
    }
});

test('orbital rotation keeps each application glyph in its original orientation on every hover frame', () => {
    for (const vertical of [false,true]) for (const count of [1,2,3,4,5,8])
        for (const cards of [false,true]) for (const reveal of [0,.2,.5,.8,1]) {
            const base=miniIconLayout(48,count,2.3,60,vertical,'test',0,cards,reveal,true);
            for (const angle of [-45,30,90,180,270,405]) {
                const moved=miniIconLayout(48,count,2.3,60,vertical,'test',angle,cards,reveal,true);
                moved.items.forEach((item,index) => {
                    assert.ok(Math.abs(item.rotation+item.glyphRotation-base.items[index].rotation)<1e-8);
                });
                assert.equal(moved.size,base.size);
                assert.equal(moved.width,base.width);
                assert.equal(moved.height,base.height);
                if (count>1 && reveal===0)
                    assert.notDeepEqual(moved.items.map(({x,y})=>[x,y]),base.items.map(({x,y})=>[x,y]));
            }
        }
});

test('card reveal expands only stacks and preserves miniature size within twice the folder width',()=> {
    for(const vertical of [false,true]) for(const count of [2,3,4,5,8]) {
        const resting=miniIconLayout(48,count,1,60,vertical,'test',45,true,0,true);
        const opened=miniIconLayout(48,count,1,60,vertical,'test',45,true,1,true);
        const axis=vertical ? 'height' : 'width', cross=vertical ? 'width' : 'height';
        assert.ok(opened[axis]>resting[axis]); assert.equal(opened[cross],resting[cross]);
        assert.ok(opened[axis]<=opened.bodySize*2);
        assert.equal(opened.items.length,count);
        assert.equal(resting.size,opened.size);
        assert.ok(opened.items.some((item,index)=>Math.hypot(item.x-resting.items[index].x,item.y-resting.items[index].y)>1));
        assert.equal(opened.cardOpacity,1);
        for(const item of opened.items) for(const point of corners(item,opened.size)) {
            const cross=point[vertical ? 0 : 1];
            assert.ok(Math.abs(cross-24)<=30);
        }
        if(count<=5) {
            const flat=miniIconLayout(48,count,1,60,vertical,'test',45,false,0,false);
            assert.deepEqual(flat,miniIconLayout(48,count,1,60,vertical,'test',45,false,1,true));
            assert.equal(flat.cardOpacity,0);
        }
    }
});

test('the upper slider range keeps enlarging miniatures in a thin panel',()=> {
    for(const vertical of [false,true]) for(const count of [2,3,4,5,8]) {
        let previous=0;
        for(let step=80;step<=300;step+=5) {
            const layout=miniIconLayout(52,count,step/100,46,vertical,'test');
            assert.ok(layout.size>previous,JSON.stringify({count,step,size:layout.size,previous}));
            previous=layout.size;
        }
    }
    const cube=miniIconLayout(52,4,3,46,false,'test');
    assert.ok(cube.size>14);
    assert.ok(Math.abs(cube.items[1].x-cube.items[0].x-cube.size-1.04)<1e-6);
});

test('the fifth icon overlays a compact four-icon formation without a reserved center gap',()=> {
    for(const scale of [1,1.6,2,3]) for(const angle of [0,30,90,180,270]) {
        const four=miniIconLayout(52,4,scale,46,false,'test',angle);
        const five=miniIconLayout(52,5,scale,46,false,'test',angle);
        assert.equal(five.size,four.size);
        assert.deepEqual(five.items.slice(0,4),four.items);
        for(const outer of five.items.slice(0,4)) assert.ok(!separate(outer,five.items[4],five.size));
        assert.ok(Math.hypot(five.items[4].x+five.size/2-26,five.items[4].y+five.size/2-26)<1e-8);
    }
});

test('large folder settings respect panel thickness and do not clip their circular background',()=> {
    for(const vertical of [false,true]) {
        const normal=miniIconLayout(40,5,1,46,vertical);
        const large=miniIconLayout(80,5,3,46,vertical);
        assert.ok(large.bodySize>normal.bodySize);
        assert.ok(large.bodySize*.86<=46);
        assert.ok(large.size>normal.size);
        assert.ok((vertical ? large.width : large.height)<80);
    }
});

test('hover rotation remains visible when card reveal is also enabled',()=> {
    const original=miniIconLayout(48,8,1,60,false,'test',0,false,1,true);
    const rotated=miniIconLayout(48,8,1,60,false,'test',60,false,1,true);
    rotated.items.forEach((item,index)=>assert.ok(Math.abs(item.rotation-original.items[index].rotation-60)<1e-8));
    assert.equal(original.size,rotated.size);
    assert.equal(original.width,rotated.width);
});

test('idle stacks reserve no space for a fan, regardless of the hover checkbox',()=> {
    for (const count of [2,5,8,30]) for (const vertical of [false,true]) {
        const disabled=miniIconLayout(48,count,1,60,vertical,'test',0,true,0,false);
        const enabled=miniIconLayout(48,count,1,60,vertical,'test',0,true,0,true);
        assert.deepEqual(enabled,disabled);
        assert.equal(enabled.width,48); assert.equal(enabled.height,48);
        assert.deepEqual(disabled,miniIconLayout(48,count,1,60,vertical,'test',0,true,1,false));
    }
});

test('fans render every application and grow continuously within the two-width limit',()=> {
    for (const count of [6,8,25,433]) for (const vertical of [false,true]) for (const angle of [0,45,90,180]) {
        const axis=vertical ? 'height' : 'width';
        let previous=0;
        for (const reveal of [0,.01,.2,.5,.8,1]) {
            const layout=miniIconLayout(48,count,3,60,vertical,'test',angle,false,reveal,true);
            assert.equal(layout.items.length,reveal ? count : 5);
            assert.ok(layout[axis]>=previous && layout[axis]<=layout.bodySize*2+1e-8);
            previous=layout[axis];
            for (const item of layout.items) for (const corner of corners(item,layout.size)) {
                const along=corner[vertical ? 1 : 0]-layout.bodySize/2;
                const across=corner[vertical ? 0 : 1]-layout.bodySize/2;
                assert.ok(Math.abs(along)<=layout[axis]/2+1e-8);
                assert.ok(Math.abs(across)<=30+1e-8);
            }
        }
    }
});
