// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import St from 'gi://St';

// Select the box layout API supported by the running GNOME Shell.
export function setBoxOrientation(box, orientation) {
    if ('orientation' in box)
        box.orientation = orientation;
    else
        box.vertical = orientation === Clutter.Orientation.VERTICAL;
}

export function createBoxLayout(orientation, properties = {}) {
    const box = new St.BoxLayout(properties);
    setBoxOrientation(box, orientation);
    return box;
}
