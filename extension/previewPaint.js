// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Cairo from 'cairo';
import Gdk from 'gi://Gdk';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import Gtk from 'gi://Gtk';
import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';

function color(context,value,alpha=1) {
    const rgba=new Gdk.RGBA();rgba.parse(value);
    context.setSourceRGBA(rgba.red,rgba.green,rgba.blue,alpha);
}

function rounded(context,item) {
    const {x,y,width,height,radius:r}=item;
    context.newSubPath();
    for (const [cx,cy,start] of [[x+width-r,y+r,-Math.PI/2],[x+width-r,y+height-r,0],
        [x+r,y+height-r,Math.PI/2],[x+r,y+r,Math.PI]]) context.arc(cx,cy,r,start,start+Math.PI/2);
    context.closePath();
}

/** Cache native icons and paint the shared settings preview scene. */
export class PreviewPaint {
    constructor(widget) { this.widget=widget;this.icons=new Map(); }
    icon(app) {
        const desktop=app.desktop || app.icon;
        const scale=Math.max(1,this.widget.get_scale_factor());
        const key=JSON.stringify([desktop,scale]);
        if (!this.icons.has(key)) {
            let info=null;
            try { info=GioUnix.DesktopAppInfo.new(desktop); } catch (_) {}
            const gicon=info?.get_icon() || Gio.ThemedIcon.new(app.icon || 'application-x-executable');
            const paintable=Gtk.IconTheme.get_for_display(this.widget.get_display()).lookup_by_gicon(
                gicon,96,scale,Gtk.TextDirection.NONE,Gtk.IconLookupFlags.FORCE_REGULAR);
            const file=paintable?.get_file();
            try { this.icons.set(key,file ? GdkPixbuf.Pixbuf.new_from_stream_at_scale(file.read(null),96*scale,96*scale,true,null) : null); }
            catch (_) { this.icons.set(key,null); }
        }
        return this.icons.get(key);
    }
    commands(context,commands) {
        for (const item of commands) {
            context.save();
            const size=item.size || item.width;
            if (item.rotation) {
                const cx=item.x+size/2,cy=item.y+size/2;
                context.translate(cx,cy);context.rotate(item.rotation*Math.PI/180);context.translate(-cx,-cy);
            }
            if (item.type==='round' || item.type==='circle') {
                color(context,item.color,item.alpha);
                if (item.type==='round') rounded(context,item);else context.arc(item.x,item.y,item.radius,0,Math.PI*2);
                context.fill();
            } else if (item.type==='icon') {
                const icon=this.icon(item.app);
                if (icon) {
                    context.translate(item.x,item.y);context.scale(size/icon.width,size/icon.height);
                    Gdk.cairo_set_source_pixbuf(context,icon,0,0);context.paintWithAlpha(item.alpha);
                }
            } else if (item.type==='text') {
                const layout=PangoCairo.create_layout(context),font=Pango.FontDescription.from_string('Sans');
                font.set_absolute_size(size*Pango.SCALE);layout.set_font_description(font);
                layout.set_width(item.width*Pango.SCALE);layout.set_ellipsize(Pango.EllipsizeMode.END);
                layout.set_alignment(Pango.Alignment.CENTER);layout.set_text(item.value,-1);
                color(context,item.color);context.moveTo(item.x,item.y);PangoCairo.show_layout(context,layout);
            }
            context.restore();
        }
    }
    surface(scene,width,height) {
        const scale=Math.max(1,this.widget.get_scale_factor());
        const surface=new Cairo.ImageSurface(Cairo.Format.ARGB32,width*scale,height*scale);
        surface.setDeviceScale(scale,scale);
        const context=new Cairo.Context(surface);
        this.commands(context,scene.commands);context.$dispose();return surface;
    }
    mesh(context,surface,frame) {
        for (const triangle of frame.triangles) {
            context.save();
            const [first,...rest]=triangle.points;
            context.moveTo(first.x,first.y);for (const point of rest)context.lineTo(point.x,point.y);
            context.closePath();context.setAntialias(Cairo.Antialias.NONE);context.clip();
            const [tx,ty,angle,sx,sy,end]=triangle.transform;
            context.translate(tx,ty);context.rotate(angle);context.scale(sx,sy);context.rotate(end);
            context.setSourceSurface(surface,0,0);context.paintWithAlpha(frame.opacity);context.restore();
        }
    }
}
