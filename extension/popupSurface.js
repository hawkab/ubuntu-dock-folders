// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {roundedPath, RoundedBackdrop} from './effects.js';
import {contract} from './core/contract.js';
import {surface} from './core/preferences.js';
import {BackdropContrast} from './backdropContrast.js';

/** Paint the shared material surface with Shell actors and compositor effects. */
export function updatePopupSurface(host, menu, group) {
        const resolved = surface(group, host._preferences().blurStrength, host._settings.get_boolean('glass'),menu._contrast?.backdrop);
        const glass = resolved.glass;
        const color = resolved.popupColor;
        const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
        const wallpaper = group.wallpaper && Gio.File.new_for_path(group.wallpaper).query_exists(null);
        if (!menu._background) {
            const stack = new St.Widget({layout_manager: new Clutter.BinLayout()});
            menu._shadow = new Clutter.Actor({width: 0, height: 0, x_expand: true, y_expand: true});
            const shadow = new St.DrawingArea();
            menu._shadow.add_child(shadow);
            menu._shadow.connect('notify::allocation', () => {
                shadow.set_position(-32, -24);
                shadow.set_size(menu._shadow.width + 64, menu._shadow.height + 64);
                shadow.queue_repaint();
            });
            shadow.connect('repaint', () => {
                const cr = shadow.get_context();
                const width = menu._shadow.width;
                const height = menu._shadow.height;
                cr.setFillRule(Cairo.FillRule.EVEN_ODD);
                cr.rectangle(0, 0, width + 64, height + 64);
                roundedPath(cr, 32, 24, width, height, contract.layout.radius);
                cr.clip();
                cr.setFillRule(Cairo.FillRule.WINDING);
                for (let spread = 32; spread >= -24; spread--) {
                    const alpha = .35 * Math.exp(-spread * spread / 162) / 22.56;
                    cr.setSourceRGBA(0, 0, 0, alpha);
                    roundedPath(cr, 32 - spread, 32 - spread,
                        width + spread * 2, height + spread * 2, Math.max(.1, contract.layout.radius + spread));
                    cr.fill();
                }
                cr.$dispose();
            });
            menu._glass = new St.Widget({width: 0, height: 0, x_expand: true, y_expand: true,
                clip_to_allocation: true, visible: false});
            menu._background = new St.Widget({style_class: 'dock-group-background',
                x_expand: true, y_expand: true});
            menu._wallpaper = new St.Widget({x_expand:true,y_expand:true,clip_to_allocation:true});
            menu._sheen = new St.DrawingArea({x_expand:true,y_expand:true});
            menu._sheen.connect('repaint', () => {
                const cr=menu._sheen.get_context(), [width,height]=menu._sheen.get_surface_size();
                const radius=contract.layout.radius;
                roundedPath(cr,.5,.5,width-1,height-1,radius);
                const gradient=new Cairo.LinearGradient(0,0,0,height);
                gradient.addColorStopRGBA(0,1,1,1,.02 + .18 * (menu._blurAmount ?? 0));
                gradient.addColorStopRGBA(.6,1,1,1,0);
                cr.setSource(gradient); cr.fillPreserve();
                cr.setSourceRGBA(1,1,1,.08 + .22 * (menu._blurAmount ?? 0)); cr.setLineWidth(1); cr.stroke();
                cr.$dispose();
            });
            menu._boxPointer.bin.set_child(null);
            stack.add_child(menu._shadow);
            stack.add_child(menu._glass);
            stack.add_child(menu._background);
            stack.add_child(menu._wallpaper);
            stack.add_child(menu._sheen);
            stack.add_child(menu.box);
            menu._boxPointer.bin.set_child(stack);
            menu._glass.connect('notify::allocation', () => {
                if (!menu._glassClone)
                    host._syncGlass(menu);
                host._positionGlass(menu);
            });
            menu.actor.connect('notify::allocation', () => host._positionGlass(menu));
        }
        const background = menu._background;
        const tintOpacity = resolved.backgroundOpacity;
        background.set_style(`background-color: rgb(${rgb.join(',')}); border:none; border-radius:${contract.layout.radius}px;`);
        background.opacity = Math.round(tintOpacity * 255);
        menu._wallpaper.visible = Boolean(wallpaper);
        menu._wallpaper.set_style(wallpaper ? `background-image: url("${Gio.File.new_for_path(group.wallpaper).get_uri()}"); background-size:cover;` : '');
        menu._wallpaper.opacity = Math.round(tintOpacity * (1 - .2 * resolved.blurAmount) * 255);
        menu._wallpaper.remove_effect_by_name('folder-wallpaper-blur');
        menu._wallpaper.remove_effect_by_name('folder-wallpaper-round');
        if (wallpaper) {
            menu._wallpaper.add_effect_with_name('folder-wallpaper-round',new RoundedBackdrop());
            if (glass) menu._wallpaper.add_effect_with_name('folder-wallpaper-blur',new Shell.BlurEffect({brightness:.96,
                radius:contract.layout.blurRadius * .65 * resolved.blurAmount,mode:Shell.BlurMode.ACTOR}));
        }
        menu._sheen.opacity = Math.round(tintOpacity * 255);
        menu._sheen.queue_repaint();
        menu._shadow.opacity = Math.round(Math.min(1,tintOpacity*3) * 255);
        menu._blurAmount = resolved.blurAmount;
        menu._useGlass = glass;
        host._syncGlass(menu);
        const light = resolved.foreground === '#000000';
        menu.actor.remove_style_class_name(light ? 'dock-group-dark' : 'dock-group-light');
        menu.actor.add_style_class_name(light ? 'dock-group-light' : 'dock-group-dark');
        menu._contrast ??= new BackdropContrast(menu,host,group);
        menu._contrast.refresh(group);
        menu._contrast.schedule();
    }
