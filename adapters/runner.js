// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import {transact, referencedDesktops, folderCatalog, folderCommand} from '../core/engine.js';
import {activation, cycleWindow, canonicalDesktop, expandedFavorites, groupedDesktops} from '../core/applications.js';
import {contract} from '../core/contract.js';
import {preferences, animation, duration, frame, appearance, hoverDuration, hoverRotation, surface} from '../core/preferences.js';
import {miniIconLayout} from '../core/iconGeometry.js';
import {deform} from '../core/animationGeometry.js';
import {settingsPreview, settingsPreviewFrame} from '../core/settingsPreview.js';
import {folderInteraction} from '../core/folderInteraction.js';
import {orbitVelocity, orbitFrame, orbitHoverFrame, orbitMiniatures} from '../core/orbit.js';
import {folderChanges} from '../core/changes.js';
import {pwaIndex, matchPwa} from '../core/windowIdentity.js';

const stream = new Gio.DataInputStream({base_stream:new GioUnix.InputStream({fd:0,close_fd:false})});
const frameSources = new Map();

/** Serve the portable API to GTK adapters until their input pipe closes. */
function dispatch(request) {
    const value = request.value;
    if (request.method === 'pwaIndex') return pwaIndex(value);
    if (request.method === 'matchPwa') return matchPwa(value.index,value.classes,value.fallback);
    if (request.method === 'registerFrame') {
        frameSources.set(value.id,value);
        if (frameSources.size > 64) frameSources.delete(frameSources.keys().next().value);
        return true;
    }
    if (request.method === 'releaseFrame') return frameSources.delete(value);
    if (request.method === 'orbitVelocity') return orbitVelocity(value.values, value.hovered, value.allowed);
    if (request.method === 'orbitFrame') return orbitFrame(value);
    if (request.method === 'orbitHoverFrame') return orbitHoverFrame(value);
    if (request.method === 'orbitMiniatures') return orbitMiniatures(value);
    if (request.method === 'orbitMiniaturesBatch') return value.items.map(item => orbitMiniatures({...item,values:value.values}));
    if (request.method === 'folderInteraction') return folderInteraction(value);
    if (request.method === 'settingsPreview') return settingsPreview(value);
    if (request.method === 'settingsPreviewFrame') return settingsPreviewFrame(value);
    if (request.method === 'folderCatalog') return folderCatalog(value);
    if (request.method === 'folderCommand') return folderCommand(value);
    if (request.method === 'folderChanges') return folderChanges(value.previous,value.next);
    if (request.method === 'references') return referencedDesktops(value.state,value.command);
    if (request.method === 'activation') return activation(value.windows,value.newInstance);
    if (request.method === 'cycle') return cycleWindow(value.windows,value.direction);
    if (request.method === 'canonical') return canonicalDesktop(value.desktop,value.aliases);
    if (request.method === 'favorites') return expandedFavorites(value.groups,value.favorites);
    if (request.method === 'grouped') return groupedDesktops(value.groups,value.favorites);
    if (request.method === 'transaction') return transact(value);
    if (request.method === 'contract') return contract;
    if (request.method === 'preferences') return preferences(item => value[item.name], value.glass);
    if (request.method === 'hoverDuration') return hoverDuration(value);
    if (request.method === 'hoverRotation') return hoverRotation(value);
    if (request.method === 'appearance') return appearance(value);
    if (request.method === 'surface') return surface(value.group, value.blurStrength, value.legacyGlass, value.backdrop);
    if (request.method === 'miniatures') return miniIconLayout(...value);
    if (request.method === 'frame') {
        const source = value.id ? frameSources.get(value.id) : value;
        if (!source) throw new Error('Unknown animation source');
        const effect = animation(source.mode), state = frame(source.mode,value.time,value.opening);
        return {animation:effect,duration:duration(source.mode,source.speed),frame:state,
            points:(source.points || []).map(point => deform(point,source.rect,source.anchor,
                value.progress ?? state.progress,source.edge,effect.id))};
    }
    throw new Error('Unknown core method');
}

while (true) {
    const [line] = stream.read_line_utf8(null);
    if (line === null) break;
    try { print(JSON.stringify({ok:true,result:dispatch(JSON.parse(line))})); }
    catch (error) { print(JSON.stringify({ok:false,error:error.message})); }
}
