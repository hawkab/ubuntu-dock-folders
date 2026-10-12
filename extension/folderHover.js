// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {miniIconLayout} from './iconGeometry.js';
import {appearance, hoverEffect, hoverDuration, hoverRotation} from './core/preferences.js';
import {orbitFrame, orbitHoverFrame} from './core/orbit.js';
import {contract} from './core/contract.js';

/** Animate dock miniatures on hover and release signals with their actor. */
export function bindFolderHover(source, actor, bubbles, settings, group, size, vertical, crossSize, createBubble, baseSize) {
    let progress = source._folderHoverProgress || 0, timeline = null;
    const orbit = {angle: source._orbitalPhase || 0, velocity: 0, timer: 0, last: 0};
    actor._orbit = orbit;
    const readValues = () => ({enabled: settings.get_boolean('enabled'),
        orbitSpeed: settings.get_int('orbit-speed'), hoverOrbitSpeed: settings.get_int('hover-orbit-speed'),
        hoverSpeed: settings.get_int('hover-speed'), hoverAngle: settings.get_int('hover-angle'), hoverEffect: settings.get_string('hover-effect')});
    let motionValues = readValues();
    const values = () => motionValues;
    const allowed = () => actor.mapped && !source._dragging && St.Settings.get().enable_animations;
    const apply = value => {
        orbit.angle = orbitHoverFrame({angle: orbit.angle, velocity: orbit.velocity,
            previous: progress, progress: value, values: values()}).angle;
        source._orbitalPhase = orbit.angle;
        progress = value;
        source._folderHoverProgress = value;
        actor._hoverProgress = value;
        const mode = hoverEffect(settings.get_string('hover-effect'));
        const layout = miniIconLayout(size, group.apps.length, settings.get_int('mini-icon-size') / 100,
            crossSize, vertical, group.id, (group.iconRotation || 0) + orbit.angle + hoverRotation(values()) * value,
            group.alwaysStack || false, mode.cards ? value : 0, mode.cards);
        const x = (layout.width - size) / 2, y = (layout.height - size) / 2;
        actor._miniLayout = layout;
        actor.set_size(layout.width, layout.height);
        const circle = actor.get_first_child();
        circle.set_position(x + (size-circle.width)/2, y + (size-circle.height)/2);
        while (bubbles.length < layout.items.length) createBubble(bubbles.length);
        bubbles.forEach((bubble, index) => {
            const item = layout.items[index];
            bubble.visible = Boolean(item);
            if (!item) return;
            bubble.opacity = Math.round(item.opacity * 255);
            bubble.set_size(layout.size,layout.size);
            const glyph = bubble.get_child();
            if (glyph instanceof St.Icon) glyph.icon_size = layout.size;
            else glyph.set_size(layout.size,layout.size);
            bubble.set_position(x + item.x, y + item.y);
            bubble.rotation_angle_z = item.rotation;
            bubble.get_child().rotation_angle_z = item.glyphRotation;
        });
    };
    const stopOrbit = () => {
        if (orbit.timer) GLib.source_remove(orbit.timer);
        orbit.timer = 0;
    };
    const syncOrbit = () => {
        motionValues = readValues();
        const state = orbitFrame({angle: orbit.angle, velocity: orbit.velocity,
            values: values(), hovered: source.hover, allowed: allowed()});
        orbit.velocity = state.velocity;
        if (!state.active) { stopOrbit(); return; }
        if (orbit.timer) return;
        orbit.last = GLib.get_monotonic_time();
        orbit.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, contract.layout.orbitFrameInterval, () => {
            const now = GLib.get_monotonic_time();
            const state = orbitFrame({angle: orbit.angle, velocity: orbit.velocity, elapsed: (now-orbit.last)/1000,
                values: values(), hovered: source.hover, allowed: allowed()});
            orbit.last = now;
            orbit.angle = state.angle;
            orbit.velocity = state.velocity;
            source._orbitalPhase = state.angle;
            apply(progress);
            if (!state.active) { orbit.timer = 0; return GLib.SOURCE_REMOVE; }
            return GLib.SOURCE_CONTINUE;
        });
    };
    const syncHover = () => {
        syncOrbit();
        timeline?.stop();
        const mode=hoverEffect(settings.get_string('hover-effect'));
        if (!mode.rotate && !(mode.cards && (group.alwaysStack || group.apps.length > 5))) { apply(0); return; }
        const target = source.hover && !source._dragging ? 1 : 0;
        const duration = hoverDuration(settings.get_int('hover-speed'));
        if (!duration || !St.Settings.get().enable_animations) { apply(target); return; }
        const from = progress;
        if (from === target) { apply(target); return; }
        timeline = new Clutter.Timeline({actor, duration});
        timeline.connect('new-frame', () => {
            const t = timeline.get_progress();
            apply(from + (target - from) * t * t * (3 - 2 * t));
        });
        timeline.connect('completed', () => { apply(target); timeline = null; });
        timeline.start();
    };
    actor.refreshFormation = () => {
        size = baseSize * settings.get_int('group-icon-size') / 100;
        crossSize = size+12;
        const resolved = appearance(group);
        const rgb = [1,3,5].map(index => parseInt(resolved.dockColor.slice(index,index+2),16));
        const circle = actor.get_first_child(), diameter = size * contract.layout.circleScale;
        circle.set_size(diameter,diameter);
        circle.set_style(`background-color: rgba(${rgb.join(',')},${resolved.dockOpacity}); border-radius: ${diameter/2}px; border: 1px solid rgba(255,255,255,${resolved.dockOpacity*.25});`);
        syncHover();
        for (const bubble of bubbles) bubble.set_style(actor._miniLayout.stacked
            ? `background-color: ${resolved.dockColor}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.25);`
            : 'background-color: transparent;');
    };
    source.connectObject('notify::hover', syncHover, actor);
    actor.connectObject('notify::mapped', syncOrbit, actor);
    settings.connectObject('changed::orbit-speed', syncOrbit, 'changed::hover-orbit-speed', syncOrbit,
        'changed::enabled', syncOrbit, actor);
    St.Settings.get().connectObject('notify::enable-animations', syncOrbit, actor);
    const draggable = source._draggable;
    const dragSignals = draggable ? ['drag-begin', 'drag-end'].map(name => draggable.connect(name, syncOrbit)) : [];
    actor.connect('destroy', () => {
        timeline?.stop(); timeline = null; stopOrbit();
        for (const id of dragSignals)
            if (draggable.signalHandlerIsConnected(id)) draggable.disconnect(id);
    });
    apply(progress);
    syncHover();
}
