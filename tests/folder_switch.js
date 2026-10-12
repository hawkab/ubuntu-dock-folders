// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';

/** Click adjacent folders through the compositor's modal pointer handling. */
export async function checkFolderSwitch(folders, firstKey, secondEntry, until, assert) {
    assert(GLib.getenv('DOCK_FOLDERS_TEST_SESSION'), 'Pointer test requires a private desktop');
    const settings = folders._settings;
    const groups = settings.get_string('groups');
    const favorites = global.settings.get_strv('favorite-apps');
    const backend = global.stage.context?.get_backend() ?? Clutter.get_default_backend();
    const pointer = backend.get_default_seat()
        .create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
    try {
        folders._view._closeMenus();
        folders._commands._createGroup(secondEntry, {desktop:'local.test.NoIcon.desktop',label:'No icon'});
        await until(() => Object.keys(folders._groups).length === 2, 'Switch fixture did not create a second group');
        const secondKey = folders._entryIds.get(secondEntry.desktop).group.key;
        await until(() => [...folders._icons.values()].filter(item => item.icon.mapped).length === 2,
            'Both switch targets did not map');
        await Scripting.sleep(500);
        for (const key of [firstKey, secondKey, firstKey, secondKey]) {
            await until(() => [...folders._icons.values()].some(item => item.group.key === key && item.icon.mapped),
                'Switch target did not map');
            let record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
            const [x, y] = record.icon.get_transformed_position();
            const [width, height] = record.icon.get_transformed_size();
            pointer.notify_absolute_motion(GLib.get_monotonic_time(), x + width/2, y + height/2);
            await Scripting.sleep(100);
            pointer.notify_absolute_motion(GLib.get_monotonic_time(), x + width/2, y + height/2);
            await Scripting.sleep(50);
            pointer.notify_button(GLib.get_monotonic_time(), 1, Clutter.ButtonState.PRESSED);
            await Scripting.sleep(50);
            pointer.notify_button(GLib.get_monotonic_time(), 1, Clutter.ButtonState.RELEASED);
            await until(() => {
                record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
                return record?.menu.isOpen && !record.menu._timeline;
            }, () =>
                `One click did not open ${key}: point=${x + width/2},${y + height/2}, pointer=${global.get_pointer()}, ` +
                `menus=${JSON.stringify([...folders._icons.values()].map(item => ({key:item.group.key,open:item.menu.isOpen,mapped:item.icon.mapped})))}; ` +
                `picked=${global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE,x + width/2,y + height/2)}`);
            await Scripting.sleep(150);
            assert([...folders._icons.values()].filter(item => item.menu.isOpen).length === 1,
                'Folder switching left two menus open');
            assert(record.menu.isOpen, 'Release of the switching click closed the new folder');
        }
        print('GNOME: native pointer switching between folders passed');
    } finally {
        folders._view._closeMenus();
        pointer.notify_absolute_motion(GLib.get_monotonic_time(), 500, 400);
        await Scripting.sleep(100);
        pointer.notify_absolute_motion(GLib.get_monotonic_time(), 500, 400);
        settings.set_string('groups', groups);
        global.settings.set_strv('favorite-apps', favorites);
        await Scripting.sleep(500);
    }
}
