// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import Gettext from 'gettext';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {AppMenu} from 'resource:///org/gnome/shell/ui/appMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

/** Verify dock and overview actions send the package ID over D-Bus. */
export async function checkFolderDetails(folders, record, until, assert) {
    const calls = [];
    const xml = `<node><interface name="org.gtk.Actions"><method name="Activate">
        <arg type="s" direction="in"/><arg type="av" direction="in"/>
        <arg type="a{sv}" direction="in"/></method></interface></node>`;
    const service = Gio.DBusExportedObject.wrapJSObject(xml, {
        Activate: (action, parameters) => calls.push([action, parameters[0].deepUnpack()[0]]),
    });
    service.export(Gio.DBus.session, '/org/gnome/Software');
    let acquired = false;
    const owner = Gio.bus_own_name_on_connection(Gio.DBus.session, 'org.gnome.Software',
        Gio.BusNameOwnerFlags.NONE, () => { acquired = true; }, () => { acquired = false; });
    const menu = new AppMenu(record.icon, St.Side.BOTTOM, {favoritesSection: true});
    Main.uiGroup.add_child(menu.actor);
    menu.actor.hide();
    const ordinary = Shell.AppSystem.get_default().lookup_app('local.test.Second.desktop');
    try {
        await until(() => acquired, 'Software details test service did not own its bus name');
        const label = Gettext.domain('gnome-shell').gettext('App Details');
        for (let index = 0; index < 2; index++) {
            record.icon.popupMenu();
            const item = record.icon._menu._getMenuItems().find(candidate => candidate.label?.text === label);
            assert(item, 'Folder context menu lost App Details');
            item.activate(null);
            await until(() => calls.length === index + 1, 'Dock details did not dispatch a D-Bus action');
            assert(!record.icon._menu.isOpen, 'Folder context menu stayed open after App Details');
            assert(record.icon.app.get_id() === record.group.desktopId, 'Details changed the folder identity');
        }
        menu.setApp(record.icon.app);
        menu._detailsItem.activate(null);
        await until(() => calls.length === 3, 'Overview details did not dispatch a D-Bus action');
        assert(calls.every(([action, id]) => action === 'details' && id === 'io.github.hawkab.UbuntuDockFolders.desktop'),
            'Virtual folder ID was sent to the software center');
        menu.setApp(ordinary);
        menu._detailsItem.activate(null);
        await until(() => calls.length === 4, 'Normal application details stopped working');
        assert(calls[3][1] === ordinary.get_id(), 'Normal application details were redirected');
        menu.setApp(record.icon.app);
        folders._dock.details.uninstall();
        menu._detailsItem.activate(null);
        await until(() => calls.length === 5, 'Disabling did not restore the original menu action');
        assert(calls[4][1] === record.group.desktopId, 'Disabling retained the details override');
    } finally {
        folders._dock.details.uninstall();
        folders._dock.details.install();
        for (const {icon} of folders._icons.values())
            folders._dock.details.decorateDockIcon(icon);
        record.icon._menu?.close();
        menu.destroy();
        Gio.bus_unown_name(owner);
        service.unexport();
    }
    print('FOLDER_DETAILS_OK dock, overview, repeated opening, ordinary apps and disable cleanup');
}
