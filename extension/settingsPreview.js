// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {contract} from './core/contract.js';
import {settingsPreview,settingsPreviewFrame} from './core/settingsPreview.js';
import {duration,hoverDuration} from './core/preferences.js';
import {PreviewPaint} from './previewPaint.js';
import {orbitFrame, orbitHoverFrame} from './core/orbit.js';
import {onWindowClose} from './windowLifecycle.js';

/** Attach GTK previews with bounded animation and no idle polling. */
export function attachPreviews(builder,settings,window,translate) {
    const sampleApps=() => {
        const groups=JSON.parse(settings.get_string('groups'));
        return Object.values(groups).find(group => group.apps?.length)?.apps ||
            Gio.AppInfo.get_all().filter(info => info.get_id() && info.should_show() && !info.get_id().startsWith('local.groups.'))
                .slice(0,3).map(info => ({desktop:info.get_id(),label:info.get_name()}));
    };
    let apps=sampleApps();
    const previews=[];
    for (const mode of ['dock','popup']) {
        const area=new Gtk.DrawingArea({hexpand:true,content_height:214});
        area.set_tooltip_text(translate(mode==='dock' ? 'Dock icon preview' : 'Open folder preview'));
        const painter=new PreviewPaint(area);
        const state={area,painter,mode,scene:null,card:null,frame:null,tick:0,phase:null,hover:0,target:0,orbit:0,velocity:0,hovered:false,last:0};
        const values=() => Object.fromEntries(contract.preferences.map(item => [item.name,settings.get_value(item.key).deep_unpack()]));
        area.set_draw_func((_area,context,width,height) => {
            if (width<1 || height<1)return;
            if (!state.scene || state.width!==width || state.height!==height) {
                state.scene=settingsPreview({values:values(),apps,name:translate('Dock folders'),width,height,mode,hover:state.hover,orbit:state.orbit,labels:true});
                state.width=width;state.height=height;state.card=null;
            }
            painter.commands(context,state.scene.background);
            if (state.frame) {
                state.card ||= painter.surface(state.scene,width,height);
                painter.mesh(context,state.card,state.frame);
            } else painter.commands(context,state.scene.commands);
        });
        const animate=() => {
            if (state.tick)return;
            state.last=GLib.get_monotonic_time();
            state.tick=area.add_tick_callback(() => {
                const now=GLib.get_monotonic_time();
                const motion=orbitFrame({angle:state.orbit,velocity:state.velocity,elapsed:(now-state.last)/1000,values:values(),hovered:state.hovered,
                    allowed:mode==='dock' && area.get_mapped() && Gtk.Settings.get_default().gtk_enable_animations});
                state.last=now;
                state.velocity=motion.velocity;
                if(state.orbit!==motion.angle)state.scene=null;
                state.orbit=motion.angle;
                if (state.hover!==state.target) {
                    const milliseconds=hoverDuration(settings.get_int('hover-speed'));
                    const p=milliseconds ? Math.min(1,(now-state.hoverStart)/(milliseconds*1000)) : 1;
                    const progress=state.origin+(state.target-state.origin)*(1-Math.pow(1-p,3));
                    state.orbit=orbitHoverFrame({angle:state.orbit,velocity:state.velocity,
                        previous:state.hover,progress,values:values()}).angle;
                    state.hover=progress;state.scene=null;
                }
                if (state.phase && state.scene) {
                    const p=Math.min(1,(now-state.started)/Math.max(1,duration(settings.get_string('animation'),settings.get_int('animation-speed'))*1000));
                    state.frame=settingsPreviewFrame({scene:state.scene,time:p,opening:state.phase==='opening'});
                    if (p===1) {
                        if (state.phase==='closing'){state.phase='opening';state.started=now;}
                        else {state.phase=null;state.frame=null;}
                    }
                }
                area.queue_draw();
                if (state.phase || state.hover!==state.target || motion.active)return GLib.SOURCE_CONTINUE;
                state.tick=0;return GLib.SOURCE_REMOVE;
            });
        };
        const motion=new Gtk.EventControllerMotion();
        const hover=value => {
            state.hovered=Boolean(value);
            if(mode==='dock' && settings.get_boolean('enabled') && settings.get_string('hover-effect')!=='none'){
                state.target=value;state.origin=state.hover;state.hoverStart=GLib.get_monotonic_time();
            }
            if(state.hover!==state.target || orbitFrame({velocity:state.velocity,values:values(),hovered:state.hovered,allowed:mode==='dock'}).active)animate();
        };
        state.sync=()=>{if(mode==='dock' && area.get_mapped() && orbitFrame({velocity:state.velocity,values:values(),hovered:state.hovered}).active)animate();};
        area.connect('map',state.sync);
        area.connect('unmap',()=>{if(state.tick){area.remove_tick_callback(state.tick);state.tick=0;}state.velocity=0;});
        motion.connect('enter',() => hover(1));motion.connect('leave',() => hover(0));area.add_controller(motion);
        state.replay=() => {
            if (!settings.get_boolean('enabled') || settings.get_string('animation')==='none')return;
            state.phase='closing';state.started=GLib.get_monotonic_time();animate();
        };
        builder.get_object(mode+'_preview_box').append(area);previews.push(state);
    }
    const content=new Gtk.Box({spacing:6});
    content.append(new Gtk.Image({icon_name:'media-playback-start-symbolic'}));
    content.append(new Gtk.Label({label:translate('Preview animation')}));
    const button=new Gtk.Button({child:content,halign:Gtk.Align.CENTER});
    button.connect('clicked',() => previews[1].replay());builder.get_object('popup_preview_box').append(button);
    const refresh=(_settings,key) => {
        if(key==='groups')apps=sampleApps();
        button.sensitive=settings.get_boolean('enabled') && settings.get_string('animation')!=='none';
        for (const preview of previews){preview.phase=null;preview.scene=null;preview.card=null;preview.frame=null;preview.area.queue_draw();preview.sync();}
    };
    const signal=settings.connect('changed',refresh);
    refresh(settings);
    onWindowClose(window,() => {
        settings.disconnect(signal);for (const preview of previews)if(preview.tick){preview.area.remove_tick_callback(preview.tick);preview.tick=0;}
    });
    window._settingsPreviews=previews;
}
