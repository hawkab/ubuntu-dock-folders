// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
import {DockDash} from 'file:///usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/dash.js';
import {checkFolderSwitch} from './folder_switch.js';
import {checkPreferencesWindows} from './preferences_windows.js';
import {checkOrbitMotion} from './orbit_motion.js';
import {checkFolderDetails} from './folder_details.js';
import {checkWindowBehavior} from './window_behavior.js';
import {checkGlassAllocation} from './glass_allocation.js';

function assert(value, message) {
    if (!value)
        throw new Error(message);
}

async function until(predicate, message, timeout = 3000) {
    for (let attempt = 0; attempt < timeout / 50; attempt++) {
        if (predicate())
            return;
        await Scripting.sleep(50);
    }
    throw new Error(typeof message === 'function' ? message() : message);
}

// Exercise folder rendering, windows, drag targets, and cleanup in a real compositor.
export async function run() {
    const helper = await Scripting._getPerfHelper();
    let helperError = null;
    const keepAlive = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
        helper.WaitWindowsAsync().catch(error => helperError = error);
        return GLib.SOURCE_CONTINUE;
    });
    const uuid = 'dock-groups@local';
    await until(() => Main.extensionManager.lookup(uuid)?.stateObj?._enabled,
        'Extension did not enable');
    const extension = Main.extensionManager.lookup(uuid);
    const folders = extension.stateObj;
    await until(() => folders._dock._docks().length, 'Ubuntu Dock did not enable');
    Main.overview.hide();
    await Scripting.sleep(500);
    if (GLib.getenv('DOCK_FOLDERS_TEST_PREFERENCES_ONLY')) {
        await checkPreferencesWindows(folders, extension.path, until, assert);
        GLib.Source.remove(keepAlive);
        assert(!helperError, `Test helper failed: ${helperError}`);
        print(`DOCK_FOLDERS_SHELL_OK ${GLib.getenv('DOCK_FOLDERS_TEST_BACKEND')} preferences`);
        return;
    }
    assert(folders._groups.stale.apps.length === 2 &&
        !folders._groups.stale.apps.some(entry => entry.desktop === 'local.test.Missing.desktop'),
        'Startup retained an uninstalled application');
    const fallback = folders._appIcon({desktop: 'local.test.Missing.desktop'}, 64);
    assert(fallback.icon_name === 'application-x-executable', 'Missing application has no safe icon');
    fallback.destroy();
    const lookup = folders._appSystem.lookup_app;
    folders._appSystem.lookup_app = id => id === 'local.test.NoIcon.desktop' ? null : lookup.call(folders._appSystem, id);
    try {
        const icon = folders._appIcon({desktop: 'local.test.NoIcon.desktop'}, 64);
        assert(icon.icon_name === 'application-x-executable', 'Icon-less desktop entry has no safe icon');
        icon.destroy();
    } finally {
        folders._appSystem.lookup_app = lookup;
    }

    folders._settings.set_boolean('customization', true);
    folders._settings.set_int('blur-strength', 100);
    const first = {desktop: 'org.gnome.Shell.PerfHelper.desktop', label: 'Test Window'};
    const second = {desktop: 'local.test.Second.desktop', label: 'Second'};
    const third = {desktop: 'local.test.Third.desktop', label: 'Third'};
    const gridSource = new Gio.Settings({schema_id:'org.gnome.desktop.app-folders.folder',
        path:`${folders._grid.root.path}folders/ExistingFolderTest/`});
    gridSource.set_string('name','Grid tools');
    gridSource.set_boolean('translate',false);
    gridSource.set_strv('apps',[second.desktop,third.desktop,'local.test.Missing.desktop']);
    gridSource.set_strv('categories',[]);
    gridSource.set_strv('excluded-apps',[third.desktop]);
    assert(JSON.stringify(folders._grid._read(gridSource).apps) === JSON.stringify([second.desktop]),
        'Shared source resolver ignored exclusions or missing applications');
    gridSource.set_strv('excluded-apps',[]);
    folders._grid.root.set_strv('folder-children',['ExistingFolderTest']);
    const linked = JSON.parse(folders._settings.get_string('groups'));
    linked.stale.gridFolder='ExistingFolderTest';
    folders._settings.set_string('groups',JSON.stringify(linked));
    folders._grid.pull();
    await until(() => folders._groups.stale.name === 'Grid tools','Imported grid name did not synchronize');
    gridSource.set_string('name','Updated grid tools');
    await until(() => folders._groups.stale.name === 'Updated grid tools','Live grid change did not synchronize');
    folders._grid.push({...folders._groups,stale:{...folders._groups.stale,name:'Updated from dock'}});
    assert(gridSource.get_string('name') === 'Updated from dock','Dock name did not synchronize to the grid');
    folders._grid.root.set_strv('folder-children',[]);
    await until(() => !folders._groups.stale.gridFolder,'Removed source retained a stale link');
    folders._commands._createGroup(first, second);
    const key = folders._entryIds.get(first.desktop).group.key;
    await until(() => [...folders._icons.values()].some(record => record.group.key === key && record.icon.mapped),
        'Folder icon did not appear');
    await Scripting.sleep(500);
    let record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    assert(record.group.apps.length === 2, 'Grouping lost an application');
    assert(record.tiles.size === 2, 'Folder tiles were not rendered');
    await checkFolderDetails(folders, record, until, assert);
    await checkFolderSwitch(folders, key, third, until, assert);
    record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    record.menu.open();
    await Scripting.sleep(500);
    const underlay = new St.Widget({x:0,y:0,width:global.stage.width,height:global.stage.height,
        style:'background-color:white;',reactive:false});
    record.menu.actor.get_parent().insert_child_below(underlay,record.menu.actor);
    await Scripting.sleep(100);
    await record.menu._contrast.sample();
    assert(!record.menu._contrast.lastError,'Backdrop sampling failed: '+record.menu._contrast.lastError);
    assert(record.menu._contrast.backdrop === '#ffffff','Backdrop was not sampled: '+record.menu._contrast.backdrop);
    assert(record.menu.actor.has_style_class_name('dock-group-light'),'White backdrop did not switch labels to black');
    await Scripting.sleep(500);
    const samples = record.menu._contrast.samples;
    await Scripting.sleep(750);
    assert(record.menu._contrast.samples === samples, 'Idle folder kept sampling its background');
    underlay.destroy();
    record.menu.close();

    for (const count of [3, 4, 5, 9]) {
        const sample = folders._folderIcon({...record.group, iconRotation: 45,
            apps: Array.from({length: count}, (_, index) => record.group.apps[index % 2])}, 48, true);
        assert(sample.get_n_children() === 1 + Math.min(5, count), 'Miniature count is incorrect');
        assert(Number.isFinite(sample.width) && Number.isFinite(sample.height), 'Miniature dimensions are invalid');
        if (count > 5) assert(sample.get_children()[1].rotation_angle_z !== 0, 'Cards did not rotate');
        sample.destroy();
    }
    const stack = folders._folderIcon({...record.group, alwaysStack: true}, 48, true);
    assert(stack.get_children()[1].rotation_angle_z !== 0, 'Forced stack was ignored');
    stack.destroy();
    const dash = folders._dock._docks()[0].dash;
    const popupCount = Main.uiGroup.get_n_children();
    const dropCount = folders._dropIcons.size;
    const stylePopup = folders._stylePopup;
    let rejected = false;
    folders._stylePopup = () => { throw new Error('Injected popup construction failure'); };
    try {
        dash._createAppItem(record.icon.app);
    } catch (error) {
        rejected = error.message === 'Injected popup construction failure';
    } finally {
        folders._stylePopup = stylePopup;
    }
    assert(rejected, 'Popup failure was not propagated');
    assert(Main.uiGroup.get_n_children() === popupCount && folders._dropIcons.size === dropCount,
        'Failed popup construction leaked actors or drag targets');
    record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    const tile = record.tiles.get(first.desktop).get_child();
    assert('orientation' in tile ? tile.orientation === Clutter.Orientation.VERTICAL : tile.vertical,
        'Application tile is not vertical');

    for (const animation of ['none', 'fade', 'scale', 'flow', 'lamp', 'fold', 'sheet', 'unfold']) {
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        folders._settings.set_string('animation', animation);
        await Scripting.sleep(400);
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        assert(folders._openGroup(key), 'Could not open folder');
        await until(() => record.menu.isOpen, `${animation} folder did not open after layout`);
        assert(animation === 'none' ? !record.menu._timeline : record.menu._timeline,
            `${animation} animation mode was ignored: selected=${folders._settings.get_string('animation')}, ` +
            `enabled=${St.Settings.get().enable_animations}, destroyed=${record.menu._destroying}, open=${record.menu.isOpen}`);
        if (['flow', 'lamp', 'fold', 'sheet', 'unfold'].includes(animation))
            assert(record.menu._flowEffect, 'Genie deformation effect is missing');
        await until(() => {
            record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
            return record?.menu.isOpen && !record.menu._timeline && record.menu.actor.mapped;
        }, () => `${animation} animation did not complete: open=${record?.menu.isOpen}, mapped=${record?.menu.actor.mapped}, timeline=${record?.menu._timeline?.get_progress()}, opacity=${record?.menu.actor.opacity}, destroyed=${record?.menu._destroying}`);
        assert(folders._animation._animationOrigin(record.menu), 'Animation has no valid dock origin');
        assert(record.menu.isOpen && record.menu.actor.mapped, 'Folder popup did not map');
        await until(() => record.menu._glassClone, 'Open folder did not restore its backdrop blur');
        assert(record.menu._glass.get_effect('dock-group-glass'), 'Glass blur is missing');
        assert(record.menu._glass.get_effect('dock-group-round'), 'Glass clipping is missing');
        assert(record.menu._blurEffect.radius > 0, 'Glass blur radius is zero');
        folders._stylePopup(record.menu, {...record.group, backgroundOpacity: .17});
        assert(record.menu._glass.opacity === 255 && record.menu._glass.visible,
            'Transparency changed the blur amount');
        folders._stylePopup(record.menu, {...record.group, blurStrength: 50});
        assert(record.menu._glass.opacity === 255 && record.menu._blurEffect.radius === 24,
            'Blur slider did not adjust the backdrop radius');
        folders._stylePopup(record.menu, {...record.group, blurStrength: 0});
        assert(!record.menu._glass.visible && !record.menu._glassClone,
            'Zero blur retained the backdrop');
        folders._stylePopup(record.menu, {...record.group, blurStrength: 100});
        await until(() => record.menu._glassClone, 'Restoring blur did not restore its backdrop');
        assert(record.menu._glass.visible && record.menu._glassClone,
            'Restoring blur did not restore its backdrop');
        folders._openGroup(key);
        await Scripting.sleep(400);
        assert(!record.menu.isOpen && !record.menu._glassClone, 'Closed glass backdrop was retained');
    }

    folders._settings.set_int('hover-angle', 60);
    folders._settings.set_int('hover-speed', 150);
    for (const [mode, stacked] of [['cards', false], ['rotate', false], ['cards', true], ['rotate-cards', true]]) {
        const groups = JSON.parse(folders._settings.get_string('groups'));
        groups[key].alwaysStack = stacked;
        folders._settings.set_string('groups', JSON.stringify(groups));
        folders._settings.set_string('hover-effect', mode);
        await Scripting.sleep(400);
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        const miniatures = record.icon.icon.icon;
        assert(miniatures, 'Hover has no miniature actor');
        const resting = miniatures.get_children().slice(1).map(item =>
            [item.x, item.y, item.rotation_angle_z, item.get_child().rotation_angle_z]);
        record.icon.set_hover(true);
        await Scripting.sleep(250);
        const hovered = miniatures.get_children().slice(1).map(item =>
            [item.x, item.y, item.rotation_angle_z, item.get_child().rotation_angle_z]);
        const moved = hovered.some((item, index) => Math.hypot(item[0]-resting[index][0], item[1]-resting[index][1]) > 1);
        assert(moved === (mode !== 'cards' || stacked), `${mode} hover did not respect the formation type`);
        if (mode === 'rotate') hovered.forEach((item,index) =>
            assert(Math.abs(item[2]-resting[index][2]-60) < .01 &&
                Math.abs(item[2]+item[3]-resting[index][2]-resting[index][3]) < .01,
                'Hover must orbit the glyph without turning its face'));
        record.icon.set_hover(false);
        await Scripting.sleep(250);
        miniatures.get_children().slice(1).forEach((item,index) =>
            assert(Math.hypot(item.x-resting[index][0],item.y-resting[index][1]) < .01,
                `${mode}/${stacked} hover did not restore the formation: ${JSON.stringify({resting:resting[index],current:[item.x,item.y],width:miniatures.width,height:miniatures.height})}`));
    }
    const savedGroups = JSON.parse(folders._settings.get_string('groups'));
    const expandedGroups = JSON.parse(JSON.stringify(savedGroups));
    const memberIds = new Set(expandedGroups[key].apps.map(entry => entry.desktop));
    const extraApps = folders._appSystem.get_installed().filter(app => !memberIds.has(app.get_id())
        && !app.get_id().startsWith('local.groups.')).slice(0,3);
    assert(extraApps.length === 3, 'Hover fixture has too few installed applications');
    expandedGroups[key].apps.push(...extraApps.map(app => ({desktop:app.get_id(),label:app.get_name()})));
    expandedGroups[key].alwaysStack = true;
    folders._settings.set_string('groups', JSON.stringify(expandedGroups));
    folders._settings.set_string('hover-effect', 'cards');
    await Scripting.sleep(400);
    record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
    const stackActor = record.icon.icon.icon;
    const compactWidth = stackActor.width;
    record.icon.set_hover(true);
    await Scripting.sleep(250);
    assert(stackActor.get_children().slice(1).filter(item => item.visible && item.opacity > 0).length === expandedGroups[key].apps.length,
        'Hover did not render applications beyond the fifth');
    assert(stackActor.width > compactWidth && stackActor.width <= compactWidth * 2,
        'Stack did not expand within twice its compact width');
    record.icon.set_hover(false);
    await Scripting.sleep(250);
    assert(stackActor.get_children().slice(1).filter(item => item.visible).length === 5,
        'Collapsed stack retained extra visible cards');
    folders._settings.set_string('groups', JSON.stringify(savedGroups));
    await Scripting.sleep(400);
    const groups = JSON.parse(folders._settings.get_string('groups'));
    groups[key].alwaysStack = false;
    folders._settings.set_string('groups', JSON.stringify(groups));
    folders._settings.set_string('hover-effect', 'none');
    await Scripting.sleep(400);
    record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);

    folders._settings.set_string('animation', 'none');
    await checkOrbitMotion(folders,key,until,assert);
    record = [...folders._icons.values()].find(item => item.group.key===key && item.icon.mapped);
    assert(folders._openGroup(key), 'Could not open folder before rebuilding the dock');
    const oldIcon = record.icon;
    folders._queueUpdate();
    dash.resetAppIcons();
    await until(() => {
        record = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        return record && record.icon !== oldIcon && record.menu.isOpen;
    }, 'Rebuilding the dock lost the open folder');
    folders._openGroup(key);
    await Scripting.sleep(100);

    const wmClass = await checkWindowBehavior({folders, key, helper, first, second, third, until, assert, record});
    await checkGlassAllocation(folders, key, third, until, assert);
    await checkPreferencesWindows(folders, extension.path, until, assert);
    const redisplay = folders._originalRedisplay;
    Main.extensionManager.disableExtension(uuid);
    await until(() => !folders._enabled, 'Extension did not disable');
    assert(DockDash.prototype._redisplay === redisplay, 'Ubuntu Dock hook was not restored');
    assert(!folders._timer && !folders._configTimer && !folders._icons.size,
        'Extension retained timers or menus after disabling');
    assert(!extension.errors?.length, `Extension errors: ${extension.errors}`);
    GLib.Source.remove(keepAlive);
    assert(!helperError, `Test helper failed: ${helperError}`);
    print(`DOCK_FOLDERS_SHELL_OK ${GLib.getenv('DOCK_FOLDERS_TEST_BACKEND')} ${Shell.AppSystem.get_default().get_installed().length} applications, WM_CLASS=${wmClass}`);
}
