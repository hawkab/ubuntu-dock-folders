// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as DND from 'resource:///org/gnome/shell/ui/dnd.js';

/** Translate Shell drag events into folder commands. */
export class DockDragDrop {
    constructor(host) { this.host = host; this.extractLayerSignal = 0; }

    _sourceEntry(source) {
        const host = this.host;
        if (!source?.app || source.app.is_window_backed())
            return null;
        const id = source.app.get_id();
        if (id.startsWith('local.groups.'))
            return null;
        return source.groupEntry ?? host._entryIds.get(id) ?? {desktop: id, label: source.app.get_name()};
    }

    _decorateDrop(icon, group, dash) {
        const host = this.host;
        host._dropIcons.add(icon);
        const canDrop = (source, x, y) => {
            const entry = host._dnd._sourceEntry(source);
            const vertical = [St.Side.LEFT, St.Side.RIGHT].includes(dash._position);
            const center = vertical ? y > icon.height * .22 && y < icon.height * .78 :
                x > icon.width * .22 && x < icon.width * .78;
            return entry && (group || !icon.app.get_id().startsWith('local.groups.')) &&
                entry.desktop !== icon.app.get_id() && source !== icon &&
                center;
        };
        icon.handleDragOver = (source, _actor, x, y) => {
            if (!canDrop(source, x, y)) {
                icon.remove_style_class_name('dock-group-drop-target');
                return DND.DragMotionResult.CONTINUE;
            }
            host._dnd._clearDropHighlight();
            icon.add_style_class_name('dock-group-drop-target');
            dash._clearDragPlaceholder();
            return DND.DragMotionResult.MOVE_DROP;
        };
        icon.acceptDrop = (source, _actor, x, y) => {
            if (!canDrop(source, x, y))
                return false;
            host._dnd._clearDropHighlight();
            const entry = host._dnd._sourceEntry(source);
            if (group)
                host._commands._moveEntry(entry, group.key);
            else
                host._commands._createGroup(entry, host._entryIds.get(icon.app.get_id()) ??
                    {desktop: icon.app.get_id(), label: icon.app.get_name()});
            return true;
        };
        icon.connect('destroy', () => host._dropIcons.delete(icon));
    }

    _clearDropHighlight() {
        const host = this.host;
        for (const icon of host._dropIcons ?? [])
            icon.remove_style_class_name('dock-group-drop-target');
    }

    _makeTileDraggable(button, entry, menu, dash) {
        const host = this.host;
        let alive = true;
        button.connect('destroy', () => { alive = false; });
        button.app = host._appSystem.lookup_app(entry.desktop);
        button.groupEntry = entry;
        button._delegate = button;
        button.getDragActor = () => host._appIcon(entry, 64);
        button.getDragActorSource = () => button.get_child().get_first_child();
        button.handleDragOver = source => {
            if (!host._dnd._sourceEntry(source) || source === button)
                return DND.DragMotionResult.CONTINUE;
            button.add_style_class_name('dock-group-drop-target');
            return DND.DragMotionResult.MOVE_DROP;
        };
        button.acceptDrop = (source, _actor, x) => {
            const member = host._dnd._sourceEntry(source);
            if (!member || source === button)
                return false;
            const apps = entry.group.apps;
            const next = apps[apps.indexOf(entry) + 1]?.desktop;
            host._commands._moveEntry(member, entry.group.key, x > button.width / 2 ? next : entry.desktop);
            return true;
        };
        const draggable = DND.makeDraggable(button, {dragActorMaxSize: 64, dragActorOpacity: 220});
        button._draggable = draggable;
        draggable.connect('drag-begin', () => {
            host._dragging = true;
            for (const record of host._icons.values())
                record.previews.clear();
            button.opacity = 90;
            Main.overview.beginItemDrag(button);
            host._dnd._createExtractTargets(menu, dash);
        });
        draggable.connect('drag-end', () => {
            host._dragging = false;
            if (alive) button.opacity = 255;
            host._dnd._removeExtractTargets();
            host._dnd._clearDropHighlight();
            Main.overview.endItemDrag(button);
            if (!alive || host._configTimer)
                return;
            for (const child of button.get_parent()?.get_children() ?? [])
                child.remove_style_class_name('dock-group-drop-target');
        });
        draggable.connect('drag-cancelled', () => host._dnd._removeExtractTargets());
    }

    _createExtractTargets(menu, dash) {
        const host = this.host;
        host._dnd._removeExtractTargets();
        const layer = menu.actor.get_parent();
        if (!layer) return;
        const dockPoint = (x, y) => {
            if (host._extractLayer !== layer) return null;
            const [lx, ly] = layer.get_transformed_position();
            const [dx, dy] = dash.get_transformed_position();
            const [width, height] = dash.get_transformed_size();
            const local = [x + lx - dx, y + ly - dy];
            return local[0] >= 0 && local[0] < width && local[1] >= 0 && local[1] < height
                ? local : null;
        };
        layer._delegate = {
            handleDragOver: (source, actor, x, y, time) => {
                const point = dockPoint(x, y);
                return point ? dash.handleDragOver(source, actor, ...point, time)
                    : DND.DragMotionResult.CONTINUE;
            },
            acceptDrop: (source, actor, x, y, time) => {
                const point = dockPoint(x, y);
                return Boolean(point && dash.acceptDrop(source, actor, ...point, time));
            },
        };
        host._extractLayer = layer;
        this.extractLayerSignal = layer.connect('destroy', () => {
            host._extractLayer = null;
            this.extractLayerSignal = 0;
        });
        for (const monitor of Main.layoutManager.monitors) {
            const rect = {x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height};
            const reserve = dash.iconSize + 32;
            if (dash._position === St.Side.LEFT) { rect.x += reserve; rect.width -= reserve; }
            else if (dash._position === St.Side.RIGHT) rect.width -= reserve;
            else if (dash._position === St.Side.TOP) { rect.y += reserve; rect.height -= reserve; }
            else rect.height -= reserve;
            const actor = new St.Widget({...rect, reactive: true});
            actor.connect('destroy', () => {
                host._extractTargets = host._extractTargets.filter(target => target !== actor);
            });
            actor._delegate = {
                handleDragOver: source => source?.groupEntry ? DND.DragMotionResult.MOVE_DROP : DND.DragMotionResult.CONTINUE,
                acceptDrop: source => {
                    if (!source?.groupEntry)
                        return false;
                    host._commands._extractEntry(source.groupEntry.desktop, true);
                    return true;
                },
            };
            layer.add_child(actor);
            layer.set_child_below_sibling(actor, menu.actor);
            host._extractTargets.push(actor);
        }
    }

    _removeExtractTargets() {
        const host = this.host;
        if (host._extractLayer) {
            host._extractLayer.disconnect(this.extractLayerSignal);
            delete host._extractLayer._delegate;
        }
        this.extractLayerSignal = 0;
        host._extractLayer = null;
        const targets = host._extractTargets ?? [];
        host._extractTargets = [];
        for (const actor of targets) actor.destroy();
    }
}
