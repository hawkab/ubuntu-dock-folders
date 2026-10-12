// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import GLib from 'gi://GLib';
import {contract} from '../core/contract.js';

/** Reject a mixed core bundle before a shell adapter changes settings or actors. */
export function verifyCore(directory) {
    const read = name => directory.get_child(name).load_contents(null)[1];
    const manifest=JSON.parse(new TextDecoder().decode(read('manifest.json')));
    if (manifest.api !== contract.version) throw new Error('Dock folders core API does not match its contract');
    for (const [name,expected] of Object.entries(manifest.files))
        if (name.includes('/') || GLib.compute_checksum_for_data(GLib.ChecksumType.SHA256,read(name)) !== expected)
            throw new Error('Dock folders core is incomplete or belongs to another build');
    return manifest;
}
