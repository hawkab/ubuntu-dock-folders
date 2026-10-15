// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import GioUnix from 'gi://GioUnix';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {DockManager} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/docking.js';
import {activation, cycleWindow} from './core/applications.js';
import {matchPwa} from './core/windowIdentity.js';

/** Identify grouped windows and activate their applications. */
export class DockWindows {
    constructor(host) { this.host = host; }

    /** Build one event-local window index; discard it before handling later events. */
    beginUpdate() {
        const host = this.host;
        this.favorites = new Set(global.settings.get_strv('favorite-apps'));
        this.snapshot = new Map();
        this.applications = new Map();
        for (const actor of global.get_window_actors()) {
            const window = actor.meta_window;
            if (!window || window.skip_taskbar) continue;
            const desktop = this._pwaDesktop(window) ?? host._tracker.get_window_app(window)?.get_id();
            if (desktop) {
                if (!this.applications.has(desktop)) this.applications.set(desktop,[]);
                this.applications.get(desktop).push(window);
            }
            const entry = this._entryForWindow(window);
            if (!entry) continue;
            if (!this.snapshot.has(entry)) this.snapshot.set(entry,[]);
            this.snapshot.get(entry).push(window);
        }
    }

    endUpdate() { this.snapshot = null; this.favorites = null; this.applications = null; }

    _pwaDesktop(window) {
        return matchPwa(this.host._pwas ?? {},[window.get_wm_class_instance(),window.get_wm_class()],null);
    }

    /** Return only windows represented by this launcher. */
    applicationWindows(app) {
        const id = app.get_id();
        if (this.applications) return this.applications.get(id) || [];
        const windows = this.host._pwaDesktops.has(id)
            ? global.get_window_actors().map(actor => actor.meta_window).filter(Boolean) : app.get_windows();
        return windows.filter(window => !window.skip_taskbar &&
            (this._pwaDesktop(window) ?? this.host._tracker.get_window_app(window)?.get_id()) === id);
    }

    /** Include running PWA launchers even when the native tracker returns Chrome. */
    runningApplications() {
        const apps = new Map(this.host._getRunning().map(app => [app.get_id(),app]));
        const desktops = this.applications ? [...this.applications.keys()] :
            global.get_window_actors().map(actor => actor.meta_window).filter(Boolean).map(window => this._pwaDesktop(window));
        for (const desktop of desktops) {
            if (!desktop || !this.host._pwaDesktops.has(desktop) || apps.has(desktop)) continue;
            const app = this.host._appSystem.lookup_app(desktop);
            if (app) apps.set(desktop,app);
        }
        return [...apps.values()].filter(app => !this._isHidden(app));
    }

    _activeGroup(group) {
        const host = this.host;
        return host._settings.get_boolean('enabled') && DockManager.getDefault()?.settings.showFavorites &&
            (this.favorites?.has(group.desktopId) ?? global.settings.get_strv('favorite-apps').includes(group.desktopId));
    }

    _entryForWindow(window, app = null) {
        const host = this.host;
        const classes = [window.get_wm_class_instance(), window.get_wm_class()];
        const pwa = matchPwa(host._pwas ?? {},classes,null);
        if (pwa !== null) return pwa ? host._entryIds.get(pwa) ?? null : null;
        app ??= host._tracker.get_window_app(window);
        const identified = app ? host._entryIds.get(app.get_id()) : null;
        if (identified && !['google-chrome.desktop', 'chromium-gost.desktop'].includes(identified.desktop))
            return identified;
        for (const value of classes) {
            const entry = value ? host._classes.get(value.toLowerCase()) : null;
            if (entry)
                return entry;
        }
        return identified;
    }

    _isHidden(app) {
        const host = this.host;
        const windows = app.get_windows().filter(window => !window.skip_taskbar);
        if (windows.length) {
            return windows.every(window => {
                const pwa = this._pwaDesktop(window);
                if (pwa && pwa !== app.get_id()) return true;
                const entry = host._windowsAdapter._entryForWindow(window, app);
                return entry && host._windowsAdapter._activeGroup(entry.group);
            });
        }
        const entry = host._entryIds.get(app.get_id());
        return entry && host._windowsAdapter._activeGroup(entry.group);
    }

    _windows(group, entry = null) {
        if (this.snapshot) {
            if (entry) return [...(this.snapshot.get(entry) || [])];
            const result = [];
            for (const [member,windows] of this.snapshot) if (member.group === group) result.push(...windows);
            return result;
        }
        const host = this.host;
        const result = new Set();
        for (const actor of global.get_window_actors()) {
            const window = actor.meta_window;
            if (!window || window.skip_taskbar)
                continue;
            const member = host._windowsAdapter._entryForWindow(window);
            if (member?.group === group && (!entry || member === entry))
                result.add(window);
        }
        return [...result];
    }

    _activateEntry(entry, newInstance = false) {
        const host = this.host;
        const windows = host._windowsAdapter._windows(entry.group, entry).sort(
            (a, b) => b.get_user_time() - a.get_user_time());
        const decision = activation(windows.map(window => ({active:window.has_focus(),minimized:window.minimized})),newInstance);
        if (decision.action !== 'launch') {
            if (decision.action === 'minimize') windows[decision.index].minimize();
            else Main.activateWindow(windows[decision.index]);
            return;
        }
        const info = GioUnix.DesktopAppInfo.new(entry.desktop);
        if (info) {
            try {
                info.launch([], global.create_app_launch_context(0, -1));
            } catch (error) {
                Main.notifyError(_('Could not open %s').replace('%s', entry.label.replaceAll('\n', ' ')), error.message);
            }
        }
    }

    _cycleEntry(entry, direction) {
        const windows = this._windows(entry.group,entry);
        const index = cycleWindow(windows.map(window => ({active:window.has_focus()})),direction);
        if (index >= 0) Main.activateWindow(windows[index]);
    }
}
