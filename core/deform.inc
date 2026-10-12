// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

    float p = progress;
    if (abs(style - 10.0) < .5 || abs(style - 3.0) < .5) return vec2(pointX,pointY);
    if (style < .5 || abs(style - 2.0) < .5) return vec2(anchorX + (pointX-anchorX)*(.12+.88*p), anchorY + (pointY-anchorY)*(.12+.88*p));
    bool vertical = edge < 2.0;
    bool reversed = edge == 0.0 || edge == 3.0;
    float start = vertical ? rectY : rectX;
    float size = vertical ? rectHeight : rectWidth;
    float near = start + (reversed ? size : 0.0);
    float far = start + (reversed ? 0.0 : size);
    float axis = vertical ? pointY : pointX;
    float distance = (axis - near) / (far - near);
    float origin = vertical ? anchorY : anchorX;
    float center = vertical ? rectX + rectWidth/2.0 : rectY + rectHeight/2.0;
    float crossOrigin = vertical ? anchorX : anchorY;
    float across = (vertical ? pointX : pointY)-center;
    float along, cross;
    if (abs(style - 7.0) < .5) {
        float spread = smoothstep(0.0,.25,p), depth = 1.0+.35*(1.0-p)*clamp(distance,0.0,1.0);
        along = origin + (near-origin)*spread + (far-near)*distance*sin(p*3.14159265/2.0)/depth;
        cross = crossOrigin + (center-crossOrigin)*spread + across*spread/depth;
    } else if (abs(style - 8.0) < .5) {
        float angle = (1.0-p)*3.14159265/3.0;
        float centerAxis = start + size/2.0, displacement = (axis-centerAxis)*p;
        float depth = 1.0 + displacement*sin(angle)/1100.0;
        along = origin + (centerAxis-origin)*p + displacement*cos(angle)/depth;
        cross = center + across/depth;
    } else if (abs(style - 5.0) < .5) {
        float folded = 0.0;
        for (int panel = 0; panel < 3; panel++) {
            float portion = clamp(distance*3.0-float(panel), 0.0, 1.0);
            folded += portion * smoothstep(.05+.15*float(2-panel), .65+.175*float(2-panel), p)/3.0;
        }
        folded += min(0.0,distance)*smoothstep(.35,1.0,p) + max(0.0,distance-1.0)*smoothstep(.05,.65,p);
        along = origin + (near-origin)*smoothstep(.7,1.0,p) + (far-near)*folded;
        cross = crossOrigin + (center-crossOrigin)*smoothstep(.05,.7,p)
            + across*smoothstep(.1,.85,p)*(1.0+.08*(1.0-p)*sin(distance*3.0*3.14159265));
    } else {
        float head = smoothstep(0.0, .65, p), tail = smoothstep(.55, 1.0, p);
        float travel = mix(tail, head, distance);
        float d = clamp(distance, 0.0, 1.0);
        float spread = smoothstep(.05+(1.0-d)*.55, .45+(1.0-d)*.55, p);
        along = origin + (near-origin)*tail*(1.0-distance) + (far-origin)*head*distance;
        cross = crossOrigin + (center-crossOrigin)*travel + across*spread;
        if (abs(style - 4.0) < .5)
            cross += (vertical ? rectWidth : rectHeight)*.16*sin(d*3.14159265)*sin(p*3.14159265);
    }
    return vertical ? vec2(cross,along) : vec2(along,cross);
