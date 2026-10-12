// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {contract} from './contract.js';
import {preferences, hoverEffect, hoverRotation, animation, frame} from './preferences.js';
import {miniIconLayout} from './iconGeometry.js';
import {deform} from './animationGeometry.js';

/** Describe a settings preview using the same sizes and formations as the dock. */
export function settingsPreview({values = {}, apps = [], name = '', width = 520, height = 214,
    mode = 'dock', hover = 0, orbit = 0, labels = false}) {
    const prefs=preferences(item => values[item.name]), style=contract.appearance;
    const commands=[], background=[{type:'round',x:0,y:0,width,height,radius:16,color:'#25394b',alpha:1}];
    const text=(value,x,y,span,size) => commands.push({type:'text',value,x,y,width:span,size,color:'#ffffff',alpha:1});
    const icon=(app,x,y,size,rotation=0,stacked=false,alpha=1,glyphRotation=0) => {
        if (stacked) commands.push({type:'round',x,y,width:size,height:size,radius:5,color:style.dockColor,alpha,rotation});
        commands.push({type:'icon',app,x,y,size,rotation:rotation+glyphRotation,alpha});
    };
    const sample=apps.length ? apps : [{desktop:'preview',icon:'applications-internet',label:''}];
    const rect={x:24,y:10,width:Math.max(1,width-48),height:height-46}, anchor={x:width/2,y:height-12};
    if (mode === 'dock') {
        background.push({type:'round',x:16,y:12,width:width-32,height:height-24,radius:14,color:'#101c28',alpha:.7});
        const effect=hoverEffect(prefs.hoverEffect);
        for (const [index,count] of [4,7].entries()) {
            const size=52*prefs.groupIconSize/100;
            const layout=miniIconLayout(size,count,prefs.groupMiniIconSize/100,142,false,'preview-'+index,
                orbit + hoverRotation(prefs)*hover,index===1,effect.cards ? hover : 0,effect.cards);
            const center=width*(index ? .70 : .27), x=center-layout.bodySize/2, y=(height-layout.bodySize-24)/2;
            commands.push({type:'circle',x:center,y:y+layout.bodySize/2,radius:layout.bodySize*contract.layout.circleScale/2,
                color:style.dockColor,alpha:style.dockOpacity});
            layout.items.forEach((item,i) => icon(sample[i%sample.length],x+item.x,y+item.y,
                layout.size,item.rotation,layout.stacked,item.opacity,item.glyphRotation));
            if (labels) text(name,center-90,y+layout.bodySize/2+layout.height/2+8,180,prefs.fontSize);
        }
    } else {
        background.push({type:'round',x:width*.6,y:28,width:width*.32,height:height*.62,radius:14,color:'#9cb3c9',alpha:.18});
        background.push({type:'circle',x:width*.22,y:height*.65,radius:height*.32,color:'#97526c',alpha:.35});
        background.push({type:'circle',x:anchor.x,y:anchor.y,radius:10,color:style.dockColor,alpha:.45});
        commands.push(Object.assign({type:'round',radius:20,color:style.popupColor,alpha:style.backgroundOpacity},rect));
        text(name,rect.x+20,rect.y+12,rect.width-40,14);
        const shown=sample.slice(0,3), cell=(rect.width-32)/shown.length, size=Math.min(prefs.popupIconSize,cell-16);
        shown.forEach((app,index) => {
            const center=rect.x+16+cell*(index+.5);
            icon(app,center-size/2,rect.y+44,size);
            text(app.label || '',center-cell/2+4,rect.y+size+53,cell-8,11);
        });
    }
    return {background,commands,rect,anchor,preferences:prefs};
}

/** Return bounded affine triangles for a preview animation at a normalized time. */
export function settingsPreviewFrame({scene,time,opening}) {
    const state=frame(scene.preferences.animation,time,opening), rect=scene.rect;
    const vertices=Array.from({length:81},(_,i) => ({x:rect.x+rect.width*(i%9)/8,y:rect.y+rect.height*Math.floor(i/9)/8}));
    const targets=vertices.map(point => deform(point,rect,scene.anchor,state.progress,0,animation(scene.preferences.animation).id));
    const triangles=[];
    for (let y=0;y<8;y++) for (let x=0;x<8;x++) {
        const first=y*9+x;
        for (const ids of [[first,first+1,first+9],[first+1,first+10,first+9]]) {
            const [s,u,v]=ids.map(i => vertices[i]), [t,a,b]=ids.map(i => targets[i]);
            const det=(u.x-s.x)*(v.y-s.y)-(u.y-s.y)*(v.x-s.x);
            const xx=((a.x-t.x)*(v.y-s.y)-(b.x-t.x)*(u.y-s.y))/det;
            const xy=((b.x-t.x)*(u.x-s.x)-(a.x-t.x)*(v.x-s.x))/det;
            const yx=((a.y-t.y)*(v.y-s.y)-(b.y-t.y)*(u.y-s.y))/det;
            const yy=((b.y-t.y)*(u.x-s.x)-(a.y-t.y)*(v.x-s.x))/det;
            if (Math.abs(xx*yy-xy*yx)<.0001) continue;
            const angle=.5*Math.atan2(2*(xx*xy+yx*yy),xx*xx+yx*yx-xy*xy-yy*yy);
            const bx=xx*Math.cos(angle)+xy*Math.sin(angle), by=yx*Math.cos(angle)+yy*Math.sin(angle);
            const scale=Math.hypot(bx,by);
            const tx=t.x-xx*s.x-xy*s.y, ty=t.y-yx*s.x-yy*s.y;
            triangles.push({points:[t,a,b],matrix:[xx,yx,xy,yy,tx,ty],
                transform:[tx,ty,Math.atan2(by,bx),scale,(xx*yy-xy*yx)/scale,-angle]});
        }
    }
    return {triangles,opacity:state.opacity};
}
