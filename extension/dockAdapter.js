// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import * as Dash from 'resource:///org/gnome/shell/ui/dash.js';
import {DockManager} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/docking.js';
import {DockDash} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/dash.js';
import {FolderDetails} from './folderDetails.js';

/** Adapt Ubuntu Dock lifecycle, favorites, and application delegates. */
export class DockAdapter {
    constructor(host) {
        this.host = host;
        this.details = new FolderDetails(host);
    }

    _favoriteMap(original) {
        const host = this.host;
        const map = {};
        for (const id of global.settings.get_strv('favorite-apps')) {
            let app = original[id];
            if (!app && Object.values(host._groups).some(group => `${group.id}.desktop` === id)) {
                app = host._appSystem.lookup_app(id) ?? host._folderApps.get(id);
                if (!app) {
                    const info = GioUnix.DesktopAppInfo.new_from_filename(
                        `${GLib.get_user_data_dir()}/applications/${id}`);
                    if (info) {
                        app = new Shell.App({app_info: info});
                        host._folderApps.set(id, app);
                    }
                }
            }
            if (app)
                map[id] = app;
        }
        return map;
    }

    _withFavorites(callback) {
        const host = this.host;
        const favorites = AppFavorites.getAppFavorites();
        const getMap = favorites.getFavoriteMap;
        const getList = favorites.getFavorites;
        const map = host._dock._favoriteMap(getMap.call(favorites));
        favorites.getFavoriteMap = () => map;
        favorites.getFavorites = () => Object.values(map);
        try {
            return callback();
        } finally {
            favorites.getFavoriteMap = getMap;
            favorites.getFavorites = getList;
        }
    }

    _docks() {
        return DockManager.getDefault()?._allDocks ?? [];
    }

    _rebuildDocks() {
        const host = this.host;
        const manager = DockManager.getDefault();
        if (manager) {
            host._dock._clearDockTimeouts();
            manager._deleteDocks();
            manager._createDocks();
        }
    }

    _clearDockTimeouts() {
        const host = this.host;
        for (const dock of host._dock._docks()) {
            for (const property of ['_showLabelTimeoutId', '_resetHoverTimeoutId', '_ensureActorVisibilityTimeoutId']) {
                if (dock.dash[property])
                    GLib.source_remove(dock.dash[property]);
                dock.dash[property] = 0;
            }
        }
    }

    _decorateIcon(icon, dash) {
        const host = this.host;
        if (!host._settings.get_boolean('enabled') || host._dropIcons.has(icon))
            return;
        const group = Object.values(host._groups).find(
            candidate => candidate.desktopId === icon.app.get_id());
        host._dnd._decorateDrop(icon, group, dash);
        if (group)
            host._view._decorate(icon, group, dash);
    }

    /** Stack edited folder titles in the preferences icon's tooltip. */
    _decoratePreferences(item, app) {
        const tracked = new Set();
        item.label.clutter_text.set_single_line_mode(false);
        const update = () => {
            const windows = app.get_windows();
            const titles = [...new Set(windows.map(window => window.get_title()).filter(Boolean))];
            const label = titles.join('\n') || app.get_name();
            if (label !== item._labelText)
                item.setLabelText(label);
            for (const window of tracked) {
                if (!windows.includes(window)) {
                    window.disconnectObject(item);
                    tracked.delete(window);
                }
            }
            for (const window of windows) {
                if (!tracked.has(window)) {
                    window.connectObject('notify::title', update, item);
                    tracked.add(window);
                }
            }
        };
        app.connectObject('windows-changed', update, item);
        update();
    }

    install() {
        const host = this.host;
        const extension = host;
        this.details.install();
        host._originalRedisplay = DockDash.prototype._redisplay;
        host._originalCreate = DockDash.prototype._createAppItem;
        DockDash.prototype._redisplay = function (...args) {
            const originalGetRunning = this._appSystem.get_running;
            this._appSystem.get_running = () => extension._getRunning().filter(
                app => !extension._windowsAdapter._isHidden(app));
            try {
                const result = extension._dock._withFavorites(() => extension._originalRedisplay.apply(this, args));
                for (const icon of this.getAppIcons())
                    extension._dock._decorateIcon(icon, this);
                return result;
            } finally {
                this._appSystem.get_running = originalGetRunning;
            }
        };
        DockDash.prototype._createAppItem = function (app) {
            const item = extension._originalCreate.call(this, app);
            if (app.get_id() === 'io.github.hawkab.UbuntuDockFolders.desktop')
                extension._dock._decoratePreferences(item, app);
            try {
                extension._dock._decorateIcon(item.child, this);
            } catch (error) {
                item.destroy();
                throw error;
            }
            return item;
        };

        host._originalAcceptDrop = DockDash.prototype.acceptDrop;
        host._originalAppFromSource = Dash.Dash.getAppFromSource;
        Dash.Dash.getAppFromSource = source => source?.groupEntry
            ? extension._appSystem.lookup_app(source.groupEntry.desktop)
            : extension._originalAppFromSource(source);
        host._originalDragMotion = DockDash.prototype._onItemDragMotion;
        DockDash.prototype._onItemDragMotion = function (event) {
            if (event.source?.groupEntry && extension._extractLayer?.contains(event.targetActor)) {
                const [x, y] = this.get_transformed_position();
                const [width, height] = this.get_transformed_size();
                if (event.x >= x && event.x < x + width && event.y >= y && event.y < y + height)
                    event = {...event, targetActor: this._box};
            }
            return extension._originalDragMotion.call(this, event);
        };
        DockDash.prototype.acceptDrop = function (source, ...args) {
            const positioning = Boolean(this._dragPlaceholder);
            const accepted = extension._dock._withFavorites(() => extension._originalAcceptDrop.call(this, source, ...args));
            if (accepted && source?.groupEntry && extension._settings.get_boolean('enabled'))
                extension._commands._extractEntry(source.groupEntry.desktop, !positioning);
            return accepted;
        };
    }

    uninstall() {
        const host = this.host;
        this.details.uninstall();
        if (host._originalRedisplay)
            DockDash.prototype._redisplay = host._originalRedisplay;
        if (host._originalCreate)
            DockDash.prototype._createAppItem = host._originalCreate;
        if (host._originalAcceptDrop)
            DockDash.prototype.acceptDrop = host._originalAcceptDrop;
        if (host._originalAppFromSource)
            Dash.Dash.getAppFromSource = host._originalAppFromSource;
        if (host._originalDragMotion)
            DockDash.prototype._onItemDragMotion = host._originalDragMotion;
        host._originalRedisplay = null;
        host._originalCreate = null;
        host._originalAcceptDrop = null;
        host._originalAppFromSource = null;
        host._originalDragMotion = null;
    }
}
