// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

/** Adapt ordinary Dock icons to profile-aware PWA windows. */
export class PwaDock {
    constructor(host) {
        this.host = host;
        this.icons = new WeakSet();
        this.windows = new WeakMap();
    }

    decorate(icon) {
        if (this.icons.has(icon) || icon.app.get_id().startsWith('local.groups.')) return;
        this.icons.add(icon);
        const host = this.host, id = icon.app.get_id();
        const running = icon._updateRunningState.bind(icon);
        const activate = icon.activate.bind(icon);
        icon.getWindows = () => host._windowsAdapter.applicationWindows(icon.app);
        icon.ownsWindow = window => icon.getWindows().includes(window);
        icon._updateRunningState = () => {
            if (host._pwaDesktops.has(id)) icon.running = icon.windowsCount > 0;
            else running();
        };
        icon._updateFocusState = () => {
            icon.focused = Boolean(icon.running && icon.getWindows().includes(global.display.focus_window));
        };
        icon.activate = button => {
            if (!host._pwaDesktops.has(id)) return activate(button);
            const windows = icon.getInterestingWindows();
            if (!windows.length) return activate(button);
            const original = icon.app.activate;
            const own = Object.prototype.hasOwnProperty.call(icon.app,'activate');
            icon.app.activate = () => Main.activateWindow(windows[0]);
            try { return activate(button); }
            finally {
                if (own) icon.app.activate = original;
                else delete icon.app.activate;
            }
        };
    }

    update() {
        for (const dock of this.host._dock._docks())
            for (const icon of dock.dash.getAppIcons())
                if (this.icons.has(icon) && icon.mapped && icon.get_stage()) {
                    const windows = icon.getInterestingWindows(), previous = this.windows.get(icon);
                    if (!previous || windows.length !== previous.length || windows.some((window,i) => window !== previous[i])) {
                        this.windows.set(icon,windows);
                        icon._updateWindows();
                    } else icon._updateFocusState();
                }
    }
}
