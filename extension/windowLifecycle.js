// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/** Release resources once when a GTK window closes or is destroyed. */
export function onWindowClose(window, callback) {
    let closed = false;
    const close = () => {
        if (!closed) {
            closed = true;
            callback(window);
        }
        return false;
    };
    window.connect('close-request', close);
    window.connect('unrealize', close);
}
