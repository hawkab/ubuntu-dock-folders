// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {contract} from '../core/contract.js';
import {settingsPreview,settingsPreviewFrame} from '../core/settingsPreview.js';

const apps=['a','b','c'].map(desktop=>({desktop,label:desktop}));
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-6,`${a} != ${b}`);

test('dock preview responds to size and fans all seven cards only on hover',()=>{
    const scene=values=>settingsPreview({values,apps});
    const small=scene({groupIconSize:80,groupMiniIconSize:80});
    const large=scene({groupIconSize:200,groupMiniIconSize:300});
    assert.ok(large.commands.find(item=>item.type==='icon').size>small.commands.find(item=>item.type==='icon').size);
    const revealed=settingsPreview({values:{hoverEffect:'rotate-cards',hoverAngle:30},apps,hover:1});
    assert.equal(revealed.commands.filter(item=>item.type==='icon').length,11);
    assert.ok(revealed.commands.filter(item=>item.type==='icon').every(item=>item.alpha===1));
    assert.equal(small.commands.filter(item=>item.type==='text').length,0);
    assert.equal(settingsPreview({apps,labels:true}).commands.filter(item=>item.type==='text').length,2);
});

test('preview labels remain below oversized orbit icons',()=>{
    for(const hover of [0,1]){
        const scene=settingsPreview({apps,labels:true,hover,values:{
            groupIconSize:200,groupMiniIconSize:300,hoverEffect:'rotate-cards',hoverAngle:180,fontSize:24}});
        let bottom=0;
        for(const item of scene.commands){
            if(item.type==='circle')bottom=0;
            if(item.type==='icon'){
                const radians=item.rotation*Math.PI/180;
                const half=item.size*(Math.abs(Math.cos(radians))+Math.abs(Math.sin(radians)))/2;
                bottom=Math.max(bottom,item.y+item.size/2+half);
            }
            if(item.type==='text')assert.ok(item.y>bottom && item.y+item.size<214);
        }
    }
});

test('preview glyphs keep their orientation while flat icons and cards orbit',()=>{
    for(const hover of [0,.1,.5,.9,1]){
        const scene=angle=>settingsPreview({apps,hover,values:{hoverEffect:'rotate-cards',hoverAngle:angle}});
        const before=scene(0).commands.filter(item=>item.type==='icon');
        const after=scene(90).commands.filter(item=>item.type==='icon');
        after.forEach((item,index)=>close(item.rotation,before[index].rotation));
        if(hover>0)assert.notDeepEqual(after.map(({x,y})=>[x,y]),before.map(({x,y})=>[x,y]));
    }
});

test('every animation has finite transforms; native Cairo decompositions match the affine mesh',()=>{
    for(const effect of contract.animations)for(const opening of [false,true])for(const time of [0,.1,.3,.7,1]){
        const scene=settingsPreview({mode:'popup',apps,values:{animation:effect.key}});
        const result=settingsPreviewFrame({scene,time,opening});
        assert.ok(result.opacity>=0 && result.opacity<=1);
        for(const item of result.triangles){
            assert.ok([...item.matrix,...item.transform].every(Number.isFinite));
            const [tx,ty,left,sx,sy,right]=item.transform;
            const [a,b,c,d,e,f]=item.matrix;
            close(Math.cos(left)*sx*Math.cos(right)-Math.sin(left)*sy*Math.sin(right),a);
            close(Math.sin(left)*sx*Math.cos(right)+Math.cos(left)*sy*Math.sin(right),b);
            close(-Math.cos(left)*sx*Math.sin(right)-Math.sin(left)*sy*Math.cos(right),c);
            close(-Math.sin(left)*sx*Math.sin(right)+Math.cos(left)*sy*Math.cos(right),d);
            close(tx,e);close(ty,f);
        }
        if(time===(opening ? 1:0)){
            assert.equal(result.triangles.length,128);
            for(const {matrix} of result.triangles)[1,0,0,1,0,0].forEach((value,index)=>close(matrix[index],value));
        }
    }
});
