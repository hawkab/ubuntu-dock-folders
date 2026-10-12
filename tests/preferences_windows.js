// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import Shell from 'gi://Shell';

/** Check application identity and grouping of real folder settings windows. */
export async function checkPreferencesWindows(folders, path, until, assert) {
    const id = 'io.github.hawkab.UbuntuDockFolders';
    const saved = folders._settings.get_string('groups');
    const groups = JSON.parse(saved);
    const keys = ['identity-one', 'identity-two'];
    const children = [];
    let app;
    let completed = false;
    try {
        for (const [index, key] of keys.entries()) {
            groups[key] = {id: `local.groups.Identity${index}`, name: `Settings ${index + 1}`,
                apps: [{desktop: 'local.test.Second.desktop', label: 'Second'}]};
        }
        folders._settings.set_string('groups', JSON.stringify(groups));
        for (const key of keys)
            children.push(Gio.Subprocess.new(['/usr/bin/python3', `${path}/app/preferences.py`, key],
                Gio.SubprocessFlags.NONE));
        const tracker = Shell.WindowTracker.get_default();
        await until(() => {
            app = Shell.AppSystem.get_default().lookup_app(`${id}.desktop`);
            return app?.get_windows().length === 2;
        }, 'Folder settings did not stack under their installed desktop entry', 7000);
        assert(app.get_app_info().get_icon().to_string() === id,
            'Folder settings use a fallback application icon');
        assert(app.get_name() === 'Ubuntu Dock Folders', 'Folder settings show an internal application ID');
        const windows = app.get_windows();
        await until(() => folders._dock._docks().every(dock => dock.dash._box.get_children().some(item =>
            item.child?.app === app && keys.every(key => item._labelText.includes(groups[key].name)))),
        'Dock tooltip did not stack the edited folder names');
        for (const [index, key] of keys.entries()) {
            const window = windows.find(item => item.get_title().endsWith(` — ${groups[key].name}`));
            assert(window, `Folder settings title lost the name of ${key}`);
            assert(tracker.get_window_app(window) === app, 'Folder settings use different dock applications');
        }
        completed = true;
    } finally {
        for (const window of app?.get_windows() || [])
            window.delete(global.get_current_time());
        if (!app)
            for (const child of children)
                child.force_exit();
        if (app)
            await until(() => app.get_windows().length === 0, 'Folder settings did not close');
        for (const child of children)
            await new Promise((resolve, reject) => child.wait_async(null, (process, result) => {
                try { process.wait_finish(result); resolve(); } catch (error) { reject(error); }
            }));
        folders._settings.set_string('groups', saved);
        if (completed)
            assert(children.every(child => child.get_successful()), 'Folder settings crashed during shutdown');
    }
    print('PREFERENCES_WINDOWS_OK two windows, one application, named folders');
}
