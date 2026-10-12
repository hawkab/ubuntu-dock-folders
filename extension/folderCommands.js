// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {transact, membership, referencedDesktops} from './core/engine.js';

/** Adapt Shell drag and undo actions to the portable folder API. */
export class FolderCommands {
    constructor(host, ports) { this.host = host; this.ports = ports; }

    _execute(command, supplied = {}) {
        const host = this.host, groups = JSON.parse(host._settings.get_string('groups'));
        const favorites = this.ports.favorites();
        const entries = Object.assign({}, supplied);
        for (const group of Object.values(groups)) for (const entry of group.apps)
            if (this.ports.isAvailable(entry.desktop)) entries[entry.desktop] = entry;
        for (const id of referencedDesktops({groups,favorites,undo:host._undo || null},command))
            if (typeof id === 'string' && !id.startsWith('local.groups.') && this.ports.isAvailable(id)) entries[id] ||= {desktop:id,label:id};
        const result = transact({state:{groups,favorites,undo:host._undo || null},command,entries,token:this.ports.makeSuffix()});
        host._undo = result.state.undo;
        if (!result.changed) return false;
        host._store._commitGroups(result.state.groups,result.state.favorites);
        if (command.operation === 'undo') this.ports.feedback.clear();
        else if (host._undo) this.ports.feedback.show(() => this._undoLastMove());
        return true;
    }

    _membership(groups) { return JSON.stringify(membership(groups)); }

    _undoLastMove() {
        if (!this.host._undo) return false;
        this.host._view._closeMenus();
        return this._execute({operation:'undo'});
    }

    _moveEntry(entry, key, before = null) {
        if (entry.group?.key !== key) this.host._view._closeMenus();
        this._execute({operation:'move',desktop:entry.desktop,key,before});
    }

    _createGroup(source, target) {
        this._execute({operation:'create',desktop:source.desktop,target:target.desktop,name:this.ports.newFolderName},{[source.desktop]:source,[target.desktop]:target});
    }

    _extractEntry(desktop, pin) {
        this.host._view._closeMenus();
        this._execute({operation:'extract',desktop,pin});
    }
}
