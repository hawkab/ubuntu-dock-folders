// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
import {DockDash} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/dash.js';

function assert(value, message) {
    if (!value)
        throw new Error(message);
}

async function until(predicate, message) {
    for (let attempt = 0; attempt < 60; attempt++) {
        if (predicate())
            return;
        await Scripting.sleep(50);
    }
    throw new Error(message);
}

// Exercise folder rendering, windows, drag targets, and cleanup in a real compositor.
export async function run() {
    const uuid = 'dock-groups@local';
    await until(() => Main.extensionManager.lookup(uuid)?.stateObj?._enabled,
        'Extension did not enable');
    const extension = Main.extensionManager.lookup(uuid);
    const folders = extension.stateObj;
    await until(() => folders._docks().length, 'Ubuntu Dock did not enable');
    Main.overview.hide();
    await Scripting.sleep(500);

    folders._settings.set_boolean('customization', true);
    folders._settings.set_boolean('glass', true);
    const first = {desktop: 'org.gnome.Shell.PerfHelper.desktop', label: 'Test Window'};
    const second = {desktop: 'local.test.Second.desktop', label: 'Second'};
    const third = {desktop: 'local.test.Third.desktop', label: 'Third'};
    folders._createGroup(first, second);
    await until(() => [...folders._icons.values()].some(record => record.icon.mapped),
        'Folder icon did not appear');
    await Scripting.sleep(500);
    let record = [...folders._icons.values()][0];
    const key = record.group.key;
    assert(record.group.apps.length === 2, 'Grouping lost an application');
    assert(record.tiles.size === 2, 'Folder tiles were not rendered');
    const tile = record.tiles.get(first.desktop).get_child();
    assert('orientation' in tile ? tile.orientation === Clutter.Orientation.VERTICAL : tile.vertical,
        'Application tile is not vertical');

    for (const animation of ['scale', 'flow']) {
        folders._settings.set_string('animation', animation);
        assert(folders._openGroup(key), 'Could not open folder');
        assert(record.menu._timeline, `${animation} animation did not start`);
        if (animation === 'flow')
            assert(record.menu._flowEffect, 'Genie deformation effect is missing');
        await until(() => !record.menu._timeline, `${animation} animation did not complete`);
        assert(folders._animationOrigin(record.menu), 'Animation has no valid dock origin');
        assert(record.menu.isOpen && record.menu.actor.mapped, 'Folder popup did not map');
        assert(record.menu._glass.get_effect('dock-group-glass'), 'Glass blur is missing');
        assert(record.menu._glass.get_effect('dock-group-round'), 'Glass clipping is missing');
        assert(record.menu._blurEffect.radius > 0, 'Glass blur radius is zero');
        folders._openGroup(key);
        await Scripting.sleep(400);
        assert(!record.menu.isOpen && !record.menu._glassClone, 'Closed glass backdrop was retained');
    }

    const helper = await Scripting._getPerfHelper();
    await helper.CreateWindowAsync(420, 260, false, false, true, false);
    await helper.WaitWindowsAsync();
    await until(() => folders._windows(record.group).length === 1,
        'Test window was not assigned to the folder');
    const window = folders._windows(record.group)[0];
    const wmClass = window.get_wm_class();
    const client = GLib.getenv('DOCK_FOLDERS_TEST_BACKEND').split('/')[1];
    assert(window.get_client_type() === (client === 'x11' ? Meta.WindowClientType.X11 : Meta.WindowClientType.WAYLAND),
        `Test window uses the wrong client backend: ${client}`);
    await until(() => record.icon.running && record.icon.windowsCount === 1,
        'Running indicator did not update');
    await until(() => record.icon.focused, 'Folder focus did not follow its application window');
    assert(record.dots.find(([entry]) => entry.desktop === first.desktop)[1].opacity === 255,
        'Application running dot is missing');
    assert(!folders._status().dockApps.includes(first.desktop), 'Grouped application reappeared on dock');

    folders._openGroup(key);
    await Scripting.sleep(400);
    const button = record.tiles.get(first.desktop);
    record.previews._open(button, record.group.apps.find(entry => entry.desktop === first.desktop), true);
    await Scripting.sleep(250);
    assert(record.previews.popup?.isOpen, 'Window preview did not open');
    assert(record.previews.section._getMenuItems().length === 1, 'Window thumbnail is missing');
    const box = record.previews.section.box;
    assert('orientation' in box ? box.orientation === Clutter.Orientation.HORIZONTAL : !box.vertical,
        'Window previews are not horizontal');
    record.previews.clear();

    const menu = record.menu;
    folders._moveEntry(record.group.apps.find(entry => entry.desktop === first.desktop), key, second.desktop);
    await Scripting.sleep(300);
    assert([...folders._icons.values()][0].menu === menu && menu.isOpen,
        'Reordering replaced or closed the folder');
    assert(record.group.apps[0].desktop === first.desktop, 'Reordering did not update application order');
    assert(record.undo.visible, 'Undo button did not appear');
    assert(folders._undoLastMove(), 'Undo did not restore the order');
    await Scripting.sleep(400);
    folders._moveEntry(third, key);
    await until(() => [...folders._icons.values()][0]?.tiles.size === 3, 'Adding application did not update tiles');
    folders._extractEntry(third.desktop, true);
    await until(() => folders._status().dockApps.includes(third.desktop), 'Extracted application was not pinned');
    const extracted = folders._docks()[0].dash.getAppIcons().find(icon => icon.app.get_id() === third.desktop);
    assert(extracted && !folders._icons.has(extracted), 'Extracted application retained folder decoration');

    await Scripting.destroyTestWindows();
    await until(() => [...folders._icons.values()].every(item => !item.icon.running),
        'Running indicator was retained after closing the window');
    const redisplay = folders._originalRedisplay;
    Main.extensionManager.disableExtension(uuid);
    await until(() => !folders._enabled, 'Extension did not disable');
    assert(DockDash.prototype._redisplay === redisplay, 'Ubuntu Dock hook was not restored');
    assert(!folders._timer && !folders._configTimer && !folders._icons.size,
        'Extension retained timers or menus after disabling');
    assert(!extension.errors?.length, `Extension errors: ${extension.errors}`);
    print(`DOCK_FOLDERS_SHELL_OK ${GLib.getenv('DOCK_FOLDERS_TEST_BACKEND')} ${Shell.AppSystem.get_default().get_installed().length} applications, WM_CLASS=${wmClass}`);
}
