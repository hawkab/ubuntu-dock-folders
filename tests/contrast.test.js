// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import test from 'node:test';
import {contrastColor, surface} from '../core/preferences.js';

const luminance = color => [1,3,5].map(index => parseInt(color.slice(index,index+2),16) / 255)
    .map(value => value <= .04045 ? value / 12.92 : ((value+.055)/1.055)**2.4)
    .reduce((total,value,index) => total + value * [.2126,.7152,.0722][index],0);

test('black or white labels satisfy normal text contrast on opaque backgrounds', () => {
    for (let r=0;r<=255;r+=17) for(let g=0;g<=255;g+=17) for(let b=0;b<=255;b+=17) {
        const background='#'+[r,g,b].map(value=>value.toString(16).padStart(2,'0')).join('');
        const dark=luminance(background), foreground=luminance(contrastColor(background));
        const ratio=(Math.max(dark,foreground)+.05)/(Math.min(dark,foreground)+.05);
        assert.ok(ratio >= 4.5, `${background}: ${ratio}`);
    }
});

test('transparent folders adapt to light and dark windows behind the same tint', () => {
    const group={popupColor:'#26262a',backgroundOpacity:.01};
    for(const blur of [0,25,100]) {
        assert.equal(surface(group,blur,true,'#ffffff').foreground,'#000000');
        assert.equal(surface(group,blur,true,'#000000').foreground,'#ffffff');
    }
    assert.equal(surface({...group,backgroundOpacity:1},100,true,'#ffffff').foreground,'#ffffff');
    assert.equal(surface({popupColor:'#ffffff',backgroundOpacity:1},100).foreground,'#000000');
    assert.equal(contrastColor('invalid'),'#ffffff');
});
