// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import St from 'gi://St';
import {FlowEffect} from './effects.js';
import {animation, duration, frame} from './core/preferences.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';

/** Animate a folder relative to its dock icon. */
export class FolderAnimation {
    constructor(host) { this.host = host; }

    _expand(menu, side) {
        const host = this.host;
        host._view._closeMenus();
        host._animation._stopAnimation(menu);
        menu.actor.set_scale(1, 1);
        const open = () => {
            this._cancelOpen(menu);
            if (!host._enabled || menu._destroying)
                return;
            menu.open(BoxPointer.PopupAnimation.NONE);
            this._animate(menu, side, true);
        };
        if (this._anchorReady(menu)) {
            open();
            return;
        }
        const pending = {signals: [], update: 0};
        menu._pendingOpen = pending;
        const schedule = () => {
            if (pending.update || menu._pendingOpen !== pending)
                return;
            pending.update = global.stage.connect('after-update', () => {
                global.stage.disconnect(pending.update);
                pending.update = 0;
                if (this._anchorReady(menu))
                    open();
            });
        };
        for (let actor = menu.sourceActor; actor && actor !== global.stage; actor = actor.get_parent()) {
            for (const signal of ['notify::allocation', 'notify::mapped'])
                pending.signals.push([actor, actor.connect(signal, schedule)]);
        }
        schedule();
    }

    _anchorReady(menu) {
        const source = menu.sourceActor;
        if (!source.mapped)
            return false;
        for (let actor = source; actor && actor !== global.stage; actor = actor.get_parent()) {
            if (!actor.has_allocation())
                return false;
            const box = actor.allocation;
            if (![box.x1, box.y1, box.x2, box.y2].every(Number.isFinite) ||
                (actor === source && (box.get_width() <= 0 || box.get_height() <= 0)))
                return false;
        }
        return source.get_stage() === global.stage;
    }

    _cancelOpen(menu) {
        const pending = menu._pendingOpen;
        if (!pending)
            return;
        menu._pendingOpen = null;
        if (pending.update)
            global.stage.disconnect(pending.update);
        for (const [actor, signal] of pending.signals)
            actor.disconnect(signal);
    }

    _animate(menu, side, opening, complete = null) {
        const host = this.host;
        host._animation._stopAnimation(menu);
        const actor = menu.actor;
        const mode = host._settings.get_string('animation');
        if (!St.Settings.get().enable_animations || mode === 'none') {
            actor.set_scale(1, 1);
            actor.opacity = 255;
            complete?.();
            return;
        }
        const definition = animation(mode);
        const flow = !['none','fade','scale'].includes(definition.key);
        const timeline = new Clutter.Timeline({duration: duration(mode,host._settings.get_int('animation-speed')), actor});
        menu._timeline = timeline;
        actor.opacity = definition.fade && opening ? 0 : 255;
        if (flow) {
            actor.set_scale(1, 1);
            const effect = new FlowEffect(side, definition.id);
            actor.add_effect_with_name('dock-group-flow', effect);
            menu._flowEffect = effect;
            effect.progress = opening ? 0 : 1;
            effect.invalidate();
            timeline.connect('new-frame', () => {
                host._positionGlass(menu);
                const origin = host._animation._animationOrigin(menu);
                if (origin) {
                    effect.originX = origin.x;
                    effect.originY = origin.y;
                }
                const current = frame(mode,timeline.get_progress(),opening);
                effect.progress = current.progress;
                actor.opacity = Math.round(255 * current.opacity);
                effect.invalidate();
            });
            timeline.connect('completed', () => {
                actor.remove_effect(effect);
                menu._flowEffect = null;
                menu._timeline = null;
                host._positionGlass(menu);
                complete?.();
            });
        } else {
            if (opening) {
                actor.set_scale(mode === 'fade' ? 1 : .12, mode === 'fade' ? 1 : .12);
                actor.opacity = definition.fade ? 0 : 255;
            }
            timeline.connect('new-frame', () => {
                host._positionGlass(menu);
                const origin = host._animation._animationOrigin(menu);
                if (origin)
                    actor.set_pivot_point(origin.x / origin.width, origin.y / origin.height);
                const current = frame(mode,timeline.get_progress(),opening);
                const scale = mode === 'fade' ? 1 : .12 + .88 * current.progress;
                actor.set_scale(scale,scale);
                actor.opacity = Math.round(255 * current.opacity);
            });
            timeline.connect('completed', () => {
                menu._timeline = null;
                host._positionGlass(menu);
                complete?.();
            });
        }
        timeline.start();
    }

    _animationOrigin(menu) {
        const source = menu.sourceActor.icon?.icon ?? menu.sourceActor;
        if (!source.mapped)
            return null;
        const box = menu.actor.allocation;
        const width = box.get_width();
        const height = box.get_height();
        if (![box.x1, box.y1, width, height].every(Number.isFinite) || width <= 0 || height <= 0)
            return null;
        const [x, y] = source.get_transformed_position();
        const [w, h] = source.get_transformed_size();
        const center = [x + w / 2, y + h / 2];
        if (![...center, w, h].every(Number.isFinite) || w <= 0 || h <= 0)
            return null;
        const [success, localX, localY] = menu.actor.get_parent().transform_stage_point(...center);
        if (!success || ![localX, localY].every(Number.isFinite))
            return null;
        const origin = {x: localX - box.x1, y: localY - box.y1, width, height, center};
        menu._origin = origin;
        return origin;
    }

    _stopAnimation(menu) {
        this._cancelOpen(menu);
        menu.actor.remove_all_transitions();
        menu._timeline?.stop();
        menu._timeline = null;
        if (menu._flowEffect)
            menu.actor.remove_effect(menu._flowEffect);
        menu._flowEffect = null;
    }
}
