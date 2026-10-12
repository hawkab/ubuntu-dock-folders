// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
import {DockDash} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/dash.js';

/** Check window tracking, previews, reordering, and uninstalled PWA cleanup. */
export async function checkWindowBehavior({folders, key, helper, first, second, third, until, assert, record}) {
    await helper.CreateWindowAsync(420, 260, false, false, true, false);
    await helper.WaitWindowsAsync();
    await until(() => folders._windowsAdapter._windows(record.group).length === 1,
        'Test window was not assigned to the folder');
    const window = folders._windowsAdapter._windows(record.group)[0];
    const wmClass = window.get_wm_class();
    const client = GLib.getenv('DOCK_FOLDERS_TEST_BACKEND').split('/')[1];
    assert(window.get_client_type() === (client === 'x11' ? Meta.WindowClientType.X11 : Meta.WindowClientType.WAYLAND),
        `Test window uses the wrong client backend: ${client}`);
    await until(() => {
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        return record?.icon.running && record.icon.windowsCount === 1;
    },
        'Running indicator did not update');
    window.activate(global.get_current_time());
    await until(() => {
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        return global.display.focus_window === window && record?.icon.focused;
    }, 'Folder focus did not follow its application window');
    assert(record.dots.find(([entry]) => entry.desktop === first.desktop)[1].opacity === 255,
        'Application running dot is missing');
    assert(!folders._status().dockApps.includes(first.desktop), 'Grouped application reappeared on dock');

    let previousRecord = null;
    let stableFrames = 0;
    await until(() => {
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        stableFrames = record && record === previousRecord ? stableFrames + 1 : 0;
        previousRecord = record;
        return stableFrames >= 15 && !folders._timer && !folders._configTimer;
    }, 'Dock did not settle after indexing the new window', 5000);
    folders._openGroup(key);
    await Scripting.sleep(400);
    record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    if (!record.menu.isOpen) {
        folders._openGroup(key);
        await Scripting.sleep(400);
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    }
    const button = record.tiles.get(first.desktop);
    await until(() => button.mapped && record.menu.actor.mapped && !record.menu._timeline,
        'Folder tile did not map before window preview');
    button.grab_key_focus();
    await until(() => button.has_key_focus(), 'Application tile did not receive keyboard focus');
    const previewContext = {destroyed: record.previews.destroyed, open: record.menu.isOpen,
        mapped: button.mapped, windows: record.previews.getWindows(record.group.apps.find(entry => entry.desktop === first.desktop)).length};
    record.previews._open(button, record.group.apps.find(entry => entry.desktop === first.desktop), true);
    await Scripting.sleep(250);
    assert(record.previews.popup?.isOpen, `Window preview did not open: ${JSON.stringify(previewContext)}; ` +
        `destroyed=${record.previews.destroyed}, menuOpen=${record.menu.isOpen}, mapped=${button.mapped}, focus=${button.has_key_focus()}`);
    assert(record.previews.section._getMenuItems().length === 1, 'Window thumbnail is missing');
    const box = record.previews.section.box;
    assert('orientation' in box ? box.orientation === Clutter.Orientation.HORIZONTAL : !box.vertical,
        'Window previews are not horizontal');
    record.previews.clear();

    const menu = record.menu;
    folders._commands._moveEntry(record.group.apps.find(entry => entry.desktop === first.desktop), key, second.desktop);
    await Scripting.sleep(300);
    assert([...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped)?.menu === menu && menu.isOpen,
        'Reordering replaced or closed the folder');
    assert(record.group.apps[0].desktop === first.desktop, 'Reordering did not update application order');
    assert(record.undo.visible, 'Undo button did not appear');
    assert(folders._commands._undoLastMove(), 'Undo did not restore the order');
    await Scripting.sleep(400);
    folders._commands._moveEntry(third, key);
    await until(() => [...folders._icons.values()].some(item => item.group.key === key && item.tiles.size === 3),
        'Adding application did not update tiles');
    folders._commands._extractEntry(third.desktop, true);
    await until(() => folders._status().dockApps.includes(third.desktop), 'Extracted application was not pinned');
    const extracted = folders._dock._docks()[0].dash.getAppIcons().find(icon => icon.app.get_id() === third.desktop);
    assert(extracted && !folders._icons.has(extracted), 'Extracted application retained folder decoration');

    const pwa = {desktop: 'local.test.PWA.desktop', label: 'Test PWA'};
    const file = Gio.File.new_for_path(`${GLib.get_user_data_dir()}/applications/${pwa.desktop}`);
    for (let attempt = 0; attempt < 3; attempt++) {
        GLib.file_set_contents(file.get_path(), '[Desktop Entry]\nType=Application\nName=Test PWA\nExec=/bin/true\nIcon=utilities-terminal\n');
        await until(() => folders._appSystem.lookup_app(pwa.desktop), 'PWA installation was not detected', 10000);
        folders._commands._moveEntry(pwa, key);
        await until(() => [...folders._icons.values()].some(item => item.group.key === key && item.tiles.size === 3),
            'PWA was not added to its folder');
        record = [...folders._icons.values()].find(item => item.group.key === key);
        if (attempt === 1) {
            folders._openGroup(key);
            await Scripting.sleep(400);
        }
        const staleButton = record.tiles.get(pwa.desktop);
        const staleEntry = record.group.apps.find(entry => entry.desktop === pwa.desktop);
        folders._dragging = attempt === 2;
        file.delete(null);
        await until(() => !folders._groups[key].apps.some(entry => entry.desktop === pwa.desktop),
            'Uninstalled PWA remained in its folder', 10000);
        if (folders._dragging) {
            const dragIcon = staleButton.getDragActor();
            assert(dragIcon.icon_name === 'application-x-executable', 'Uninstalled PWA drag icon failed');
            dragIcon.destroy();
            folders._commands._moveEntry(staleEntry, key);
            assert(!folders._groups[key].apps.some(entry => entry.desktop === pwa.desktop),
                'Dragging restored an uninstalled application');
        }
        folders._dragging = false;
        await until(() => [...folders._icons.values()].some(item => item.group.key === key && item.tiles.size === 2),
            'Uninstalling a PWA did not refresh its folder');
        assert(!folders._undo, 'Undo could restore the uninstalled application');
        assert(folders._icons.size === 1, 'Uninstalling leaked folder icons');
    }
    await Scripting.sleep(1000);
    const redisplayNow = DockDash.prototype._redisplay;
    let idleRedisplays = 0;
    DockDash.prototype._redisplay = function (...args) {
        idleRedisplays++;
        return redisplayNow.apply(this, args);
    };
    try {
        await Scripting.sleep(1000);
        assert(idleRedisplays <= 2, `Idle dock kept rebuilding: ${idleRedisplays} times`);
    } finally {
        DockDash.prototype._redisplay = redisplayNow;
    }

    await Scripting.destroyTestWindows();
    await until(() => [...folders._icons.values()].every(item => !item.icon.running),
        'Running indicator was retained after closing the window');
    return wmClass;
}
