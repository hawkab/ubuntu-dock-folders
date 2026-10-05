// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';
import Meta from 'gi://Meta';

import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import {FolderRenderer} from './rendering.js';
import {FlowEffect} from './effects.js';
import {AppGridFolders} from './gridFolders.js';
import {FolderMenuManager, WindowPreviews} from './windowPreviews.js';
import {moveEntry, pruneGroups, quoteDesktopArgument} from './model.js';
import {createBoxLayout} from './compat.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as DND from 'resource:///org/gnome/shell/ui/dnd.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import * as Dash from 'resource:///org/gnome/shell/ui/dash.js';
import {DockManager} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/docking.js';
import {DockDash} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/dash.js';

const DBUS_XML = `<node><interface name="local.groups.Dock">
<method name="OpenGroup"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="Status"><arg type="s" direction="out"/></method>
<method name="Undo"><arg type="b" direction="out"/></method>
</interface></node>`;

// Manage dock grouping, drag-and-drop, folder menus, and extension lifecycle.
export default class DockGroups extends FolderRenderer {
    enable() {
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
        this._data = GLib.build_filenamev([GLib.get_user_data_dir(), 'launcher-groups']);
        const repair = '/usr/share/ubuntu-dock-folders/scripts/manage.py';
        if (!Gio.File.new_for_path(`${this._data}/ubuntu-settings`).query_exists(null) &&
            Gio.File.new_for_path(repair).query_exists(null)) {
            Gio.Subprocess.new(['/usr/bin/python3', repair, 'repair-settings'],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        }
        this._configTimer = 0;
        this._dragging = false;
        this._dropIcons = new Set();
        this._extractTargets = [];
        this._folderApps = new Map();
        this._readGroups();
        this._customization = this._settings.get_boolean('customization');
        this._appSystem = Shell.AppSystem.get_default();
        this._settingsButtons = new Map();
        this._refreshSettingsLauncher();
        this._tracker = Shell.WindowTracker.get_default();
        this._getRunning = this._appSystem.get_running.bind(this._appSystem);
        this._icons = new Map();
        this._signals = [];
        this._timer = 0;
        this._indexGroups();
        this._dockLayout = this._groupLayout();
        this._grid = new AppGridFolders(this._settings, (groups, favorites) => this._commitGroups(groups, favorites));
        this._readGroups();
        this._indexGroups();
        this._groupingEnabled = this._settings.get_boolean('enabled');
        this._syncDesktopFiles();
        this._syncFavorites(this._groupingEnabled);

        const extension = this;
        this._originalRedisplay = DockDash.prototype._redisplay;
        this._originalCreate = DockDash.prototype._createAppItem;
        DockDash.prototype._redisplay = function (...args) {
            const originalGetRunning = this._appSystem.get_running;
            this._appSystem.get_running = () => extension._getRunning().filter(
                app => !extension._isHidden(app));
            try {
                return extension._withFavorites(() => extension._originalRedisplay.apply(this, args));
            } finally {
                this._appSystem.get_running = originalGetRunning;
            }
        };
        DockDash.prototype._createAppItem = function (app) {
            const item = extension._originalCreate.call(this, app);
            const group = Object.values(extension._groups).find(
                candidate => candidate.desktopId === app.get_id());
            if (extension._settings.get_boolean('enabled')) {
                extension._decorateDrop(item.child, group, this);
                if (group)
                    extension._decorate(item.child, group, this);
            }
            return item;
        };

        this._originalAcceptDrop = DockDash.prototype.acceptDrop;
        this._originalAppFromSource = Dash.Dash.getAppFromSource;
        Dash.Dash.getAppFromSource = source => source?.groupEntry
            ? extension._appSystem.lookup_app(source.groupEntry.desktop)
            : extension._originalAppFromSource(source);
        this._originalDragMotion = DockDash.prototype._onItemDragMotion;
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
            const accepted = extension._withFavorites(() => extension._originalAcceptDrop.call(this, source, ...args));
            if (accepted && source?.groupEntry && extension._settings.get_boolean('enabled'))
                extension._extractEntry(source.groupEntry.desktop, !positioning);
            return accepted;
        };
        this._connect(this._settings, 'changed', (_settings, key) => {
            if (!['animation', 'initialized'].includes(key))
                this._queueConfig();
        });
        this._connect(this._appSystem, 'installed-changed', () => {
            this._grid?.pull();
            this._refreshSettingsLauncher();
            this._queueUpdate();
        });
        this._connect(Main.overview, 'item-drag-end', () => this._clearDropHighlight());
        this._connect(Main.overview, 'item-drag-cancelled', () => this._clearDropHighlight());
        this._connect(this._appSystem, 'app-state-changed', () => this._queueUpdate());
        this._connect(this._tracker, 'tracked-windows-changed', () => this._queueUpdate());
        this._connect(this._tracker, 'notify::focus-app', () => this._queueUpdate());
        this._connect(global.display, 'window-created', () => this._queueUpdate());
        this._connect(global.display, 'notify::focus-window', () => this._queueUpdate());
        this._connect(AppFavorites.getAppFavorites(), 'changed', () => this._queueUpdate());
        this._connect(Main.layoutManager, 'monitors-changed', () => this._queueUpdate());
        this._connect(Main.overview, 'showing', () => this._closeMenus());
        this._connect(Main.extensionManager, 'extension-state-changed', () => this._queueUpdate());
        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_XML, {
            OpenGroup: key => this._openGroup(key),
            Status: () => JSON.stringify(this._status()),
            Undo: () => this._undoLastMove(),
        });
        this._dbus.export(Gio.DBus.session, '/local/groups/Dock');
        this._rebuildDocks();
        this._queueUpdate();
    }

    disable() {
        this._enabled = false;
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
        this._removeExtractTargets();
        for (const [object, id] of this._signals ?? [])
            object.disconnect(id);
        this._signals = [];
        for (const [button, original] of this._settingsButtons ?? [])
            button._settingsApp = original;
        this._settingsButtons?.clear();
        if (this._originalRedisplay)
            DockDash.prototype._redisplay = this._originalRedisplay;
        if (this._originalCreate)
            DockDash.prototype._createAppItem = this._originalCreate;
        if (this._originalAcceptDrop)
            DockDash.prototype.acceptDrop = this._originalAcceptDrop;
        if (this._originalAppFromSource)
            Dash.Dash.getAppFromSource = this._originalAppFromSource;
        if (this._originalDragMotion)
            DockDash.prototype._onItemDragMotion = this._originalDragMotion;
        this._rebuildDocks();
        for (const record of this._icons?.values() ?? [])
            record.menu.destroy();
        this._icons?.clear();
        this._originalRedisplay = null;
        this._originalCreate = null;
        this._originalAcceptDrop = null;
        this._originalAppFromSource = null;
        this._originalDragMotion = null;
        this._settings = null;
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

    _readGroups() {
        const previous = this._groups ?? {};
        this._groups = JSON.parse(this._settings.get_string('groups'));
        if (!this._settings.get_boolean('initialized') && Object.keys(this._groups).length === 0) {
            const [, bytes] = GLib.file_get_contents(`${this.path}/groups.json`);
            this._groups = JSON.parse(new TextDecoder().decode(bytes));
            this._settings.set_string('groups', JSON.stringify(this._groups));
        }
        for (const [key, current] of Object.entries(this._groups)) {
            const old = previous[key];
            if (!old || old.id !== current.id)
                continue;
            const apps = current.apps.map(entry => {
                const existing = old.apps.find(app => app.desktop === entry.desktop);
                return existing ? Object.assign(existing, entry) : entry;
            });
            for (const field of Object.keys(old))
                delete old[field];
            Object.assign(old, current, {apps});
            this._groups[key] = old;
        }
        this._settings.set_boolean('initialized', true);
    }

    _groupLayout() {
        return JSON.stringify(Object.entries(this._groups).map(([key, group]) =>
            [key, group.id, group.apps.map(entry => entry.desktop).sort()]).sort());
    }

    _favoriteMap(original) {
        const map = {};
        for (const id of global.settings.get_strv('favorite-apps')) {
            let app = original[id];
            if (!app && Object.values(this._groups).some(group => `${group.id}.desktop` === id)) {
                app = this._appSystem.lookup_app(id) ?? this._folderApps.get(id);
                if (!app) {
                    const info = GioUnix.DesktopAppInfo.new_from_filename(
                        `${GLib.get_user_data_dir()}/applications/${id}`);
                    if (info) {
                        app = new Shell.App({app_info: info});
                        this._folderApps.set(id, app);
                    }
                }
            }
            if (app)
                map[id] = app;
        }
        return map;
    }

    _withFavorites(callback) {
        const favorites = AppFavorites.getAppFavorites();
        const getMap = favorites.getFavoriteMap;
        const getList = favorites.getFavorites;
        const map = this._favoriteMap(getMap.call(favorites));
        favorites.getFavoriteMap = () => map;
        favorites.getFavorites = () => Object.values(map);
        try {
            return callback();
        } finally {
            favorites.getFavoriteMap = getMap;
            favorites.getFavorites = getList;
        }
    }

    _indexGroups() {
        this._entryIds = new Map();
        this._classes = new Map();
        for (const [key, group] of Object.entries(this._groups)) {
            Object.defineProperty(group, 'key', {value: key, configurable: true});
            Object.defineProperty(group, 'desktopId', {value: `${group.id}.desktop`, configurable: true});
            for (const entry of group.apps) {
                Object.defineProperty(entry, 'group', {value: group, configurable: true});
                for (const id of [entry.desktop, ...(entry.aliases ?? [])])
                    this._entryIds.set(id, entry);
                const wmClass = GioUnix.DesktopAppInfo.new(entry.desktop)?.get_startup_wm_class();
                for (const cls of [...(entry.wmClasses ?? []), ...(wmClass ? [wmClass] : [])])
                    this._classes.set(cls.toLowerCase(), entry);
            }
        }
    }

    _queueConfig() {
        if (!this._enabled || this._configTimer)
            return;
        this._configTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 180, () => {
            if (this._dragging)
                return GLib.SOURCE_CONTINUE;
            this._configTimer = 0;
            const open = [...this._icons.values()].find(record => record.menu.isOpen)?.group.key;
            const layout = this._dockLayout;
            this._readGroups();
            this._grid?.push(this._groups);
            this._indexGroups();
            this._syncDesktopFiles();
            this._dockLayout = this._groupLayout();
            const enabled = this._settings.get_boolean('enabled');
            const customization = this._settings.get_boolean('customization');
            const refresh = enabled === this._groupingEnabled &&
                customization === this._customization && layout === this._dockLayout;
            if (enabled !== this._groupingEnabled) {
                this._syncFavorites(enabled);
                this._groupingEnabled = enabled;
            }
            this._customization = customization;
            if (refresh) {
                for (const record of this._icons.values())
                    this._refreshFolder(record);
                this._queueUpdate();
                return GLib.SOURCE_REMOVE;
            }
            AppFavorites.getAppFavorites().reload();
            this._clearDockTimeouts();
            for (const dock of this._docks())
                dock.dash.resetAppIcons();
            this._queueUpdate();
            if (open && enabled)
                this._openGroup(open);
            return GLib.SOURCE_REMOVE;
        });
    }

    _syncFavorites(enabled) {
        const favorites = global.settings.get_strv('favorite-apps');
        const result = [];
        for (const id of favorites) {
            const group = Object.values(this._groups).find(candidate => candidate.desktopId === id);
            if (!enabled && group)
                result.push(...group.apps.map(entry => entry.desktop));
            else if (enabled)
                result.push(this._entryIds.get(id)?.group.desktopId ?? id);
            else
                result.push(id);
        }
        const unique = [...new Set(result)];
        if (JSON.stringify(unique) !== JSON.stringify(favorites))
            global.settings.set_strv('favorite-apps', unique);
    }

    _syncDesktopFiles() {
        const directory = GLib.build_filenamev([GLib.get_user_data_dir(), 'applications']);
        GLib.mkdir_with_parents(directory, 0o755);
        GLib.mkdir_with_parents(this._data, 0o700);
        const registry = Gio.File.new_for_path(`${this._data}/group-desktops.json`);
        const previous = registry.query_exists(null)
            ? JSON.parse(new TextDecoder().decode(registry.load_contents(null)[1])) : [];
        const currentIds = Object.values(this._groups).map(group => `${group.id}.desktop`);
        for (const [key, group] of Object.entries(this._groups)) {
            if (!/^local\.groups\.[A-Za-z0-9_-]+$/.test(group.id))
                throw new Error('Invalid group desktop ID');
            const cleanName = group.name.replaceAll('\n', ' ').replaceAll('\r', ' ');
            const launcher = quoteDesktopArgument(`${this.path}/app/launcher.py`);
            const actions = group.apps.map((entry, i) => `\n[Desktop Action App${i}]\nName=${entry.label.replace(/[\r\n]/g, ' ')}\nExec=/usr/bin/gtk-launch ${quoteDesktopArgument(entry.desktop)}\n`).join('');
            const contents = `[Desktop Entry]\nType=Application\nName=${cleanName}\nComment=${_('Choose an application')}\nExec=/usr/bin/python3 ${launcher} ${quoteDesktopArgument(key)}\nIcon=${group.icon}\nTerminal=false\nStartupNotify=true\nCategories=Utility;\nActions=${group.apps.map((_, i) => `App${i}`).join(';')};\n${actions}`;
            const path = `${directory}/${group.id}.desktop`;
            const file = Gio.File.new_for_path(path);
            let old = '';
            if (file.query_exists(null))
                old = new TextDecoder().decode(file.load_contents(null)[1]);
            if (old !== contents)
                file.replace_contents(new TextEncoder().encode(contents), null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
            const statePath = `${this._data}/state.json`;
            const stateFile = Gio.File.new_for_path(statePath);
            if (stateFile.query_exists(null)) {
                const state = JSON.parse(new TextDecoder().decode(stateFile.load_contents(null)[1]));
                if (!state.created_files.includes(path)) {
                    state.created_files.push(path);
                    GLib.file_set_contents(statePath, JSON.stringify(state, null, 2));
                }
            }
        }
        for (const id of previous) {
            if (!/^local\.groups\.[A-Za-z0-9_-]+\.desktop$/.test(id) || currentIds.includes(id))
                continue;
            const file = Gio.File.new_for_path(`${directory}/${id}`);
            if (file.query_exists(null))
                file.delete(null);
        }
        const ids = JSON.stringify(currentIds);
        if (JSON.stringify(previous) !== ids)
            registry.replace_contents(new TextEncoder().encode(ids), null, false,
                Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        const statePath = `${this._data}/state.json`;
        if (GLib.file_test(statePath, GLib.FileTest.EXISTS)) {
            const [, bytes] = GLib.file_get_contents(statePath);
            const state = JSON.parse(new TextDecoder().decode(bytes));
            const current = new Set(Object.values(this._groups).map(group => `${directory}/${group.id}.desktop`));
            for (const path of state.created_files) {
                if (path.startsWith(`${directory}/local.groups.`) && path.endsWith('.desktop') && !current.has(path)) {
                    const file = Gio.File.new_for_path(path);
                    if (file.query_exists(null))
                        file.delete(null);
                }
            }
        }
    }

    _sourceEntry(source) {
        if (!source?.app || source.app.is_window_backed())
            return null;
        const id = source.app.get_id();
        if (id.startsWith('local.groups.'))
            return null;
        return this._entryIds.get(id) ?? {desktop: id, label: source.app.get_name()};
    }

    _decorateDrop(icon, group, dash) {
        this._dropIcons.add(icon);
        const canDrop = (source, x, y) => {
            const entry = this._sourceEntry(source);
            const vertical = [St.Side.LEFT, St.Side.RIGHT].includes(dash._position);
            const center = vertical ? y > icon.height * .22 && y < icon.height * .78 :
                x > icon.width * .22 && x < icon.width * .78;
            return entry && (group || !icon.app.get_id().startsWith('local.groups.')) &&
                entry.desktop !== icon.app.get_id() && source !== icon &&
                center;
        };
        icon.handleDragOver = (source, _actor, x, y) => {
            if (!canDrop(source, x, y)) {
                icon.remove_style_class_name('dock-group-drop-target');
                return DND.DragMotionResult.CONTINUE;
            }
            this._clearDropHighlight();
            icon.add_style_class_name('dock-group-drop-target');
            dash._clearDragPlaceholder();
            return DND.DragMotionResult.MOVE_DROP;
        };
        icon.acceptDrop = (source, _actor, x, y) => {
            if (!canDrop(source, x, y))
                return false;
            this._clearDropHighlight();
            const entry = this._sourceEntry(source);
            if (group)
                this._moveEntry(entry, group.key);
            else
                this._createGroup(entry, this._entryIds.get(icon.app.get_id()) ??
                    {desktop: icon.app.get_id(), label: icon.app.get_name()});
            return true;
        };
        icon.connect('destroy', () => this._dropIcons.delete(icon));
    }

    _clearDropHighlight() {
        for (const icon of this._dropIcons ?? [])
            icon.remove_style_class_name('dock-group-drop-target');
    }

    _makeTileDraggable(button, entry, menu, dash) {
        button.app = this._appSystem.lookup_app(entry.desktop);
        button.groupEntry = entry;
        button._delegate = button;
        button.getDragActor = () => button.app?.create_icon_texture(64) ??
            new St.Icon({gicon: GioUnix.DesktopAppInfo.new(entry.desktop)?.get_icon(), icon_size: 64});
        button.getDragActorSource = () => button.get_child().get_first_child();
        button.handleDragOver = source => {
            if (!this._sourceEntry(source) || source === button)
                return DND.DragMotionResult.CONTINUE;
            button.add_style_class_name('dock-group-drop-target');
            return DND.DragMotionResult.MOVE_DROP;
        };
        button.acceptDrop = (source, _actor, x) => {
            const member = this._sourceEntry(source);
            if (!member || source === button)
                return false;
            const apps = entry.group.apps;
            const next = apps[apps.indexOf(entry) + 1]?.desktop;
            this._moveEntry(member, entry.group.key, x > button.width / 2 ? next : entry.desktop);
            return true;
        };
        const draggable = DND.makeDraggable(button, {dragActorMaxSize: 64, dragActorOpacity: 220});
        button._draggable = draggable;
        draggable.connect('drag-begin', () => {
            this._dragging = true;
            for (const record of this._icons.values())
                record.previews.clear();
            button.opacity = 90;
            Main.overview.beginItemDrag(button);
            this._createExtractTargets(menu, dash);
        });
        draggable.connect('drag-end', () => {
            this._dragging = false;
            button.opacity = 255;
            this._removeExtractTargets();
            this._clearDropHighlight();
            Main.overview.endItemDrag(button);
            if (this._configTimer)
                return;
            for (const child of button.get_parent().get_children())
                child.remove_style_class_name('dock-group-drop-target');
        });
        draggable.connect('drag-cancelled', () => this._removeExtractTargets());
    }

    _createExtractTargets(menu, dash) {
        this._removeExtractTargets();
        const layer = menu.actor.get_parent();
        const dockPoint = (x, y) => {
            const [lx, ly] = layer.get_transformed_position();
            const [dx, dy] = dash.get_transformed_position();
            const [width, height] = dash.get_transformed_size();
            const local = [x + lx - dx, y + ly - dy];
            return local[0] >= 0 && local[0] < width && local[1] >= 0 && local[1] < height
                ? local : null;
        };
        layer._delegate = {
            handleDragOver: (source, actor, x, y, time) => {
                const point = dockPoint(x, y);
                return point ? dash.handleDragOver(source, actor, ...point, time)
                    : DND.DragMotionResult.CONTINUE;
            },
            acceptDrop: (source, actor, x, y, time) => {
                const point = dockPoint(x, y);
                return Boolean(point && dash.acceptDrop(source, actor, ...point, time));
            },
        };
        this._extractLayer = layer;
        for (const monitor of Main.layoutManager.monitors) {
            const rect = {x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height};
            const reserve = dash.iconSize + 32;
            if (dash._position === St.Side.LEFT) { rect.x += reserve; rect.width -= reserve; }
            else if (dash._position === St.Side.RIGHT) rect.width -= reserve;
            else if (dash._position === St.Side.TOP) { rect.y += reserve; rect.height -= reserve; }
            else rect.height -= reserve;
            const actor = new St.Widget({...rect, reactive: true});
            actor._delegate = {
                handleDragOver: source => source?.groupEntry ? DND.DragMotionResult.MOVE_DROP : DND.DragMotionResult.CONTINUE,
                acceptDrop: source => {
                    if (!source?.groupEntry)
                        return false;
                    this._extractEntry(source.groupEntry.desktop, true);
                    return true;
                },
            };
            layer.add_child(actor);
            layer.set_child_below_sibling(actor, menu.actor);
            this._extractTargets.push(actor);
        }
    }

    _removeExtractTargets() {
        if (this._extractLayer)
            delete this._extractLayer._delegate;
        this._extractLayer = null;
        for (const actor of this._extractTargets ?? [])
            actor.destroy();
        this._extractTargets = [];
    }

    _editGroups(edit) {
        const groups = JSON.parse(this._settings.get_string('groups'));
        let favorites = global.settings.get_strv('favorite-apps');
        const before = {groups: JSON.parse(JSON.stringify(groups)), favorites: [...favorites]};
        edit(groups, favorites);
        pruneGroups(groups, favorites);
        favorites = [...new Set(favorites)];
        if (JSON.stringify(before) === JSON.stringify({groups, favorites}))
            return;
        this._undo = {before, after: {layout: this._membership(groups), favorites}};
        this._commitGroups(groups, favorites);
        this._notification?.destroy();
        const source = MessageTray.getSystemSource();
        const notification = new MessageTray.Notification({source, title: _('Dock folders'),
            body: _('Folder updated'), isTransient: true});
        notification.addAction(_('Undo'), () => this._undoLastMove());
        this._notification = notification;
        notification.connect('destroy', () => {
            if (this._notification === notification)
                this._notification = null;
        });
        source.addNotification(notification);
    }

    _membership(groups) {
        return JSON.stringify(Object.entries(groups).map(([key, group]) =>
            [key, group.id, group.gridFolder ?? null, group.apps.map(entry => entry.desktop)]).sort());
    }

    _undoLastMove() {
        if (!this._undo)
            return false;
        const {before, after} = this._undo;
        const current = JSON.parse(this._settings.get_string('groups'));
        this._undo = null;
        if (this._membership(current) !== after.layout ||
            JSON.stringify(global.settings.get_strv('favorite-apps')) !== JSON.stringify(after.favorites))
            return false;
        this._closeMenus();
        const restored = Object.fromEntries(Object.entries(before.groups).map(([key, group]) =>
            [key, {...group, ...current[key], apps: group.apps}]));
        this._commitGroups(restored, before.favorites);
        this._notification?.destroy();
        return true;
    }

    _commitGroups(groups, favorites) {
        this._settings.set_string('groups', JSON.stringify(groups));
        this._readGroups();
        this._indexGroups();
        this._syncDesktopFiles();
        global.settings.set_strv('favorite-apps', favorites);
    }

    _moveEntry(entry, key, before = null) {
        if (entry.group?.key !== key)
            this._closeMenus();
        this._editGroups((groups, favorites) => moveEntry(groups, favorites, entry, key, before));
    }

    _createGroup(source, target) {
        if (source.desktop === target.desktop)
            return;
        this._editGroups((groups, favorites) => {
            const suffix = GLib.uuid_string_random().replaceAll('-', '').slice(0, 12);
            const key = `folder-${suffix}`;
            const id = `local.groups.Folder_${suffix}`;
            groups[key] = {id, name: _('New Folder'), icon: 'folder', colors: ['#3584e4', '#62a0ea'],
                apps: [target, source].map(entry => JSON.parse(JSON.stringify(entry)))};
            for (const [other, group] of Object.entries(groups)) {
                if (other !== key)
                    group.apps = group.apps.filter(entry => ![source.desktop, target.desktop].includes(entry.desktop));
            }
            let pos = favorites.indexOf(target.desktop);
            if (pos < 0)
                pos = favorites.length;
            favorites.splice(pos, 0, `${id}.desktop`);
            for (let i = favorites.length - 1; i >= 0; i--) {
                if ([source.desktop, target.desktop, ...(source.aliases ?? []), ...(target.aliases ?? [])].includes(favorites[i]))
                    favorites.splice(i, 1);
            }
        });
    }

    _extractEntry(id, pin) {
        this._closeMenus();
        this._editGroups((groups, favorites) => {
            for (const group of Object.values(groups)) {
                if (!group.apps.some(entry => entry.desktop === id))
                    continue;
                group.apps = group.apps.filter(entry => entry.desktop !== id);
                if (pin && !favorites.includes(id)) {
                    const pos = favorites.indexOf(`${group.id}.desktop`);
                    favorites.splice(pos < 0 ? favorites.length : pos + 1, 0, id);
                }
            }
        });
    }

    _docks() {
        return DockManager.getDefault()?._allDocks ?? [];
    }

    _rebuildDocks() {
        const manager = DockManager.getDefault();
        if (manager) {
            this._clearDockTimeouts();
            manager._deleteDocks();
            manager._createDocks();
        }
    }

    _clearDockTimeouts() {
        for (const dock of this._docks()) {
            for (const property of ['_showLabelTimeoutId', '_resetHoverTimeoutId', '_ensureActorVisibilityTimeoutId']) {
                if (dock.dash[property])
                    GLib.source_remove(dock.dash[property]);
                dock.dash[property] = 0;
            }
        }
    }

    _activeGroup(group) {
        return this._settings.get_boolean('enabled') && DockManager.getDefault()?.settings.showFavorites &&
            global.settings.get_strv('favorite-apps').includes(group.desktopId);
    }

    _entryForWindow(window, app = null) {
        app ??= this._tracker.get_window_app(window);
        const identified = app ? this._entryIds.get(app.get_id()) : null;
        if (identified && !['google-chrome.desktop', 'chromium-gost.desktop'].includes(identified.desktop))
            return identified;
        for (const value of [window.get_wm_class_instance(), window.get_wm_class()]) {
            const entry = value ? this._classes.get(value.toLowerCase()) : null;
            if (entry)
                return entry;
        }
        return identified;
    }

    _isHidden(app) {
        const windows = app.get_windows().filter(window => !window.skip_taskbar);
        if (windows.length) {
            return windows.every(window => {
                const entry = this._entryForWindow(window, app);
                return entry && this._activeGroup(entry.group);
            });
        }
        const entry = this._entryIds.get(app.get_id());
        return entry && this._activeGroup(entry.group);
    }

    _windows(group, entry = null) {
        const result = new Set();
        for (const actor of global.get_window_actors()) {
            const window = actor.meta_window;
            if (!window || window.skip_taskbar)
                continue;
            const member = this._entryForWindow(window);
            if (member?.group === group && (!entry || member === entry))
                result.add(window);
        }
        return [...result];
    }

    _decorate(icon, group, dash) {
        icon.getWindows = () => this._windows(group);
        icon._updateRunningState = () => { icon.running = icon.windowsCount > 0; };
        icon._updateFocusState = () => {
            if (!this._enabled || !dash._scrollView?.get_stage())
                return;
            const window = global.display.focus_window;
            icon.focused = icon.mapped && icon.running &&
                Boolean(window && this._entryForWindow(window)?.group === group);
        };

        icon.icon.createIcon = size => this._folderIcon(group, size);
        icon.icon.update();
        icon.label?.set_text(group.name);
        icon.accessible_name = group.name;
        let dockLabel = null;
        if (this._settings.get_boolean('customization') && group.showLabel) {
            const label = new St.Label({text: group.name, style_class: 'dock-group-dock-label',
                style: `font-size: ${this._settings.get_double('font-size')}px;`,
                x_align: Clutter.ActorAlign.CENTER});
            label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            icon.icon._box.add_child(label);
            dockLabel = label;
        }
        const side = dash._position;
        const menu = new PopupMenu.PopupMenu(icon, 0.5, side);
        menu.actor.add_style_class_name('dock-group-popup');
        Main.uiGroup.add_child(menu.actor);
        menu.actor.hide();
        const previews = new WindowPreviews(menu, {
            getWindows: entry => this._windows(group, entry),
            isDragging: () => this._dragging,
            onUndo: () => this._undoLastMove(),
        });
        const manager = new FolderMenuManager(menu, previews);

        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const content = createBoxLayout(Clutter.Orientation.VERTICAL, {
            style_class: 'dock-group-content'});
        const header = new St.BoxLayout({style_class: 'dock-group-header'});
        const title = new St.Label({text: group.name, style_class: 'dock-group-title', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER});
        header.add_child(title);
        const undo = new St.Button({style_class: 'dock-group-gear', reactive: true, can_focus: true,
            accessible_name: _('Undo last move'), visible: Boolean(this._undo),
            child: new St.Icon({icon_name: 'edit-undo-symbolic', icon_size: 20})});
        undo.connect('clicked', () => this._undoLastMove());
        header.add_child(undo);
        if (this._settings.get_boolean('customization')) {
            const gear = new St.Button({style_class: 'dock-group-gear', reactive: true, can_focus: true,
                accessible_name: _('Folder settings'), child: new St.Icon({icon_name: 'emblem-system-symbolic', icon_size: 20})});
            gear.connect('clicked', () => {
                menu.close(BoxPointer.PopupAnimation.FULL);
                Gio.Subprocess.new(['/usr/bin/python3', `${this.path}/app/preferences.py`, group.key],
                    Gio.SubprocessFlags.NONE);
            });
            header.add_child(gear);
        }
        content.add_child(header);
        const row = new St.Widget({style_class: 'dock-group-apps',
            layout_manager: new Clutter.GridLayout({orientation: Clutter.Orientation.HORIZONTAL})});
        row.layout_manager.set_column_spacing(6);
        row.layout_manager.set_row_spacing(6);
        let index = 0;
        const dots = [];
        const tiles = new Map();
        for (const entry of group.apps) {
            const button = new St.Button({
                style_class: 'dock-group-tile', can_focus: true, reactive: true,
                accessible_name: entry.label.replaceAll('\n', ' '),
            });
            const tile = createBoxLayout(Clutter.Orientation.VERTICAL, {
                style_class: 'dock-group-tile-content'});
            const app = this._appSystem.lookup_app(entry.desktop);
            tile.add_child(app?.create_icon_texture(64) ?? new St.Icon({
                gicon: GioUnix.DesktopAppInfo.new(entry.desktop)?.get_icon(), icon_size: 64,
                x_align: Clutter.ActorAlign.CENTER,
            }));
            tile.add_child(new St.Label({
                text: entry.label, style_class: 'dock-group-app-label',
                x_align: Clutter.ActorAlign.CENTER,
            }));
            const dot = new St.Widget({
                style_class: 'dock-group-app-dot', x_align: Clutter.ActorAlign.CENTER,
                opacity: this._windows(group, entry).length ? 255 : 0,
            });
            dots.push([entry, dot]);
            tile.add_child(dot);
            button.set_child(tile);
            previews.bind(button, entry);
            button.connect('clicked', () => {
                menu.close(BoxPointer.PopupAnimation.FULL);
                this._activateEntry(entry);
            });
            this._makeTileDraggable(button, entry, menu, dash);
            tiles.set(entry.desktop, button);
            row.layout_manager.attach(button, index % 4, Math.floor(index / 4), 1, 1);
            index++;
        }
        content.add_child(row);
        item.add_child(content);
        menu.addMenuItem(item);
        menu.actor.connect('key-press-event', (_actor, event) => {
            if (event.get_key_symbol() === Clutter.KEY_z &&
                event.get_state() & Clutter.ModifierType.CONTROL_MASK && this._undoLastMove())
                return Clutter.EVENT_STOP;
            return Clutter.EVENT_PROPAGATE;
        });
        this._stylePopup(menu, group);
        const destroy = menu.destroy.bind(menu);
        menu.destroy = () => {
            if (menu._destroying)
                return;
            menu._destroying = true;
            this._stopAnimation(menu);
            menu._useGlass = false;
            this._syncGlass(menu);
            destroy();
        };
        const close = menu._boxPointer.close.bind(menu._boxPointer);
        menu._boxPointer.close = (animation, callback) => {
            if (menu._destroying) {
                menu.actor.hide();
                callback?.();
            } else if (animation === BoxPointer.PopupAnimation.NONE || !this._enabled) {
                this._stopAnimation(menu);
                close(BoxPointer.PopupAnimation.NONE, callback);
            } else {
                this._animate(menu, side, false, () => close(BoxPointer.PopupAnimation.NONE, () => {
                    this._syncGlass(menu);
                    callback?.();
                }));
            }
        };
        menu.connect('open-state-changed', (_menu, open) => {
            icon.emit('menu-state-changed', open);
            this._syncGlass(menu);
            if (open) {
                undo.visible = Boolean(this._undo);
                for (const [entry, dot] of dots)
                    dot.opacity = this._windows(group, entry).length ? 255 : 0;
            }
        });
        icon.activate = () => {
            if (menu.isOpen)
                menu.close(BoxPointer.PopupAnimation.FULL);
            else
                this._expand(menu, side);
        };
        const record = {icon, group, menu, dots, row, tiles, title, dockLabel, undo, previews, manager};
        this._icons.set(icon, record);
        icon.connect('notify::mapped', () => this._queueUpdate());
        icon.connect('destroy', () => {
            this._icons.delete(icon);
            this._stopAnimation(menu);
            menu.destroy();
        });
        this._queueUpdate();
    }

    _expand(menu, side) {
        this._closeMenus();
        this._stopAnimation(menu);
        menu.actor.set_scale(1, 1);
        menu.open(BoxPointer.PopupAnimation.NONE);
        this._animate(menu, side, true);
    }

    _animate(menu, side, opening, complete = null) {
        this._stopAnimation(menu);
        const actor = menu.actor;
        if (!St.Settings.get().enable_animations) {
            actor.set_scale(1, 1);
            actor.opacity = 255;
            complete?.();
            return;
        }
        const flow = this._settings.get_string('animation') === 'flow';
        const timeline = new Clutter.Timeline({duration: flow ? 300 : 220, actor});
        menu._timeline = timeline;
        actor.opacity = opening ? 0 : 255;
        if (flow) {
            actor.set_scale(1, 1);
            const effect = new FlowEffect(side);
            actor.add_effect_with_name('dock-group-flow', effect);
            menu._flowEffect = effect;
            effect.progress = opening ? 0 : 1;
            effect.invalidate();
            timeline.connect('new-frame', () => {
                this._positionGlass(menu);
                const origin = this._animationOrigin(menu);
                if (origin) {
                    effect.originX = origin.x;
                    effect.originY = origin.y;
                }
                const t = timeline.get_progress();
                const p = opening ? 1 - Math.pow(1 - t, 3) : 1 - t * t;
                effect.progress = p;
                actor.opacity = Math.round(255 * Math.min(1, p * 3));
                effect.invalidate();
            });
            timeline.connect('completed', () => {
                actor.remove_effect(effect);
                menu._flowEffect = null;
                menu._timeline = null;
                this._positionGlass(menu);
                complete?.();
            });
        } else {
            if (opening) {
                actor.set_scale(0.12, 0.12);
                actor.opacity = 0;
            }
            timeline.connect('new-frame', () => {
                this._positionGlass(menu);
                const origin = this._animationOrigin(menu);
                if (origin)
                    actor.set_pivot_point(origin.x / origin.width, origin.y / origin.height);
                const t = timeline.get_progress();
                const p = opening ? 1 - Math.pow(1 - t, 3) : 1 - t * t * t;
                actor.set_scale(.12 + .88 * p, .12 + .88 * p);
                actor.opacity = Math.round(255 * p);
            });
            timeline.connect('completed', () => {
                menu._timeline = null;
                this._positionGlass(menu);
                complete?.();
            });
        }
        timeline.start();
    }

    _animationOrigin(menu) {
        const source = menu.sourceActor.icon?.icon ?? menu.sourceActor;
        if (!source.mapped)
            return null;
        const box = menu.actor.get_allocation_box();
        const width = box.get_width();
        const height = box.get_height();
        if (![box.x1, box.y1, width, height].every(Number.isFinite) || width <= 0 || height <= 0)
            return null;
        const [x, y] = source.get_transformed_position();
        const [w, h] = source.get_transformed_size();
        const center = [x + w / 2, y + h / 2];
        if (![...center, w, h].every(Number.isFinite) || w <= 0 || h <= 0)
            return null;
        const [success, localX, localY] = menu.actor.get_parent().transform_stage_point(...center);
        if (!success || ![localX, localY].every(Number.isFinite))
            return null;
        const origin = {x: localX - box.x1, y: localY - box.y1, width, height, center};
        menu._origin = origin;
        return origin;
    }

    _stopAnimation(menu) {
        menu.actor.remove_all_transitions();
        menu._timeline?.stop();
        menu._timeline = null;
        if (menu._flowEffect)
            menu.actor.remove_effect(menu._flowEffect);
        menu._flowEffect = null;
    }

    _activateEntry(entry) {
        const windows = this._windows(entry.group, entry).sort(
            (a, b) => b.get_user_time() - a.get_user_time());
        if (windows.length) {
            Main.activateWindow(windows[0]);
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

    _closeMenus() {
        for (const {menu} of this._icons.values()) {
            if (menu.isOpen)
                menu.close(BoxPointer.PopupAnimation.FULL);
        }
    }

    _openGroup(key) {
        for (const {icon, group, menu} of this._icons.values()) {
            if (group.key === key && icon.mapped) {
                if (menu.isOpen)
                    menu.close(BoxPointer.PopupAnimation.FULL);
                else
                    this._expand(menu, menu._arrowSide);
                return true;
            }
        }
        return false;
    }

    _queueUpdate() {
        if (!this._enabled || this._timer)
            return;
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            this._timer = 0;
            if (this._undo && (this._membership(JSON.parse(this._settings.get_string('groups'))) !==
                this._undo.after.layout || JSON.stringify(global.settings.get_strv('favorite-apps')) !==
                JSON.stringify(this._undo.after.favorites))) {
                this._undo = null;
                this._notification?.destroy();
            }
            for (const record of this._icons.values()) {
                const {icon, dots, group} = record;
                icon._updateWindows();
                record.undo.visible = Boolean(this._undo);
                record.previews.update();
                for (const [entry, dot] of dots)
                    dot.opacity = this._windows(group, entry).length ? 255 : 0;
            }
            AppFavorites.getAppFavorites().reload();
            for (const dock of this._docks())
                dock.dash._redisplay();
            return GLib.SOURCE_REMOVE;
        });
    }

    _status() {
        return {
            enabled: this._settings.get_boolean('enabled'),
            customization: this._settings.get_boolean('customization'),
            glass: this._settings.get_boolean('glass'),
            animation: this._settings.get_string('animation'),
            fontSize: this._settings.get_double('font-size'),
            dragging: this._dragging,
            canUndo: Boolean(this._undo),
            groups: Object.fromEntries(Object.entries(this._groups).map(([key, group]) => [key, {
                name: group.name, apps: group.apps.map(entry => entry.desktop),
                windows: this._windows(group).length,
                icons: [...this._icons.values()].filter(record => record.group === group).map(
                    ({icon, menu}) => ({running: icon.running, count: icon.windowsCount,
                        focused: icon.focused, open: menu.isOpen,
                        position: icon.get_transformed_position(),
                        popupPosition: menu.actor.get_transformed_position(),
                        popupScale: [menu.actor.scale_x, menu.actor.scale_y],
                        origin: menu._origin ?? null,
                        flow: menu._flowEffect?.progress ?? null})),
            }])),
            hiddenApps: this._getRunning().filter(app => this._isHidden(app)).map(app => app.get_id()),
            dockApps: this._docks().flatMap(dock => dock.dash.getAppIcons().map(icon => icon.app.get_id())),
        };
    }
}
