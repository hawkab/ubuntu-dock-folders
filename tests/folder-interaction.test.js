// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import test from 'node:test';
import assert from 'node:assert/strict';
import {folderInteraction} from '../core/folderInteraction.js';

test('a folder click opens, switches or closes in one decision', () => {
    assert.deepEqual(folderInteraction({target:'a'}), {target:'a',close:null,open:'a',anchorIndex:-1});
    assert.deepEqual(folderInteraction({current:'a',target:'b'}), {target:'b',close:'a',open:'b',anchorIndex:-1});
    assert.deepEqual(folderInteraction({current:'b',target:'b'}), {target:'b',close:'b',open:null,anchorIndex:-1});
    assert.deepEqual(folderInteraction({current:'b'}), {target:null,close:'b',open:null,anchorIndex:-1});
});

test('captured presses resolve full dock bounds and the clicked monitor copy', () => {
    const anchors = [{key:'a',x:40,y:500,width:48,height:60}, {key:'b',x:90,y:500,width:48,height:60},
        {key:'b',x:1600,y:40,width:60,height:48}];
    for (const [point,key,index] of [[{x:40,y:500},'a',0],[{x:91,y:501},'b',1],[{x:1659,y:87},'b',2]]) {
        const value = folderInteraction({current:'a',anchors,point});
        assert.equal(value.target,key);
        assert.equal(value.anchorIndex,index);
        assert.equal(value.open,key === 'a' ? null : key);
    }
    for (const point of [{x:138,y:500},{x:90,y:560},{x:NaN,y:500}])
        assert.equal(folderInteraction({current:'a',anchors,point}).open,null);
    assert.equal(folderInteraction({anchors:[{key:'a',x:0,y:0,width:0,height:48}],point:{x:0,y:0}}).target,null);
});
