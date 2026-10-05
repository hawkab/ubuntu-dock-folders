// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import {WindowPreviewMenuItem} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/windowPreview.js';
import {setBoxOrientation} from './compat.js';

// Share pointer and keyboard focus between a folder and its window previews.
export class FolderMenuManager extends PopupMenu.PopupMenuManager {
    constructor(menu, previews) {
        super(menu.sourceActor);
        this.previews = previews;
        this.layer = new St.Widget({layout_manager: new Clutter.BinLayout()});
        this.layer.add_constraint(new Clutter.BindConstraint({source: global.stage,
            coordinate: Clutter.BindCoordinate.SIZE}));
        Main.uiGroup.add_child(this.layer);
        menu.actor.get_parent().remove_child(menu.actor);
        menu.actor.set({x_align: Clutter.ActorAlign.START, y_align: Clutter.ActorAlign.START});
        this.layer.add_child(menu.actor);
        this.layer.hide();
        this.layer.connect('captured-event', (_actor, event) => {
            if (menu.actor.contains(global.stage.get_event_actor(event)))
                return Clutter.EVENT_PROPAGATE;
            return this._onCapturedEvent(menu.actor, event);
        });
        this.addMenu(menu);
        menu.connect('menu-closed', () => {
            if (!menu.isOpen)
                this.layer.hide();
        });
        menu.connect('destroy', () => this.layer.destroy());
    }

    _onMenuOpenState(menu, open) {
        if (open) {
            this.layer.show();
            Main.uiGroup.set_child_above_sibling(this.layer, null);
            this._grab = Main.pushModal(this.layer, this._grabParams);
            this.activeMenu = menu;
            menu.actor.grab_key_focus();
        } else if (this.activeMenu === menu) {
            this.activeMenu = null;
            Main.popModal(this._grab);
            this._grab = null;
        }
    }

    _onCapturedEvent(actor, event) {
        if (this.previews.contains(global.stage.get_event_actor(event)))
            return Clutter.EVENT_PROPAGATE;
        return super._onCapturedEvent(actor, event);
    }
}

// Show window thumbnails on hover, with activation and close controls.
export class WindowPreviews {
    constructor(menu, {getWindows, isDragging, onUndo}) {
        this.menu = menu;
        this.getWindows = getWindows;
        this.isDragging = isDragging;
        this.onUndo = onUndo;
        this.signals = [];
        this.pendingDestroy = new Map();
        this.openTimer = 0;
        this.closeTimer = 0;
        this.popup = null;
        this._connect(menu, 'open-state-changed', (_menu, open) => {
            if (!open)
                this.clear();
        });
        this._connect(menu, 'destroy', () => this.destroy());
    }

    _connect(object, signal, callback) {
        this.signals.push([object, object.connect(signal, callback)]);
    }

    _disconnect(object) {
        this.signals = this.signals.filter(([source, signal]) => {
            if (source !== object)
                return true;
            source.disconnect(signal);
            return false;
        });
    }

    bind(button, entry) {
        button.track_hover = true;
        this._connect(button, 'notify::hover', () => {
            if (button.hover)
                this._scheduleOpen(button, entry);
            else
                this._scheduleClose();
        });
        this._connect(button, 'key-focus-in', () => {
            if (!button.hover)
                this._scheduleOpen(button, entry, true);
        });
        this._connect(button, 'key-focus-out', () => this._scheduleClose());
        this._connect(button, 'destroy', () => {
            this._disconnect(button);
            if (this.button === button)
                this.clear();
        });
    }

    contains(actor) {
        return Boolean(actor && this.popup?.actor.contains(actor));
    }

    _cancelTimers() {
        for (const key of ['openTimer', 'closeTimer']) {
            if (this[key])
                GLib.source_remove(this[key]);
            this[key] = 0;
        }
    }

    _scheduleOpen(button, entry, keyboard = false) {
        this._cancelTimers();
        if (!this.menu.isOpen || this.isDragging())
            return;
        this.openTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            this.openTimer = 0;
            if (this.menu.isOpen && !this.isDragging() && (button.hover || button.has_key_focus()))
                this._open(button, entry, keyboard);
            return GLib.SOURCE_REMOVE;
        });
    }

    _scheduleClose() {
        this._cancelTimers();
        if (!this.popup)
            return;
        this.closeTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
            this.closeTimer = 0;
            const focus = global.stage.get_key_focus();
            if (!this.button.hover && !this.popup.actor.hover &&
                !(this.keyboard && (this.button.has_key_focus() || this.contains(focus))))
                this.clear();
            return GLib.SOURCE_REMOVE;
        });
    }

    _open(button, entry, keyboard) {
        if (this.button === button && this.popup) {
            this.update();
            return;
        }
        this.clear();
        if (!this.getWindows(entry).length)
            return;
        this.button = button;
        this.entry = entry;
        this.keyboard = keyboard;
        this.popup = new PopupMenu.PopupMenu(button, 0.5, St.Side.TOP);
        this.popup._setParent(this.menu);
        this.popup.actor.add_style_class_name('dock-group-window-previews');
        this.popup.actor.add_style_class_name('app-menu');
        this.popup.actor.reactive = true;
        this.popup.actor.track_hover = true;
        this.popup.actor.set({x_align: Clutter.ActorAlign.START, y_align: Clutter.ActorAlign.START});
        this.menu.actor.get_parent().add_child(this.popup.actor);
        this.popup.actor.hide();
        const monitor = Main.layoutManager.findMonitorForActor(button) ?? Main.layoutManager.primaryMonitor;
        const workArea = Main.layoutManager.getWorkAreaForMonitor(monitor.index);
        const scale = St.ThemeContext.get_for_stage(global.stage).scaleFactor;
        this.maxWidth = Math.max(250, workArea.width / scale - 80);
        this.popup.actor.set_style(`max-width: ${this.maxWidth + 30}px;`);
        this.section = new PopupMenu.PopupMenuSection();
        setBoxOrientation(this.section.box, Clutter.Orientation.HORIZONTAL);
        this.section.actor = new St.ScrollView({
            hscrollbar_policy: St.PolicyType.AUTOMATIC,
            vscrollbar_policy: St.PolicyType.NEVER,
            overlay_scrollbars: true,
            style: `max-width: ${this.maxWidth}px;`,
            child: this.section.box,
        });
        this.section.actor._delegate = this.section;
        this.popup.addMenuItem(this.section);
        this.popup.actor.connect('notify::hover', () => {
            if (this.popup?.actor.hover)
                this._cancelTimers();
            else
                this._scheduleClose();
        });
        this.popup.actor.connect('notify::allocation', () => this._resize());
        this.popup.actor.connect('key-press-event', (_actor, event) => {
            this.keyboard = true;
            if (event.get_key_symbol() === Clutter.KEY_Escape) {
                this.menu.close(BoxPointer.PopupAnimation.FULL);
                return Clutter.EVENT_STOP;
            }
            if (event.get_key_symbol() === Clutter.KEY_z &&
                event.get_state() & Clutter.ModifierType.CONTROL_MASK && this.onUndo())
                return Clutter.EVENT_STOP;
            return Clutter.EVENT_PROPAGATE;
        });
        const popup = this.popup;
        popup.connect('open-state-changed', (_popup, open) => {
            if (!open && this.popup === popup)
                this.clear();
        });
        this.signature = null;
        this.update();
        this.popup?.open(BoxPointer.PopupAnimation.FADE);
    }

    update() {
        if (!this.popup)
            return;
        const windows = this.getWindows(this.entry).sort((a, b) =>
            a.get_stable_sequence() - b.get_stable_sequence());
        if (!windows.length || this.isDragging()) {
            this.clear();
            return;
        }
        const signature = windows.map(window => window.get_stable_sequence()).join(',');
        if (signature === this.signature)
            return;
        this.signature = signature;
        const items = this.section._getMenuItems();
        for (const item of items) {
            if (!windows.includes(item._window))
                item.destroy();
        }
        const popup = this.popup;
        for (const window of windows) {
            if (items.some(item => item._window === window))
                continue;
            const item = new WindowPreviewMenuItem(window, St.Side.TOP);
            item.connect('destroy', () => {
                if (popup._activeMenuItem === item)
                    popup._activeMenuItem = null;
            });
            this.section.addMenuItem(item);
        }
        this._resize();
    }

    _resize() {
        if (!this.section)
            return;
        const width = this.section.box.get_preferred_width(-1)[1];
        this.section.actor.hscrollbar_policy = width > this.maxWidth
            ? St.PolicyType.AUTOMATIC : St.PolicyType.NEVER;
        this.section.actor.width = Math.min(this.maxWidth, width);
    }

    clear() {
        this._cancelTimers();
        const popup = this.popup;
        this.popup = null;
        this.button = null;
        this.entry = null;
        this.section = null;
        if (popup) {
            popup.close(BoxPointer.PopupAnimation.NONE);
            popup.actor.hide();
            const id = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this.pendingDestroy.delete(id);
                popup.destroy();
                return GLib.SOURCE_REMOVE;
            });
            this.pendingDestroy.set(id, popup);
        }
    }

    destroy() {
        this.clear();
        for (const [id, popup] of this.pendingDestroy) {
            GLib.source_remove(id);
            popup.destroy();
        }
        this.pendingDestroy.clear();
        for (const [object, signal] of this.signals)
            object.disconnect(signal);
        this.signals = [];
    }
}
