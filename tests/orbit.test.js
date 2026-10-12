// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {orbitVelocity, orbitFrame, orbitHoverFrame, orbitMiniatures} from '../core/orbit.js';
import {hoverDuration, hoverRotation, preference, normalize} from '../core/preferences.js';
import {miniIconLayout} from '../core/iconGeometry.js';

test('orbital modes default to zero and pause when disabled or invisible', () => {
    assert.equal(orbitVelocity(), 0);
    for (const hovered of [false, true]) {
        assert.equal(orbitVelocity({}, hovered), 0);
        const paused = orbitFrame({angle: 47, elapsed: 100, hovered, allowed: false,
            values: {orbitSpeed: 120, hoverOrbitSpeed: 180}});
        assert.deepEqual(paused, {angle: 47, velocity: 0, active: false});
    }
    assert.equal(orbitVelocity({enabled: false, orbitSpeed: 120}, true), 0);
});

test('hover replaces continuous speed and can slow down or speed up without jumping', () => {
    for (const [base,hover] of [[180,30],[30,180],[-180,-30],[-30,-180],[180,-180],[-180,180]]) {
        const values = {orbitSpeed: base, hoverOrbitSpeed: hover};
        assert.equal(orbitVelocity(values, false), base);
        assert.equal(orbitVelocity(values, true), hover);
        let state = {angle: 74, velocity: base};
        const unchanged = orbitFrame({...state, values, hovered: true});
        assert.equal(unchanged.angle, state.angle);
        assert.equal(unchanged.velocity, base);
        for (let index=0;index<14;index++) {
            const next = orbitFrame({...state, elapsed:100, values, hovered:true});
            assert.ok(next.velocity > Math.min(base,hover) && next.velocity < Math.max(base,hover));
            assert.equal(Math.sign(next.velocity-state.velocity), Math.sign(hover-base));
            state = next;
        }
        assert.ok(Math.abs(state.velocity-hover)<.2);
        const entered = state.velocity;
        state = orbitFrame({...state, elapsed:33, values, hovered:false});
        assert.ok(Math.abs(state.velocity-entered)<Math.abs(base-entered));
        assert.equal(Math.sign(state.velocity-entered),Math.sign(base-hover));
    }
    assert.equal(orbitVelocity({orbitSpeed:90,hoverOrbitSpeed:0},true),90);
});

test('hover-only motion coasts to rest, then releases its clock without resetting phase', () => {
    const values = {orbitSpeed:0,hoverOrbitSpeed:180};
    let state = orbitFrame({angle:350,elapsed:33,values,hovered:true});
    assert.ok(state.velocity>0 && state.velocity<180);
    const initial=state.angle;
    state=orbitFrame({...state,elapsed:33,values,hovered:false});
    assert.ok(state.active && state.velocity>0);
    for(let index=0;index<30;index++)state=orbitFrame({...state,elapsed:100,values});
    assert.equal(state.velocity,0);
    assert.equal(state.active,false);
    assert.notEqual(state.angle,initial);
    assert.deepEqual(orbitFrame({...state,elapsed:100,values}),state);
});

test('rotation is independent of frame rate and bounds delayed or invalid frames', () => {
    const simulate = step => {
        let state = {angle:0,velocity:0};
        for (let time = 0; time < 1000; time += step)
            state = orbitFrame({...state, elapsed: step, values: {orbitSpeed: 180}});
        return state.angle;
    };
    assert.ok(Math.abs(simulate(10)-simulate(50)) < 1e-8);
    assert.equal(orbitFrame({velocity:180, elapsed: 10000, values: {orbitSpeed: 180}}).angle, 18);
    assert.equal(orbitFrame({elapsed: -10, values: {orbitSpeed: 180}}).angle, 0);
    assert.equal(orbitFrame({angle: NaN, elapsed: Infinity}).angle, 0);
    assert.equal(orbitVelocity({orbitSpeed: 999, hoverOrbitSpeed: -10}, true), -10);
    assert.equal(orbitVelocity({orbitSpeed: -1500}), -999);
});

test('moving miniatures preserve glyph orientation, orbital size and card reveal', () => {
    for (const count of [2,3,4,5,8]) for (const vertical of [false,true]) for (const reveal of [0,.5,1]) {
        const args = [56,count,2.3,90,vertical,'orbit',20,count>5,reveal,true];
        const before = miniIconLayout(...args);
        const moving = orbitMiniatures({args,angle:57,velocity:90,elapsed:100,values:{orbitSpeed:90}});
        assert.equal(moving.angle, 66);
        assert.equal(moving.layout.size, before.size);
        assert.equal(moving.layout.width, before.width);
        assert.equal(moving.layout.height, before.height);
        moving.layout.items.forEach((item,index) => {
            const old = before.items[index];
            assert.ok(Math.abs(item.rotation+item.glyphRotation-old.rotation-old.glyphRotation)<1e-8);
            assert.equal(item.opacity, old.opacity);
        });
        if (reveal===0) assert.notDeepEqual(moving.layout.items.map(({x,y})=>[x,y]),before.items.map(({x,y})=>[x,y]));
    }
});

test('returning hover rotation never reverses an enabled orbit, including rapid pointer changes', () => {
    const values={orbitSpeed:5,hoverOrbitSpeed:360,hoverEffect:'rotate-cards',hoverAngle:45};
    let angle=74,progress=1,total=angle+45;
    for(const next of [.95,.8,.4,.75,.3,0,.25,.9,.2,0]) {
        const frame=orbitHoverFrame({angle,previous:progress,progress:next,values});
        const shown=frame.angle+next*45;
        assert.ok(shown>=total-1e-8);
        angle=frame.angle;progress=next;total=shown;
    }
    const idle=orbitHoverFrame({angle:74,previous:1,progress:.5,
        values:{hoverEffect:'rotate',hoverAngle:45}});
    assert.equal(idle.angle,74);
    assert.equal(orbitHoverFrame({angle:74,previous:1,progress:0,
        values:{...values,hoverEffect:'cards'}}).angle,74);
    assert.equal(orbitHoverFrame({angle:74,previous:1,progress:0,
        values:{...values,enabled:false}}).angle,74);
});

test('hover speed supports both directions from minus 999 through plus 999 percent', () => {
    const speed=preference('hoverSpeed');
    assert.equal(normalize(speed,999),999);
    assert.equal(normalize(speed,1500),999);
    assert.equal(normalize(speed,-1500),-999);
    assert.equal(normalize(speed,0),0);
    assert.ok(hoverDuration(999)>0 && hoverDuration(999)<hoverDuration(200));
    assert.equal(hoverDuration(-999),hoverDuration(999));
    assert.equal(hoverDuration(0),0);
    assert.equal(hoverRotation({hoverEffect:'rotate',hoverAngle:45,hoverSpeed:-999}),-45);
    assert.equal(hoverRotation({hoverEffect:'rotate',hoverAngle:45,hoverSpeed:999}),45);
    assert.equal(hoverRotation({hoverEffect:'rotate',hoverAngle:45,hoverSpeed:0}),0);
    assert.equal(hoverRotation({hoverEffect:'cards',hoverSpeed:-999}),0);
});

test('negative hover return is absorbed and counterclockwise motion coasts to rest', () => {
    const values={orbitSpeed:0,hoverOrbitSpeed:-180,hoverEffect:'rotate',hoverAngle:45,hoverSpeed:-999};
    const absorbed=orbitHoverFrame({angle:74,previous:1,progress:0,values});
    assert.equal(absorbed.angle,29);
    let state=orbitFrame({angle:74,elapsed:100,hovered:true,values});
    assert.ok(state.active && state.velocity<0 && state.angle<74);
    for(let i=0;i<30;i++) state=orbitFrame({...state,elapsed:100,values});
    assert.equal(state.velocity,0);
    assert.equal(state.active,false);
    assert.ok(state.angle>=0 && state.angle<360);
    assert.deepEqual(orbitFrame({...state,elapsed:100,values}),state);
    const args=[56,4,1,90,false,'signed',0,false,0,false];
    const miniature=orbitMiniatures({args,values,hoverProgress:1});
    const expected=miniIconLayout(...args.slice(0,6),-45,...args.slice(7));
    assert.deepEqual(miniature.layout,expected);
});

 test('rotation reaches both 999 degree endpoints without a clamp-induced plateau', () => {
    for (const speed of [-999,999]) {
        const values={orbitSpeed:0,hoverOrbitSpeed:speed};
        let state={angle:0,velocity:0};
        for(let i=0;i<40;i++) state=orbitFrame({...state,elapsed:100,values,hovered:true});
        assert.equal(state.velocity,speed);
        assert.ok(state.active && state.angle>=0 && state.angle<360);
        assert.equal(orbitVelocity({hoverOrbitSpeed:speed*2},true),speed);
    }
 });
