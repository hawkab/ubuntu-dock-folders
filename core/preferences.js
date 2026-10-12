// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {contract} from './contract.js';
import {appearance} from './appearance.js';
export {appearance} from './appearance.js';

/** Return a preference declaration by its portable name. */
export function preference(name) { return contract.preferences.find(item => item.name === name); }

/** Return a schema default, converting portable effect keys for native enums. */
export function defaultValue(name, native = false) {
    const item = preference(name);
    const value = item.storageDefault ?? item.default;
    return native && item.type === 'enum' ? (name === 'animation' ? animation(value) : hoverEffect(value)).id : value;
}

/** Resolve portable or native effect values and their timing. */
export function animation(value) {
    return contract.animations.find(item => item.key === value || item.id === value)
        || contract.animations.find(item => item.key === preference('animation').default);
}

export function hoverEffect(value) {
    return contract.hoverEffects.find(item => item.key === value || item.id === value) || contract.hoverEffects[0];
}

/** Combine independent hover controls while retaining the existing storage values. */
export function hoverChoice(rotate, cards) {
    return contract.hoverEffects.find(item => item.rotate === rotate && item.cards === cards);
}

/** Return hover duration in milliseconds; zero disables interpolation. */
export function hoverDuration(speed) {
    const magnitude = Math.abs(normalize(preference('hoverSpeed'), speed));
    return magnitude ? Math.round(contract.layout.hoverDuration * 100 / magnitude) : 0;
}

/** Return the temporary hover angle with the configured rotation direction. */
export function hoverRotation(values = {}) {
    const speed = normalize(preference('hoverSpeed'), values.hoverSpeed);
    return hoverEffect(values.hoverEffect).rotate && speed
        ? Math.sign(speed) * normalize(preference('hoverAngle'), values.hoverAngle) : 0;
}

export function normalize(preference, value) {
    if (preference.type === 'enum') return (preference.name === 'animation' ? animation(value) : hoverEffect(value)).key;
    if (preference.type === 'bool') return typeof value === 'boolean' ? value : preference.default;
    const number = Number.isFinite(value) ? value : preference.default;
    return Math.max(preference.range[0], Math.min(preference.range[1], preference.type === 'double' ? number : Math.round(number)));
}

/** Return validated preferences through a storage adapter's read function. */
export function preferences(read, legacyGlass = true) {
    return contract.preferences.reduce((values,item) => {
        values[item.name] = item.name === 'blurStrength' ? blurLevel(read(item), legacyGlass) : normalize(item,read(item));
        return values;
    },{});
}

/** Resolve the blur amount, retaining the previous switch until first adjustment. */
export function blurLevel(value, legacyGlass = true) {
    const setting = contract.preferences.find(item => item.name === 'blurStrength');
    return Number.isFinite(value) && value >= 0 ? normalize(setting,value)
        : legacyGlass ? (value === -1 ? contract.legacy.blurStrength : setting.default) : 0;
}

/** Resolve independent tint opacity and blur for a native surface or preview. */
export function surface(group, blurStrength, legacyGlass = true, backdrop = null) {
    const value = appearance(group);
    if (!Number.isFinite(group?.backgroundOpacity))
        value.backgroundOpacity = legacyGlass ? value.glassOpacity : value.popupOpacity;
    value.blurStrength = blurLevel(Number.isFinite(group?.blurStrength) && group.blurStrength >= 0
        ? group.blurStrength : blurStrength, legacyGlass);
    value.blurAmount = value.blurStrength / 100;
    value.blurRadius = contract.layout.blurRadius * value.blurStrength / 100;
    value.glass = value.blurStrength > 0;
    value.composedBackground = /^#[0-9a-f]{6}$/i.test(backdrop)
        ? blendColor(value.popupColor,backdrop,value.backgroundOpacity) : value.popupColor;
    value.foreground = value.wallpaper ? '#ffffff' : contrastColor(value.composedBackground);
    return value;
}

/** Composite an opaque color over a backdrop at the configured opacity. */
export function blendColor(tint, backdrop, opacity) {
    return '#' + [1,3,5].map(index => Math.round(parseInt(tint.slice(index,index+2),16) * opacity
        + parseInt(backdrop.slice(index,index+2),16) * (1-opacity)).toString(16).padStart(2,'0')).join('');
}

/** Choose black or white text with the higher contrast against a background color. */
export function contrastColor(background) {
    const color = /^#[0-9a-f]{6}$/i.test(background) ? background : contract.appearance.popupColor;
    const channels = [1,3,5].map(index => parseInt(color.slice(index,index+2),16) / 255)
        .map(value => value <= .04045 ? value / 12.92 : Math.pow((value + .055) / 1.055,2.4));
    const luminance = channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
    return (luminance + .05) / .05 >= 1.05 / (luminance + .05) ? '#000000' : '#ffffff';
}

export function duration(value, speed) {
    return Math.round(animation(value).duration * 100 / normalize(preference('animationSpeed'),speed));
}

export function frame(value, progress, opening) {
    const effect = animation(value);
    const t = Math.max(0, Math.min(1, progress));
    const p = effect.curve === 'linear' ? (opening ? t : 1-t)
        : opening ? 1-Math.pow(1-t,3) : 1-t*t*t;
    return {progress:p, opacity:effect.fade ? p : 1};
}
