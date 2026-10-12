// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {FolderRenderer} from './rendering.js';
import {AppGridFolders} from './gridFolders.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import {GroupStore} from './groupStore.js';
import {FolderCommands} from './folderCommands.js';
import {FolderFeedback} from './folderFeedback.js';
import {DockAdapter} from './dockAdapter.js';
import {DockDragDrop} from './dockDragDrop.js';
import {DockWindows} from './dockWindows.js';
import {FolderView} from './folderView.js';
import {FolderAnimation} from './folderAnimation.js';
import {canUndo} from './core/engine.js';
import {preferences} from './core/preferences.js';
import {verifyCore} from './adapters/dependency.js';
import {folderChanges} from './core/changes.js';

const DBUS_XML = `<node><interface name="local.groups.Dock">
<method name="OpenGroup"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="Status"><arg type="s" direction="out"/></method>
<method name="Undo"><arg type="b" direction="out"/></method>
</interface></node>`;

/** Connect folder use cases to the GNOME Shell lifecycle. */
export default class DockGroups extends FolderRenderer {
    enable() {
        verifyCore(this.dir.get_child('core'));
        this._store = new GroupStore(this);
        this._feedback = new FolderFeedback(this);
        this._commands = new FolderCommands(this, {
            isAvailable: id => GioUnix.DesktopAppInfo.new(id) !== null,
            makeSuffix: () => GLib.uuid_string_random().replaceAll('-', '').slice(0, 12),
            newFolderName: _('New Folder'), feedback: this._feedback,
            favorites: () => global.settings.get_strv('favorite-apps'),
        });
        this._dock = new DockAdapter(this);
        this._dnd = new DockDragDrop(this);
        this._windowsAdapter = new DockWindows(this);
        this._view = new FolderView(this);
        this._animation = new FolderAnimation(this);
        try {
            this._enable();
        } catch (error) {
            this.disable();
            throw error;
        }
    }

    _enable() {
        this._enabled = true;
        this._settings = this.getSettings('org.gnome.shell.extensions.dock-groups');
        this._preferencesCache = null;
        this._data = GLib.build_filenamev([GLib.get_user_data_dir(), 'launcher-groups']);
        const repair = '/usr/share/ubuntu-dock-folders/scripts/manage.py';
        if (!Gio.File.new_for_path(`${this._data}/ubuntu-settings`).query_exists(null) &&
            Gio.File.new_for_path(repair).query_exists(null)) {
            Gio.Subprocess.new(['/usr/bin/python3', repair, 'repair-settings'],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        }
        this._configTimer = 0;
        this._configKeys = new Set();
        this._dragging = false;
        this._dropIcons = new Set();
        this._extractTargets = [];
        this._folderApps = new Map();
        this._store._readGroups();
        this._customization = this._settings.get_boolean('customization');
        this._appSystem = Shell.AppSystem.get_default();
        this._settingsButtons = new Map();
        this._refreshSettingsLauncher();
        this._tracker = Shell.WindowTracker.get_default();
        this._getRunning = this._appSystem.get_running.bind(this._appSystem);
        this._icons = new Map();
        this._signals = [];
        this._timer = 0;
        this._store._reconcileInstalledApps();
        this._store._indexGroups();
        this._dockLayout = this._store._groupLayout();
        this._grid = new AppGridFolders(this._settings, (groups, favorites) => this._store._commitGroups(groups, favorites));
        this._store._readGroups();
        this._store._indexGroups();
        this._configGroups = JSON.parse(JSON.stringify(this._groups));
        this._groupingEnabled = this._settings.get_boolean('enabled');
        this._store._syncDesktopFiles();
        this._store._syncFavorites(this._groupingEnabled);

        this._dock.install();
        this._connect(this._settings, 'changed', (_settings, key) => {
            this._preferencesCache = null;
            if (!['animation', 'animation-speed', 'initialized'].includes(key))
                this._queueConfig(key);
        });
        this._connect(this._appSystem, 'installed-changed', () => {
            this._grid?.pull();
            this._store._reconcileInstalledApps();
            this._store._indexGroups(true);
            this._refreshSettingsLauncher();
            this._queueUpdate();
        });
        this._connect(Main.overview, 'item-drag-end', () => this._dnd._clearDropHighlight());
        this._connect(Main.overview, 'item-drag-cancelled', () => this._dnd._clearDropHighlight());
        this._connect(this._appSystem, 'app-state-changed', () => this._queueUpdate());
        this._connect(this._tracker, 'tracked-windows-changed', () => this._queueUpdate());
        this._connect(this._tracker, 'notify::focus-app', () => this._queueUpdate());
        this._connect(global.display, 'window-created', () => this._queueUpdate());
        this._connect(global.display, 'notify::focus-window', () => this._queueUpdate());
        this._connect(AppFavorites.getAppFavorites(), 'changed', () => this._queueUpdate());
        this._connect(Main.layoutManager, 'monitors-changed', () => this._queueUpdate());
        this._connect(Main.overview, 'showing', () => this._view._closeMenus());
        this._connect(Main.extensionManager, 'extension-state-changed', () => this._queueUpdate());
        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_XML, {
            OpenGroup: key => this._openGroup(key),
            Status: () => JSON.stringify(this._status()),
            Undo: () => this._commands._undoLastMove(),
        });
        this._dbus.export(Gio.DBus.session, '/local/groups/Dock');
        this._dock._rebuildDocks();
        this._queueUpdate();
    }

    disable() {
        this._enabled = false;
        this._pendingFolder = null;
        this._grid?.destroy();
        this._grid = null;
        this._undo = null;
        this._notification?.destroy();
        this._notification = null;
        this._dbus?.unexport();
        this._dbus = null;
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        if (this._configTimer)
            GLib.source_remove(this._configTimer);
        this._configTimer = 0;
        this._dnd._removeExtractTargets();
        for (const [object, id] of this._signals ?? [])
            object.disconnect(id);
        this._signals = [];
        for (const [button, original] of this._settingsButtons ?? [])
            button._settingsApp = original;
        this._settingsButtons?.clear();
        this._dock.uninstall();
        this._dock._rebuildDocks();
        for (const record of this._icons?.values() ?? [])
            record.menu.destroy();
        this._icons?.clear();
        this._settings = null;
        this._preferencesCache = null;
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _refreshSettingsLauncher() {
        const app = this._appSystem.lookup_app('org.gnome.Settings.desktop');
        if (!app)
            return;
        const system = Main.panel.statusArea.quickSettings?._system?._systemItem;
        for (const button of system?.child.get_children() ?? []) {
            if (!button._settingsApp)
                continue;
            if (!this._settingsButtons.has(button))
                this._settingsButtons.set(button, button._settingsApp);
            button._settingsApp = app;
        }
    }

    _queueConfig(key = 'groups') {
        this._configKeys.add(key);
        if (!this._enabled || this._configTimer)
            return;
        this._configTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 180, () => {
            if (this._dragging)
                return GLib.SOURCE_CONTINUE;
            this._configTimer = 0;
            const keys = this._configKeys;
            this._configKeys = new Set();
            const open = [...this._icons.values()].find(record => record.menu.isOpen || record.menu._pendingOpen)?.group.key;
            const layout = this._dockLayout;
            let changes;
            if (keys.has('groups')) {
                this._store._readGroups();
                changes = folderChanges(this._configGroups,this._groups);
                this._configGroups = JSON.parse(JSON.stringify(this._groups));
                if (changes.membership || changes.launchers) this._grid?.push(this._groups);
                if (changes.membership) this._store._indexGroups();
                if (changes.launchers) this._store._syncDesktopFiles();
                this._dockLayout = this._store._groupLayout();
            }
            const enabled = this._settings.get_boolean('enabled');
            const customization = this._settings.get_boolean('customization');
            const refresh = enabled === this._groupingEnabled &&
                customization === this._customization && layout === this._dockLayout;
            if (enabled !== this._groupingEnabled) {
                this._store._syncFavorites(enabled);
                this._groupingEnabled = enabled;
            }
            this._customization = customization;
            if (refresh) {
                const all = [...keys].some(name => name !== 'groups');
                for (const record of this._icons.values())
                    if (all || changes?.changed.includes(record.group.key)) this._refreshFolder(record);
                if (changes?.membership || keys.has('enabled')) this._queueUpdate();
                return GLib.SOURCE_REMOVE;
            }
            AppFavorites.getAppFavorites().reload();
            this._dock._clearDockTimeouts();
            for (const dock of this._dock._docks())
                dock.dash.resetAppIcons();
            this._queueUpdate();
            if (open && enabled)
                this._openGroup(open);
            return GLib.SOURCE_REMOVE;
        });
    }

    _openGroup(key) {
        return this._view.activate(key);
    }

    _queueUpdate() {
        if (!this._enabled || this._timer)
            return;
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            try {
                this._windowsAdapter.beginUpdate();
                if (this._undo && !canUndo({groups:JSON.parse(this._settings.get_string('groups')),
                    favorites:global.settings.get_strv('favorite-apps'),undo:this._undo})) {
                    this._undo = null;
                    this._notification?.destroy();
                }
                for (const dock of this._dock._docks())
                    dock.dash._redisplay();
                for (const record of this._icons.values()) {
                    const {icon, dots, group} = record;
                    if (!icon.mapped || !icon.get_stage())
                        continue;
                    icon._updateWindows();
                    record.undo.visible = Boolean(this._undo);
                    record.previews.update();
                    for (const [entry, dot] of dots)
                        dot.opacity = this._windowsAdapter._windows(group, entry).length ? 255 : 0;
                }
                if (this._pendingFolder) {
                    const key = this._pendingFolder;
                    const record = [...this._icons.values()].find(item => item.group.key === key && item.icon.mapped);
                    if (!this._settings.get_boolean('enabled') || !this._groups[key] || record?.menu.isOpen || record?.menu._pendingOpen) this._pendingFolder = null;
                    else if (record) this._openGroup(key);
                }
            } finally {
                this._windowsAdapter.endUpdate();
                this._timer = 0;
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _preferences() {
        return this._preferencesCache ??= preferences(item => this._settings.get_value(item.key).deep_unpack(), this._settings.get_boolean('glass'));
    }

    _status() {
        return {
            enabled: this._settings.get_boolean('enabled'),
            customization: this._settings.get_boolean('customization'),
            blurStrength: this._preferences().blurStrength,
            animation: this._settings.get_string('animation'),
            fontSize: this._settings.get_double('font-size'),
            dragging: this._dragging,
            canUndo: Boolean(this._undo),
            groups: Object.fromEntries(Object.entries(this._groups).map(([key, group]) => [key, {
                name: group.name, apps: group.apps.map(entry => entry.desktop),
                windows: this._windowsAdapter._windows(group).length,
                icons: [...this._icons.values()].filter(record => record.group === group).map(
                    ({icon, menu}) => ({running: icon.running, count: icon.windowsCount,
                        focused: icon.focused, open: menu.isOpen,
                        position: icon.get_transformed_position(),
                        popupPosition: menu.actor.get_transformed_position(),
                        popupScale: [menu.actor.scale_x, menu.actor.scale_y],
                        origin: menu._origin ?? null,
                        flow: menu._flowEffect?.progress ?? null})),
            }])),
            hiddenApps: this._getRunning().filter(app => this._windowsAdapter._isHidden(app)).map(app => app.get_id()),
            dockApps: this._dock._docks().flatMap(dock => dock.dash.getAppIcons().map(icon => icon.app.get_id())),
        };
    }
}
