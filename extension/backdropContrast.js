// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import Meta from 'gi://Meta';
import * as Config from 'resource:///org/gnome/shell/misc/config.js';
import {surface} from './core/preferences.js';

/** Sample a small offscreen backdrop only when an open folder's background changes. */
export class BackdropContrast {
    constructor(menu, host, group) {
        this.menu=menu; this.host=host; this.group=group; this.timer=0;
        menu.actor.connect('destroy', () => this.destroy());
        menu.connect('open-state-changed', () => this.schedule());
        menu.actor.connectObject('notify::allocation', () => this.schedule(),menu.actor);
        global.window_group.connectObject('child-added', () => this.bind(),
            'child-removed', () => this.schedule(),menu.actor);
        global.display.connectObject('restacked', () => this.schedule(),menu.actor);
        this.bound=new WeakSet(); this.bind();
    }

    bind() {
        for (const actor of global.get_window_actors()) {
            if (this.bound.has(actor)) continue;
            this.bound.add(actor);
            actor.connectObject('notify::allocation', () => this.schedule(),
                'notify::visible', () => this.schedule(),
                'damaged', () => this.schedule(),this.menu.actor);
            actor.meta_window?.connectObject('notify::minimized', () => this.schedule(),this.menu.actor);
        }
        this.schedule();
    }

    schedule() {
        if (this.timer || this.sampling || !this.menu.isOpen || this.menu._timeline || this.group.wallpaper ||
            surface(this.group,this.host._preferences().blurStrength,this.host._settings.get_boolean('glass')).backgroundOpacity >= 1) return;
        this.timer=GLib.timeout_add(GLib.PRIORITY_DEFAULT,200, () => {
            this.timer=0;
            if (this.menu.isOpen && !this.menu._timeline) this.sample();
            return GLib.SOURCE_REMOVE;
        });
    }

    async sample() {
        const menu=this.menu, layer=menu._background;
        if (!layer || !layer.mapped) return;
        const [x,y]=layer.get_transformed_position(), [width,height]=layer.get_transformed_size();
        if (![x,y,width,height].every(Number.isFinite) || width < 1 || height < 1) return;
        const major=Number(Config.PACKAGE_VERSION.split('.')[0]);
        const Rectangle=major >= 50 ? imports.gi.Mtk.Rectangle : Meta.Rectangle;
        const left=Math.max(0,Math.floor(x)), top=Math.max(0,Math.floor(y));
        const w=Math.min(Math.ceil(width),global.stage.width-left), h=Math.min(Math.ceil(height),global.stage.height-top);
        if (w < 1 || h < 1) return;
        const scale=8/Math.max(w,h);
        const opacity=menu.actor.opacity;
        let content;
        this.sampling=true;
        try {
            menu.actor.opacity=0;
            const args=[new Rectangle({x:left,y:top,width:w,height:h}),scale];
            if (major >= 48) args.push(null);
            args.push(Clutter.PaintFlag.NO_CURSORS);
            content=global.stage.paint_to_content(...args);
        } catch (error) {
            this.lastError=error.message;
            this.sampling=false;
            return;
        } finally {
            menu.actor.opacity=opacity;
        }
        try {
            const texture=content.get_texture();
            const stream=Gio.MemoryOutputStream.new_resizable();
            const pixbuf=await Shell.Screenshot.composite_to_stream(texture,0,0,
                texture.get_width(),texture.get_height(),1,null,0,0,1,stream);
            stream.close(null);
            const pixels=pixbuf.get_pixels();
            if (this.destroyed || !this.menu.isOpen) return;
            const rgb=[0,0,0]; let count=0;
            for (let row=0;row<pixbuf.get_height();row++) for (let col=0;col<pixbuf.get_width();col++) {
                const i=row*pixbuf.get_rowstride()+col*pixbuf.get_n_channels();
                for (let channel=0;channel<3;channel++) rgb[channel]+=pixels[i+channel];
                count++;
            }
            if (!count) return;
            this.backdrop='#'+rgb.map(value => Math.round(value/count).toString(16).padStart(2,'0')).join('');
            this.samples=(this.samples || 0)+1;
            this.lastError=null;
            this.refresh();
        } catch (error) {
            this.lastError=error.message;
            this.backdrop=null;
        } finally {
            this.sampling=false;
        }
    }

    refresh(group = this.group) {
        this.group=group;
        const value=surface(group,this.host._preferences().blurStrength,this.host._settings.get_boolean('glass'),this.backdrop);
        const light=value.foreground === '#000000';
        this.menu.actor.remove_style_class_name(light ? 'dock-group-dark' : 'dock-group-light');
        this.menu.actor.add_style_class_name(light ? 'dock-group-light' : 'dock-group-dark');
    }

    destroy() { this.destroyed=true; if (this.timer) GLib.source_remove(this.timer); this.timer=0; }
}
