// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {contract} from './contract.js';
import {hoverRotation, normalize, preference} from './preferences.js';
import {miniIconLayout} from './iconGeometry.js';

/** Return the hover override or continuous speed in degrees per second. */
export function orbitVelocity(values = {}, hovered = false, allowed = true) {
    if (!allowed || values.enabled === false) return 0;
    const hover = normalize(preference('hoverOrbitSpeed'), values.hoverOrbitSpeed);
    return hovered && hover !== 0 ? hover : normalize(preference('orbitSpeed'), values.orbitSpeed);
}

/** Smooth velocity and integrate phase; pass both returned values to the next frame. */
export function orbitFrame({angle = 0, velocity = 0, elapsed = 0, values = {}, hovered = false, allowed = true} = {}) {
    const phase = Number.isFinite(angle) ? angle : 0;
    if (!allowed || values.enabled === false) return {angle: phase, velocity: 0, active: false};
    const target = orbitVelocity(values, hovered);
    const limit = Math.max(preference('orbitSpeed').range[1], preference('hoverOrbitSpeed').range[1]);
    const previous = Number.isFinite(velocity) ? Math.max(-limit, Math.min(limit, velocity)) : 0;
    const time = (Number.isFinite(elapsed) ? Math.max(0, Math.min(contract.layout.orbitMaxElapsed, elapsed)) : 0) / 1000;
    if (!time) return {angle: phase, velocity: previous, active: previous !== 0 || target !== 0};
    const response = contract.layout.orbitResponseTime / 1000;
    const decay = Math.exp(-time / response);
    const distance = target * time + (previous - target) * response * (1 - decay);
    let speed = target + (previous - target) * decay;
    if (Math.abs(speed - target) < contract.layout.orbitStopThreshold) speed = target;
    return {angle: ((phase + distance) % 360 + 360) % 360, velocity: speed, active: speed !== 0 || target !== 0};
}

/** Absorb a returning hover turn into the orbital phase to avoid reversing motion. */
export function orbitHoverFrame({angle = 0, velocity = 0, previous = 0, progress = 0, values = {}} = {}) {
    const current = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;
    const prior = Number.isFinite(previous) ? Math.max(0, Math.min(1, previous)) : 0;
    const phase = Number.isFinite(angle) ? angle : 0;
    const moving = values.enabled !== false && (orbitVelocity(values, false) !== 0 ||
        orbitVelocity(values, true) !== 0 || Number.isFinite(velocity) && velocity !== 0);
    const offset = moving ? Math.max(0, prior - current) * hoverRotation(values) : 0;
    return {angle: offset !== 0 ? ((phase + offset) % 360 + 360) % 360 : phase, progress: current};
}

/** Return an orbital frame and miniature layout in one call for native adapters. */
export function orbitMiniatures(request) {
    const hover = orbitHoverFrame({angle: request.angle, velocity: request.velocity,
        previous: request.previousProgress, progress: request.hoverProgress, values: request.values});
    const state = orbitFrame({angle: hover.angle, velocity: request.velocity, elapsed: request.elapsed,
        values: request.values, hovered: request.hovered, allowed: request.allowed});
    const parameters = request.args.slice();
    parameters[6] = (parameters[6] || 0) + state.angle + hoverRotation(request.values) * hover.progress;
    return {angle: state.angle, velocity: state.velocity, active: state.active,
        layout: miniIconLayout.apply(null, parameters)};
}
