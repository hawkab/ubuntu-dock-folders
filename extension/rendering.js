// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {roundedPath, RoundedBackdrop} from './effects.js';

// Render folder icons, popup backgrounds, and running indicators.
export class FolderRenderer extends Extension {
    _appIcon(entry, size) {
        const app = this._appSystem.lookup_app(entry.desktop);
        if (app)
            return app.create_icon_texture(size);
        const gicon = GioUnix.DesktopAppInfo.new(entry.desktop)?.get_icon();
        return new St.Icon({
            ...(gicon ? {gicon} : {icon_name: 'application-x-executable'}),
            icon_size: size, x_align: Clutter.ActorAlign.CENTER,
        });
    }

    _color(value, fallback) {
        return /^#[0-9a-f]{6}$/i.test(value ?? '') ? value : fallback;
    }

    _folderIcon(group, size) {
        const custom = this._settings.get_boolean('customization');
        const color = this._color(custom ? group.dockColor : null, group.colors[1]);
        const opacity = custom ? Math.max(0, Math.min(1, group.dockOpacity ??
            ('transparentDock' in group ? (group.transparentDock ? 0 : 1) : .2))) : .2;
        const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
        const actor = new St.Widget({width: size, height: size,
            clip_to_allocation: false,
            style: `background-color: rgba(${rgb.join(',')},${opacity}); border-radius: ${size / 2}px; border: 1px solid rgba(255,255,255,${opacity * .25});`});
        const apps = group.apps.slice(0, 4);
        const positions = apps.length === 1 ? [[.5, .5]] :
            apps.length === 2 ? [[.22, .5], [.78, .5]] :
                apps.length === 3 ? [[.25, .27], [.75, .27], [.5, .79]] :
                    [[.24, .24], [.76, .24], [.24, .76], [.76, .76]];
        const diameter = Math.floor(size * (apps.length === 2 ? .52 : .48));
        apps.forEach((entry, i) => {
            const [x, y] = positions[i];
            const bubble = new St.Bin({x: Math.round(size * x - diameter / 2),
                y: Math.round(size * y - diameter / 2), width: diameter, height: diameter,
                style: 'background-color: transparent;'});
            bubble.set_child(this._appIcon(entry, diameter));
            actor.add_child(bubble);
        });
        return actor;
    }

    _stylePopup(menu, group) {
        const custom = this._settings.get_boolean('customization');
        const glass = this._settings.get_boolean('glass');
        const color = this._color(custom ? group.popupColor : null, '#26262a');
        const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
        const wallpaper = custom && group.wallpaper && Gio.File.new_for_path(group.wallpaper).query_exists(null);
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
                roundedPath(cr, 32, 24, width, height, 24);
                cr.clip();
                cr.setFillRule(Cairo.FillRule.WINDING);
                for (let spread = 32; spread >= -24; spread--) {
                    const alpha = .35 * Math.exp(-spread * spread / 162) / 22.56;
                    cr.setSourceRGBA(0, 0, 0, alpha);
                    roundedPath(cr, 32 - spread, 32 - spread,
                        width + spread * 2, height + spread * 2, Math.max(.1, 24 + spread));
                    cr.fill();
                }
                cr.$dispose();
            });
            menu._glass = new St.Widget({width: 0, height: 0, x_expand: true, y_expand: true,
                clip_to_allocation: true, visible: false});
            menu._background = new St.Widget({style_class: 'dock-group-background',
                x_expand: true, y_expand: true});
            menu._shade = new St.Widget({x_expand: true, y_expand: true,
                style: 'background-color: rgba(0,0,0,0.42); border-radius: 24px;'});
            menu._boxPointer.bin.set_child(null);
            stack.add_child(menu._shadow);
            stack.add_child(menu._glass);
            stack.add_child(menu._background);
            stack.add_child(menu._shade);
            stack.add_child(menu.box);
            menu._boxPointer.bin.set_child(stack);
            menu._glass.connect('notify::allocation', () => {
                if (!menu._glassClone)
                    this._syncGlass(menu);
                this._positionGlass(menu);
            });
            menu.actor.connect('notify::allocation', () => this._positionGlass(menu));
        }
        const background = menu._background;
        const opacity = Math.max(0, Math.min(1, custom && group.popupOpacity !== undefined ?
            group.popupOpacity : .98));
        const tintOpacity = glass ? Math.max(0, Math.min(1,
            custom ? group.glassOpacity ?? .38 : .38)) : opacity;
        let style = `background-color: rgb(${rgb.join(',')});`;
        if (wallpaper)
            style += `background-image: url("${Gio.File.new_for_path(group.wallpaper).get_uri()}"); background-size: cover;`;
        background.set_style(style);
        background.opacity = Math.round(tintOpacity * 255);
        menu._shadow.opacity = Math.round((glass ? .85 : opacity) * 255);
        menu._shade.visible = Boolean(wallpaper);
        menu._shade.opacity = Math.round(tintOpacity * 255);
        menu._useGlass = glass;
        this._syncGlass(menu);
        const light = !wallpaper && rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 > 160;
        menu.actor.remove_style_class_name(light ? 'dock-group-dark' : 'dock-group-light');
        menu.actor.add_style_class_name(light ? 'dock-group-light' : 'dock-group-dark');
    }

    _syncGlass(menu) {
        const active = menu._useGlass && (menu.isOpen || Boolean(menu._timeline));
        menu._glass.visible = active;
        if (!active) {
            if (menu._glassLater)
                global.compositor.get_laters().remove(menu._glassLater);
            menu._glassLater = 0;
            menu._glass.remove_effect_by_name('dock-group-glass');
            menu._glass.remove_effect_by_name('dock-group-round');
            menu._glassClone?.destroy();
            menu._glassClone = null;
            return;
        }
        const [width, height] = menu._glass.get_allocation_box().get_size();
        if (![width, height].every(value => Number.isFinite(value) && value > 0)) {
            return;
        }
        if (!menu._glassClone) {
            menu._glassClone = new Clutter.Actor({width: global.stage.width, height: global.stage.height});
            for (const source of global.window_group.get_children()) {
                const clone = new Clutter.Clone({source});
                const update = () => {
                    const valid = [source.x, source.y, source.width, source.height].every(Number.isFinite);
                    if (valid)
                        clone.set_position(source.x, source.y);
                    clone.visible = valid && source.visible && source.width > 0 && source.height > 0;
                };
                menu._glassClone.add_child(clone);
                source.connectObject('notify::allocation', update,
                    'notify::visible', update, menu._glassClone);
                update();
            }
            menu._glass.add_child(menu._glassClone);
            menu._roundEffect ??= new RoundedBackdrop();
            menu._blurEffect ??= new Shell.BlurEffect({brightness: .96, radius: 32,
                mode: Shell.BlurMode.ACTOR});
            menu._glass.add_effect_with_name('dock-group-round', menu._roundEffect);
            menu._glass.add_effect_with_name('dock-group-glass', menu._blurEffect);
            menu._glassLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
                menu._glassLater = 0;
                this._positionGlass(menu);
                return GLib.SOURCE_REMOVE;
            });
        }
        this._positionGlass(menu);
    }

    _positionGlass(menu) {
        if (!menu._glassClone)
            return;
        let x = 0;
        let y = 0;
        for (let actor = menu._glass; actor; actor = actor.get_parent()) {
            const box = actor.get_allocation_box();
            x += box.x1;
            y += box.y1;
            if (actor === menu.actor)
                break;
        }
        if ([x, y].every(Number.isFinite))
            menu._glassClone.set_position(-x, -y);
    }

    _refreshFolder(record) {
        const {icon, group, menu, row, tiles, title} = record;
        icon.icon.update();
        icon.label?.set_text(group.name);
        icon.accessible_name = group.name;
        title.set_text(group.name);
        record.dockLabel?.destroy();
        record.dockLabel = null;
        if (this._settings.get_boolean('customization') && group.showLabel) {
            record.dockLabel = new St.Label({text: group.name, style_class: 'dock-group-dock-label',
                style: `font-size: ${this._settings.get_double('font-size')}px;`,
                x_align: Clutter.ActorAlign.CENTER});
            record.dockLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            icon.icon._box.add_child(record.dockLabel);
        }
        for (const [index, entry] of group.apps.entries()) {
            const button = tiles.get(entry.desktop);
            const placement = row.layout_manager.get_child_meta(row, button);
            placement.left_attach = index % 4;
            placement.top_attach = Math.floor(index / 4);
        }
        this._stylePopup(menu, group);
    }

}
