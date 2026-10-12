/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

import {contract} from './contract.js';

const formations = new Map();
const [minimumScale, maximumScale] = contract.preferences.find(item => item.name === 'groupMiniIconSize').range.map(value => value / 100);

/** Return a folder's stable orientation from its identity. */
export function folderOrientation(identity) {
    let hash = 2166136261;
    for (const letter of String(identity)) hash = Math.imul(hash ^ letter.charCodeAt(0), 16777619) >>> 0;
    return hash % 4 * Math.PI / 2;
}

/** Measure the enclosing circle of glyph corners without depending on rotation. */
function radiusOf(centers, size) {
    let radius = 0;
    for (const item of centers) {
        const angle = item.rotation * Math.PI / 180;
        for (const x of [-size/2,size/2]) for (const y of [-size/2,size/2])
            radius = Math.max(radius,Math.hypot(item.x+x*Math.cos(angle)-y*Math.sin(angle),
                item.y+x*Math.sin(angle)+y*Math.cos(angle)));
    }
    return radius;
}

/** Cache a formation's dimensions and resting positions independently of motion. */
function formation(bodySize, count, scale, crossSize, vertical, orientation, stacked) {
    const key = [bodySize,count,scale,crossSize,vertical,orientation,stacked].join(':');
    const cached = formations.get(key);
    if (cached) {
        formations.delete(key);
        formations.set(key,cached);
        return cached;
    }
    const restingCount = Math.min(contract.layout.maxMiniatures,count), gap = Math.max(1,bodySize*.02);
    let points = count === 0 ? [] : count === 1 ? [[0,0]] : count === 2 ? [[-.5,0],[.5,0]]
        : count === 3 ? Array.from({length:3},(_,index) => {
            const angle = orientation+index*Math.PI*2/3;
            return [Math.cos(angle),Math.sin(angle)];
        }) : [[-.5,-.5],[.5,-.5],[-.5,.5],[.5,.5]];
    if (count === 5) points.push([0,0]);
    if (count === 2 && vertical) points = [[0,-.5],[0,.5]];
    let separation = Infinity;
    const separateCount = count === 5 ? 4 : points.length;
    for (let a=0;a<separateCount;a++) for (let b=a+1;b<separateCount;b++)
        separation = Math.min(separation,Math.max(Math.abs(points[a][0]-points[b][0]),Math.abs(points[a][1]-points[b][1])));
    const factor = Number.isFinite(separation) ? 1/separation : 0;
    const place = size => stacked ? Array.from({length:restingCount},(_,index) => {
        const offset=index-(restingCount-1)/2;
        return {x:offset*size*.04,y:offset*size*.005,rotation:offset*4};
    }) : points.map(([x,y]) => ({x:x*factor*(size+gap),y:y*factor*(size+gap),rotation:0}));
    const nominal = bodySize*(stacked ? .62 : count <= 2 ? .55 : .32);
    let low=0,high=nominal*maximumScale;
    for (let iteration=0;iteration<18;iteration++) {
        const trial=(low+high)/2;
        if (2*radiusOf(place(trial),trial) <= Math.min(crossSize,bodySize*2)) low=trial; else high=trial;
    }
    const maximum=low, baseline=Math.min(nominal,maximum*.8);
    const size=scale <= 1 ? baseline*scale : baseline+(maximum-baseline)*(scale-1)/(maximumScale-1);
    const resting=place(size), radius=radiusOf(resting,size);
    const extent=Math.max(bodySize,2*radius), projected=size*Math.SQRT2;
    const step=count>1 ? Math.max(0,Math.min(size*.65,(bodySize*2-projected)/(count-1))) : 0;
    const fanExtent=Math.max(extent,Math.min(bodySize*2,(count-1)*step+projected));
    const result = {size,resting,restingCount,extent,step,fanExtent};
    formations.set(key,result);
    if (formations.size > 256) formations.delete(formations.keys().next().value);
    return result;
}

/** Return orbital placements with independent card and local glyph angles. */
export function miniIconLayout(bodySize, count, scale, crossSize, vertical, identity = '', rotation = 0, alwaysStack = false, reveal = 0, revealCards = true) {
    crossSize = Math.max(8, Number.isFinite(crossSize) ? crossSize : bodySize + 12);
    bodySize = Math.min(bodySize, crossSize / contract.layout.circleScale);
    rotation = Number.isFinite(rotation) ? rotation : 0;
    count = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0;
    scale = Math.max(minimumScale,Math.min(maximumScale,Number.isFinite(scale) ? scale : 1));
    const stacked = count > 5 || (alwaysStack === true && count > 0);
    reveal = stacked && revealCards ? Math.max(0, Math.min(1, reveal)) : 0;
    const {size,resting,restingCount,extent,step,fanExtent} = formation(bodySize,count,scale,crossSize,vertical,
        count === 3 && !stacked ? folderOrientation(identity) : 0,stacked);
    const shown=stacked && reveal>0 ? count : resting.length;
    const turn=rotation*Math.PI/180;
    const cosine = Math.cos(turn), sine = Math.sin(turn);
    const items=Array.from({length:shown},(_,index) => {
        const item=resting[index] || resting[0];
        let x=item.x*cosine-item.y*sine;
        let y=item.x*sine+item.y*cosine;
        const offset=index-(count-1)/2;
        let angle=item.rotation+rotation;
        if (reveal) {
            x += ((vertical ? 0 : offset*step)-x)*reveal;
            y += ((vertical ? offset*step : 0)-y)*reveal;
            angle += ((count>1 ? offset*36/(count-1) : 0)-item.rotation)*reveal;
        }
        return {x:x+(bodySize-size)/2,y:y+(bodySize-size)/2,rotation:angle,glyphRotation:-rotation,
            opacity:index<restingCount ? 1 : reveal};
    });
    const length=extent+(fanExtent-extent)*reveal;
    return {bodySize,size,items,stacked,cardOpacity:stacked ? 1 : 0,width:vertical ? extent : length,height:vertical ? length : extent};
}
