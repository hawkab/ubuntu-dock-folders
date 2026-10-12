// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';

/** Extract and regroup applications, including destruction during an active drag. */
export async function checkDragLifecycle(folders, third, until, assert) {
    assert(GLib.getenv('DOCK_FOLDERS_TEST_SESSION'), 'Drag test requires a private desktop');
    const groups = folders._settings.get_string('groups');
    const favorites = global.settings.get_strv('favorite-apps');
    const backend = global.stage.context?.get_backend() ?? Clutter.get_default_backend();
    const pointer = backend.get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
    let pressed = false;
    const noIcon = {desktop:'local.test.NoIcon.desktop',label:'No icon'};
    const recordFor = key => [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    const motion = async (x,y) => {
        pointer.notify_absolute_motion(GLib.get_monotonic_time(),x,y);
        await Scripting.sleep(100);
        pointer.notify_absolute_motion(GLib.get_monotonic_time(),x,y);
        await Scripting.sleep(50);
    };
    try {
        folders._view._closeMenus();
        folders._commands._createGroup(third,noIcon);
        let key = folders._entryIds.get(third.desktop).group.key;
        for (const rebuild of [false,true]) {
            await until(() => recordFor(key), 'Drag fixture did not map');
            await Scripting.sleep(500);
            folders._openGroup(key);
            await until(() => recordFor(key)?.menu.isOpen && !recordFor(key)?.menu._timeline,
                'Drag fixture did not open');
            await Scripting.sleep(500);
            let record = recordFor(key);
            const button = record.tiles.get(third.desktop);
            const [x,y] = button.get_transformed_position();
            const [width,height] = button.get_transformed_size();
            await motion(x+width/2,y+height/2);
            assert(button.mapped && record.menu.actor.contains(global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE,x+width/2,y+height/2)),
                `Drag tile is not pickable: mapped=${button.mapped}, menu=${record.menu.isOpen}, ` +
                `position=${x},${y},${width},${height}, picked=${global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE,x+width/2,y+height/2)}`);
            pointer.notify_button(GLib.get_monotonic_time(),1,Clutter.ButtonState.PRESSED);
            pressed = true;
            await Scripting.sleep(50);
            await motion(x+width/2+30,y+height/2);
            await until(() => folders._dragging, () => 'Native pointer did not start dragging: ' +
                `tile=${x},${y},${width},${height}, mapped=${button.mapped}, pointer=${global.get_pointer()}, ` +
                `picked=${global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE,x+width/2,y+height/2)}`);
            await motion(global.stage.width-30,global.stage.height/2);
            if (rebuild) {
                folders._dock._docks()[0].dash.resetAppIcons();
                await until(() => recordFor(key)?.menu !== record.menu, 'Active drag did not rebuild its source');
                assert(!folders._extractLayer, 'Destroyed folder retained its extraction layer');
            }
            pointer.notify_button(GLib.get_monotonic_time(),1,Clutter.ButtonState.RELEASED);
            pressed = false;
            await until(() => !folders._dragging && !folders._extractTargets.length,
                'Drag completion retained a grab or extraction targets');
            await Scripting.sleep(500);
            if (!rebuild) {
                assert(!folders._groups[key], 'Extracting from two applications did not dissolve the folder');
                assert(global.settings.get_strv('favorite-apps').includes(third.desktop), 'Extracted application was not pinned');
                const icons = folders._dock._docks()[0].dash.getAppIcons();
                const source = icons.find(item => item.app.get_id() === third.desktop);
                const target = icons.find(item => item.app.get_id() === noIcon.desktop);
                assert(source && target, 'Extracted applications did not return to the dock');
                folders._commands._createGroup(folders._dnd._sourceEntry(source),folders._dnd._sourceEntry(target));
                key = folders._entryIds.get(third.desktop).group.key;
                assert(folders._groups[key].apps.find(app => app.desktop === third.desktop).label === third.desktop.replace('.desktop',''),
                    'Regrouping used the desktop filename instead of the application name');
            }
        }
        print('DRAG_LIFECYCLE_OK extract, regroup and source destruction');
    } finally {
        if (pressed) pointer.notify_button(GLib.get_monotonic_time(),1,Clutter.ButtonState.RELEASED);
        folders._view._closeMenus();
        folders._dnd._removeExtractTargets();
        await motion(global.stage.width-20,global.stage.height-20);
        pointer.run_dispose();
        const writer = new Gio.Settings({settings_schema:folders._settings.settings_schema});
        writer.set_string('groups',groups);
        global.settings.set_strv('favorite-apps',favorites);
        await until(() => folders._settings.get_string('groups') === groups &&
            Object.keys(folders._groups).length === Object.keys(JSON.parse(groups)).length,
        'Restoring drag fixtures did not restore the folders');
        await Scripting.sleep(500);
    }
}
