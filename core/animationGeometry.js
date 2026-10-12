// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

const {abs, sin, cos, min, max} = Math;
const point = (x, y) => ({x, y});
const clamp = (value, low, high) => min(high, max(low, value));
const mix = (a, b, t) => a + (b-a)*t;
export function smooth(low, high, value) { const t=clamp((value-low)/(high-low),0,1); return t*t*(3-2*t); }
const smoothstep=smooth;

/** Deform a point using the shared CPU/GPU animation kernel. */
export function deform(position, rect, anchor, progress, edge, style) {
    const pointX=position.x, pointY=position.y, anchorX=anchor.x, anchorY=anchor.y;
    const rectX=rect.x, rectY=rect.y, rectWidth=rect.width, rectHeight=rect.height;

    let p = progress;
    if (abs(style - 10.0) < .5 || abs(style - 3.0) < .5) return point(pointX,pointY);
    if (style < .5 || abs(style - 2.0) < .5) return point(anchorX + (pointX-anchorX)*(.12+.88*p), anchorY + (pointY-anchorY)*(.12+.88*p));
    let vertical = edge < 2.0;
    let reversed = edge == 0.0 || edge == 3.0;
    let start = vertical ? rectY : rectX;
    let size = vertical ? rectHeight : rectWidth;
    let near = start + (reversed ? size : 0.0);
    let far = start + (reversed ? 0.0 : size);
    let axis = vertical ? pointY : pointX;
    let distance = (axis - near) / (far - near);
    let origin = vertical ? anchorY : anchorX;
    let center = vertical ? rectX + rectWidth/2.0 : rectY + rectHeight/2.0;
    let crossOrigin = vertical ? anchorX : anchorY;
    let across = (vertical ? pointX : pointY)-center;
    let along, cross;
    if (abs(style - 7.0) < .5) {
        let spread = smoothstep(0.0,.25,p), depth = 1.0+.35*(1.0-p)*clamp(distance,0.0,1.0);
        along = origin + (near-origin)*spread + (far-near)*distance*sin(p*3.14159265/2.0)/depth;
        cross = crossOrigin + (center-crossOrigin)*spread + across*spread/depth;
    } else if (abs(style - 8.0) < .5) {
        let angle = (1.0-p)*3.14159265/3.0;
        let centerAxis = start + size/2.0, displacement = (axis-centerAxis)*p;
        let depth = 1.0 + displacement*sin(angle)/1100.0;
        along = origin + (centerAxis-origin)*p + displacement*cos(angle)/depth;
        cross = center + across/depth;
    } else if (abs(style - 5.0) < .5) {
        let folded = 0.0;
        for (let panel = 0; panel < 3; panel++) {
            let portion = clamp(distance*3.0-Number(panel), 0.0, 1.0);
            folded += portion * smoothstep(.05+.15*Number(2-panel), .65+.175*Number(2-panel), p)/3.0;
        }
        folded += min(0.0,distance)*smoothstep(.35,1.0,p) + max(0.0,distance-1.0)*smoothstep(.05,.65,p);
        along = origin + (near-origin)*smoothstep(.7,1.0,p) + (far-near)*folded;
        cross = crossOrigin + (center-crossOrigin)*smoothstep(.05,.7,p)
            + across*smoothstep(.1,.85,p)*(1.0+.08*(1.0-p)*sin(distance*3.0*3.14159265));
    } else {
        let head = smoothstep(0.0, .65, p), tail = smoothstep(.55, 1.0, p);
        let travel = mix(tail, head, distance);
        let d = clamp(distance, 0.0, 1.0);
        let spread = smoothstep(.05+(1.0-d)*.55, .45+(1.0-d)*.55, p);
        along = origin + (near-origin)*tail*(1.0-distance) + (far-origin)*head*distance;
        cross = crossOrigin + (center-crossOrigin)*travel + across*spread;
        if (abs(style - 4.0) < .5)
            cross += (vertical ? rectWidth : rectHeight)*.16*sin(d*3.14159265)*sin(p*3.14159265);
    }
    return vertical ? point(cross,along) : point(along,cross);
}

/** Return the rounded card's deformed outline for compositor blur. */
export function outline(rect, anchor, progress, edge, style, radius) {
    const points = [];
    const corners = [[rect.x + rect.width - radius, rect.y + radius, -Math.PI / 2],
                     [rect.x + rect.width - radius, rect.y + rect.height - radius, 0],
                     [rect.x + radius, rect.y + rect.height - radius, Math.PI / 2],
                     [rect.x + radius, rect.y + radius, Math.PI]];
    for (const corner of corners) {
        for (let step = 0; step <= 8; step++) {
            const angle = corner[2] + step * Math.PI / 16;
            points.push({x: corner[0] + radius * Math.cos(angle), y: corner[1] + radius * Math.sin(angle)});
        }
    }
    const outline = [];
    for (let index = 0; index < points.length; index++) {
        const start = points[index], end = points[(index + 1) % points.length];
        outline.push(start);
        if (Math.hypot(start.x - end.x, start.y - end.y) > radius * 2) {
            for (let step = 1; step < 12; step++) outline.push({x: start.x + (end.x - start.x) * step / 12,
                y: start.y + (end.y - start.y) * step / 12});
        }
    }
    return outline.map(point => {
        const mapped = deform(point, rect, anchor, progress, edge, style);
        return mapped;
    });
}
