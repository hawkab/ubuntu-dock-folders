// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {RoundedBackdrop} from './effects.js';
import {updatePopupSurface} from './popupSurface.js';
import {miniIconLayout} from './iconGeometry.js';
import {bindFolderHover} from './folderHover.js';
import {contract} from './core/contract.js';
import {appearance} from './core/preferences.js';

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

    _folderIcon(group, size, vertical = false, source = null) {
        const baseSize = size;
        const resolved = appearance(group);
        size *= this._preferences().groupIconSize / 100;
        const crossSize = size + 12;
        const color = resolved.dockColor;
        const opacity = resolved.dockOpacity;
        const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
        const layout = miniIconLayout(size, group.apps.length, this._preferences().groupMiniIconSize / 100, crossSize, vertical, group.id, group.iconRotation || 0, group.alwaysStack || false, 0, ['cards','rotate-cards'].includes(this._settings.get_string('hover-effect')));
        size = layout.bodySize;
        const actor = new St.Widget({width: layout.width, height: layout.height, clip_to_allocation: false});
        actor._miniLayout = layout;
        const offset = {x: (layout.width - size) / 2, y: (layout.height - size) / 2};
        const circle = size * contract.layout.circleScale;
        actor.add_child(new St.Widget({x: offset.x+(size-circle)/2, y: offset.y+(size-circle)/2, width: circle, height: circle,
            style: `background-color: rgba(${rgb.join(',')},${opacity}); border-radius: ${circle / 2}px; border: 1px solid rgba(255,255,255,${opacity * .25});`}));
        const bubbles = [];
        const createBubble = i => {
            const entry = group.apps[i], current = actor._miniLayout, item = current.items[i];
            const bubble = new St.Bin({x: offset.x + (item?.x || 0),
                y: offset.y + (item?.y || 0), width: current.size, height: current.size,
                style: current.stacked ? `background-color: ${appearance(group).dockColor}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.25);` : 'background-color: transparent;'});
            bubble.set_pivot_point(.5, .5);
            bubble.rotation_angle_z = item?.rotation || 0;
            const glyph = this._appIcon(entry, current.size);
            glyph.set_pivot_point(.5, .5);
            glyph.rotation_angle_z = item?.glyphRotation || 0;
            bubble.set_child(glyph);
            actor.add_child(bubble);
            bubbles.push(bubble);
        };
        layout.items.forEach((_item, index) => createBubble(index));
        if (source) {
            source._folderActor = actor;
            bindFolderHover(source, actor, bubbles, this._settings, group, size, vertical, crossSize, createBubble,baseSize);
            actor.connect('destroy',() => { if (source._folderActor === actor) source._folderActor = null; });
        }
        return actor;
    }

    _stylePopup(menu, group) { updatePopupSurface(this,menu,group); }

    _syncGlass(menu) {
        const active = menu._useGlass && (menu.isOpen || Boolean(menu._timeline));
        menu._glass.visible = active;
        menu._glass.opacity = 255;
        if (!active) {
            if (menu._glassLater)
                global.compositor.get_laters().remove(menu._glassLater);
            menu._glassLater = 0;
            menu._glass.remove_effect_by_name('dock-group-glass');
            menu._glass.remove_effect_by_name('dock-group-round');
            menu._glassClone?.destroy();
            menu._glassClone = null;
            menu._glassChildren = null;
            return;
        }
        const [width, height] = menu._glass.allocation.get_size();
        if (![width, height].every(value => Number.isFinite(value) && value > 0)) {
            return;
        }
        const created = !menu._glassClone;
        if (created) {
            if (menu._glassLater)
                global.compositor.get_laters().remove(menu._glassLater);
            menu._glassLater = 0;
            menu._glassClone = new Clutter.Actor({width: global.stage.width, height: global.stage.height});
            menu._glassChildren = new Map();
            global.window_group.connectObject?.('child-added', () => this._syncGlass(menu),
                'child-removed', () => this._syncGlass(menu),menu._glassClone);
        }
        const sources = new Set(global.window_group.get_children());
        for (const [source,clone] of menu._glassChildren) {
            if (!sources.has(source)) { clone.destroy(); menu._glassChildren.delete(source); }
        }
        for (const source of sources) {
            if (menu._glassChildren.has(source)) continue;
            const clone = new Clutter.Clone({source});
            menu._glassChildren.set(source,clone);
            const update = () => {
                const valid = [source.x, source.y, source.width, source.height].every(Number.isFinite);
                if (valid)
                    clone.set_position(source.x, source.y);
                clone.visible = valid && source.visible && source.width > 0 && source.height > 0;
            };
            menu._glassClone.add_child(clone);
            source.connectObject('notify::allocation', update,
                'notify::visible', update, clone);
            update();
        }
        if (created) {
            menu._glass.add_child(menu._glassClone);
            menu._roundEffect ??= new RoundedBackdrop();
            menu._blurEffect ??= new Shell.BlurEffect({brightness: .96, radius: contract.layout.blurRadius,
                mode: Shell.BlurMode.ACTOR});
            menu._glass.add_effect_with_name('dock-group-round', menu._roundEffect);
            menu._glass.add_effect_with_name('dock-group-glass', menu._blurEffect);
            menu._glassLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
                menu._glassLater = 0;
                this._positionGlass(menu);
                return GLib.SOURCE_REMOVE;
            });
        }
        menu._blurEffect.radius = contract.layout.blurRadius * (menu._blurAmount ?? 1);
        this._positionGlass(menu);
    }

    _positionGlass(menu) {
        menu._contrast?.schedule();
        if (!menu._glassClone)
            return;
        let x = 0;
        let y = 0;
        for (let actor = menu._glass; actor; actor = actor.get_parent()) {
            const box = actor.allocation;
            if (![box.x1, box.y1].every(Number.isFinite))
                return;
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
        if (icon._folderActor?.get_stage()) icon._folderActor.refreshFormation();
        else icon.icon.update();
        icon.label?.set_text(group.name);
        icon.accessible_name = group.name;
        title.set_text(group.name);
        if (this._settings.get_boolean('customization') && group.showLabel) {
            if (!record.dockLabel) {
                record.dockLabel = new St.Label({style_class:'dock-group-dock-label',x_align:Clutter.ActorAlign.CENTER});
                record.dockLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                icon.icon._box.add_child(record.dockLabel);
            }
            record.dockLabel.set_text(group.name);
            record.dockLabel.set_style(`font-size: ${this._settings.get_double('font-size')}px;`);
        } else if (record.dockLabel) {
            record.dockLabel.destroy();
            record.dockLabel = null;
        }
        const size = this._preferences().popupIconSize;
        const columns = Math.min(contract.layout.maxColumns,Math.max(1,group.apps.length));
        for (const [index, entry] of group.apps.entries()) {
            const button = tiles.get(entry.desktop);
            button.accessible_name = entry.label.replaceAll('\n',' ');
            button.get_child().get_children()[1].set_text(entry.label);
            if (button._glyphSize !== size) {
                const tile = button.get_child(), old = tile.get_first_child();
                tile.insert_child_at_index(this._appIcon(entry,size),0);
                old.destroy(); button._glyphSize = size;
            }
            const placement = row.layout_manager.get_child_meta(row, button);
            placement.left_attach = index % columns;
            placement.top_attach = Math.floor(index / columns);
        }
        this._stylePopup(menu, group);
    }

}
