// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gettext from 'gettext';
import {AppMenu} from 'resource:///org/gnome/shell/ui/appMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const APPLICATION_ID = 'io.github.hawkab.UbuntuDockFolders.desktop';
const detailsLabel = Gettext.domain('gnome-shell').gettext('App Details');

/** Open the package's software card for virtual folder launchers. */
export class FolderDetails {
    constructor(host) {
        this.host = host;
        this.items = new Map();
        this.icons = new Map();
    }

    async open() {
        try {
            const bus = await Gio.DBus.get(Gio.BusType.SESSION, null);
            const arguments_ = new GLib.Variant('(ss)', [APPLICATION_ID, '']);
            await bus.call('org.gnome.Software', '/org/gnome/Software',
                'org.gtk.Actions', 'Activate',
                new GLib.Variant('(sava{sv})', ['details', [arguments_], {}]),
                null, Gio.DBusCallFlags.NONE, -1, null);
            Main.overview.hide();
        } catch (error) {
            logError(error, 'Unable to open Ubuntu Dock Folders details');
        }
    }

    _isFolder(app) {
        return this.host._settings.get_boolean('enabled') && Object.values(this.host._groups)
            .some(group => group.desktopId === app?.get_id());
    }

    _bind(menu, item) {
        if (!item || this.items.has(item))
            return;
        const activate = item.activate;
        const destroy = item.connect('destroy', () => this.items.delete(item));
        this.items.set(item, {activate, destroy});
        item.activate = () => {
            menu.close();
            this.open();
        };
    }

    _restore(item) {
        const saved = this.items.get(item);
        if (!saved)
            return;
        item.activate = saved.activate;
        item.disconnect(saved.destroy);
        this.items.delete(item);
    }

    decorateDockIcon(icon) {
        const popup = icon.popupMenu;
        const destroy = icon.connect('destroy', () => this.icons.delete(icon));
        this.icons.set(icon, {popup, destroy});
        icon.popupMenu = (...args) => {
            const result = popup.apply(icon, args);
            const menu = icon._menu;
            const item = menu?._getMenuItems().find(candidate => candidate.label?.text === detailsLabel);
            this._bind(menu, item);
            return result;
        };
    }

    install() {
        const adapter = this;
        this.originalSetApp = AppMenu.prototype.setApp;
        AppMenu.prototype.setApp = function (...args) {
            const result = adapter.originalSetApp.apply(this, args);
            if (adapter._isFolder(this._app))
                adapter._bind(this, this._detailsItem);
            else
                adapter._restore(this._detailsItem);
            return result;
        };
    }

    uninstall() {
        if (this.originalSetApp)
            AppMenu.prototype.setApp = this.originalSetApp;
        for (const item of this.items.keys())
            this._restore(item);
        for (const [icon, {popup, destroy}] of this.icons) {
            icon.popupMenu = popup;
            icon.disconnect(destroy);
        }
        this.icons.clear();
        this.originalSetApp = null;
    }
}
