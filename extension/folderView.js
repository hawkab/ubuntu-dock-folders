// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import {FolderMenuManager, WindowPreviews} from './windowPreviews.js';
import {createBoxLayout} from './compat.js';
import {contract} from './core/contract.js';
import {folderInteraction} from './core/folderInteraction.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';

/** Build and dispose folder menus and dock indicators. */
export class FolderView {
    constructor(host) { this.host = host; }

    _decorate(icon, group, dash) {
        const host = this.host;
        host._dock.details.decorateDockIcon(icon);
        icon.getWindows = () => host._windowsAdapter._windows(group);
        icon._updateRunningState = () => { icon.running = icon.windowsCount > 0; };
        icon._updateFocusState = () => {
            if (!host._enabled || !dash._scrollView?.get_stage())
                return;
            const window = global.display.focus_window;
            icon.focused = icon.mapped && icon.running &&
                Boolean(window && host._windowsAdapter._entryForWindow(window)?.group === group);
        };

        if (Shell.SquareBin && icon.icon instanceof Shell.SquareBin) {
            const content = icon.icon.get_child();
            icon.icon.set_child(null);
            icon._folderMeasure = new St.Widget({width:icon.icon.iconSize,height:icon.icon.iconSize});
            icon.icon.set_child(icon._folderMeasure);
            icon.icon.hide();
            icon._iconContainer.add_child(new St.Bin({style_class:icon.icon.style_class,child:content}));
        }
        icon.icon.createIcon = size => {
            icon._folderMeasure?.set_size(size,size);
            return host._folderIcon(group, size, dash._position === St.Side.LEFT || dash._position === St.Side.RIGHT, icon);
        };
        icon.icon.update();
        icon.label?.set_text(group.name);
        icon.accessible_name = group.name;
        let dockLabel = null;
        if (host._settings.get_boolean('customization') && group.showLabel) {
            const label = new St.Label({text: group.name, style_class: 'dock-group-dock-label',
                style: `font-size: ${host._settings.get_double('font-size')}px;`,
                x_align: Clutter.ActorAlign.CENTER});
            label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            icon.icon._box.add_child(label);
            dockLabel = label;
        }
        const side = dash._position;
        const menu = new PopupMenu.PopupMenu(icon, 0.5, side);
        menu.actor.add_style_class_name('dock-group-popup');
        Main.uiGroup.add_child(menu.actor);
        menu.actor.hide();
        icon.connect('destroy', () => {
            if ((menu.isOpen || menu._pendingOpen) && host._enabled && host._settings.get_boolean('enabled') && host._groups[group.key]) {
                host._pendingFolder = group.key;
                host._queueUpdate();
            }
            host._icons.delete(icon);
            host._animation._stopAnimation(menu);
            menu.destroy();
        });
        const previews = new WindowPreviews(menu, {
            getWindows: entry => host._windowsAdapter._windows(group, entry),
            isDragging: () => host._dragging,
            onUndo: () => host._commands._undoLastMove(),
        });
        const manager = new FolderMenuManager(menu, previews, point => this._press(point));

        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const content = createBoxLayout(Clutter.Orientation.VERTICAL, {
            style_class: 'dock-group-content'});
        const header = new St.BoxLayout({style_class: 'dock-group-header'});
        const title = new St.Label({text: group.name, style_class: 'dock-group-title', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER});
        header.add_child(title);
        const undo = new St.Button({style_class: 'dock-group-gear', reactive: true, can_focus: true,
            accessible_name: _('Undo last move'), visible: Boolean(host._undo),
            child: new St.Icon({icon_name: 'edit-undo-symbolic', icon_size: 20})});
        undo.connect('clicked', () => host._commands._undoLastMove());
        header.add_child(undo);
        if (host._settings.get_boolean('customization')) {
            const gear = new St.Button({style_class: 'dock-group-gear', reactive: true, can_focus: true,
                accessible_name: _('Folder settings'), child: new St.Icon({icon_name: 'emblem-system-symbolic', icon_size: 20})});
            gear.connect('clicked', () => {
                menu.close(BoxPointer.PopupAnimation.FULL);
                Gio.Subprocess.new(['/usr/bin/python3', `${host.path}/app/preferences.py`, group.key],
                    Gio.SubprocessFlags.NONE);
            });
            header.add_child(gear);
        }
        content.add_child(header);
        const row = new St.Widget({style_class: 'dock-group-apps',
            layout_manager: new Clutter.GridLayout({orientation: Clutter.Orientation.HORIZONTAL})});
        row.layout_manager.set_column_spacing(6);
        row.layout_manager.set_row_spacing(6);
        const columns = Math.min(contract.layout.maxColumns,Math.max(1,group.apps.length));
        let index = 0;
        const dots = [];
        const tiles = new Map();
        for (const entry of group.apps) {
            const button = new St.Button({
                style_class: 'dock-group-tile', can_focus: true, reactive: true,
                accessible_name: entry.label.replaceAll('\n', ' '),
            });
            const tile = createBoxLayout(Clutter.Orientation.VERTICAL, {
                style_class: 'dock-group-tile-content'});
            button._glyphSize = host._preferences().popupIconSize;
            tile.add_child(host._appIcon(entry, host._preferences().popupIconSize));
            tile.add_child(new St.Label({
                text: entry.label, style_class: 'dock-group-app-label',
                x_align: Clutter.ActorAlign.CENTER,
            }));
            const dot = new St.Widget({
                style_class: 'dock-group-app-dot', x_align: Clutter.ActorAlign.CENTER,
                opacity: host._windowsAdapter._windows(group, entry).length ? 255 : 0,
            });
            dots.push([entry, dot]);
            tile.add_child(dot);
            button.set_child(tile);
            previews.bind(button, entry);
            button.connect('clicked', () => {
                menu.close(BoxPointer.PopupAnimation.FULL);
                host._windowsAdapter._activateEntry(entry);
            });
            button.connect('button-release-event', (_button,event) => {
                if (event.get_button() !== 2) return Clutter.EVENT_PROPAGATE;
                menu.close(BoxPointer.PopupAnimation.FULL);
                host._windowsAdapter._activateEntry(entry,true);
                return Clutter.EVENT_STOP;
            });
            button.connect('scroll-event', (_button,event) => {
                const direction = event.get_scroll_direction();
                if (![Clutter.ScrollDirection.UP,Clutter.ScrollDirection.DOWN].includes(direction)) return Clutter.EVENT_PROPAGATE;
                host._windowsAdapter._cycleEntry(entry,direction === Clutter.ScrollDirection.UP ? -1 : 1);
                return Clutter.EVENT_STOP;
            });
            host._dnd._makeTileDraggable(button, entry, menu, dash);
            tiles.set(entry.desktop, button);
            row.layout_manager.attach(button, index % columns, Math.floor(index / columns), 1, 1);
            index++;
        }
        content.add_child(row);
        item.add_child(content);
        menu.addMenuItem(item);
        menu.actor.connect('key-press-event', (_actor, event) => {
            if (event.get_key_symbol() === Clutter.KEY_z &&
                event.get_state() & Clutter.ModifierType.CONTROL_MASK && host._commands._undoLastMove())
                return Clutter.EVENT_STOP;
            return Clutter.EVENT_PROPAGATE;
        });
        host._stylePopup(menu, group);
        const destroy = menu.destroy.bind(menu);
        menu.destroy = () => {
            if (menu._destroying)
                return;
            menu._destroying = true;
            host._animation._stopAnimation(menu);
            menu._useGlass = false;
            host._syncGlass(menu);
            destroy();
        };
        const close = menu._boxPointer.close.bind(menu._boxPointer);
        const closeMenu = menu.close.bind(menu);
        menu.close = (...args) => {
            host._animation._cancelOpen(menu);
            closeMenu(...args);
        };
        menu._boxPointer.close = (animation, callback) => {
            if (menu._destroying) {
                menu.actor.hide();
                callback?.();
            } else if (animation === BoxPointer.PopupAnimation.NONE || !host._enabled) {
                host._animation._stopAnimation(menu);
                close(BoxPointer.PopupAnimation.NONE, callback);
            } else {
                host._animation._animate(menu, side, false, () => close(BoxPointer.PopupAnimation.NONE, () => {
                    host._syncGlass(menu);
                    callback?.();
                }));
            }
        };
        menu.connect('open-state-changed', (_menu, open) => {
            icon.emit('menu-state-changed', open);
            host._syncGlass(menu);
            if (open) {
                undo.visible = Boolean(host._undo);
                for (const [entry, dot] of dots)
                    dot.opacity = host._windowsAdapter._windows(group, entry).length ? 255 : 0;
            }
        });
        icon.activate = () => this.activate(group.key, host._icons.get(icon));
        const record = {icon, group, menu, dots, row, tiles, title, dockLabel, undo, previews, manager};
        host._icons.set(icon, record);
        icon.connect('notify::mapped', () => host._queueUpdate());
        host._queueUpdate();
    }

    activate(key, record = null) {
        record ??= [...this.host._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        if (!record)
            return false;
        const current = [...this.host._icons.values()].find(item => item.menu.isOpen || item.menu._pendingOpen)?.group.key ?? null;
        this._applyInteraction(folderInteraction({current, target: key}), record);
        return true;
    }

    _press([x, y]) {
        const records = [...this.host._icons.values()].filter(item => item.icon.mapped);
        const anchors = records.map(({icon, group}) => {
            const [left, top] = icon.get_transformed_position();
            const [width, height] = icon.get_transformed_size();
            return {key: group.key, x: left, y: top, width, height};
        });
        const current = records.find(item => item.menu.isOpen || item.menu._pendingOpen)?.group.key ?? null;
        const decision = folderInteraction({current, anchors, point: {x, y}});
        if (!decision.target)
            return false;
        this._applyInteraction(decision, records[decision.anchorIndex]);
        return true;
    }

    _applyInteraction(decision, record) {
        for (const item of this.host._icons.values())
            if (item.menu.isOpen || item.menu._pendingOpen)
                item.menu.close(decision.open ? BoxPointer.PopupAnimation.NONE : BoxPointer.PopupAnimation.FULL);
        if (decision.open)
            this.host._animation._expand(record.menu, record.menu._arrowSide);
    }

    _closeMenus() {
        const host = this.host;
        host._pendingFolder = null;
        for (const {menu} of host._icons.values()) {
            if (menu.isOpen || menu._pendingOpen)
                menu.close(BoxPointer.PopupAnimation.FULL);
        }
    }
}
