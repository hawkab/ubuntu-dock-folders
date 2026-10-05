// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

// Expose grouping preferences through GNOME Extensions.
export default class DockFoldersPreferences extends ExtensionPreferences {
    constructor(metadata) {
        super(metadata);
        this.initTranslations('ubuntu-dock-folders');
    }

    fillPreferencesWindow(window) {
        const language = GLib.get_language_names()[0].split(/[_-]/)[0];
        Gtk.Widget.set_default_direction(['ar', 'ur'].includes(language)
            ? Gtk.TextDirection.RTL : Gtk.TextDirection.LTR);
        const builder = new Gtk.Builder();
        builder.set_translation_domain('ubuntu-dock-folders');
        builder.add_from_file(`${this.path}/preferences.ui`);
        const template = builder.get_object('preferences_window');
        const page = builder.get_object('preferences_page');
        template.remove(page);
        window.add(page);
        template.destroy();
        window.set_default_size(620, 700);
        window.set_search_enabled(false);

        const settings = this.getSettings('org.gnome.shell.extensions.dock-groups');
        window._settings = settings;
        for (const key of ['enabled', 'customization', 'glass'])
            settings.bind(key, builder.get_object(`${key}_row`), 'active', Gio.SettingsBindFlags.DEFAULT);
        for (const key of ['customization', 'glass'])
            settings.bind('enabled', builder.get_object(`${key}_row`), 'sensitive', Gio.SettingsBindFlags.GET);
        const grid = builder.get_object('grid_folders_row');
        settings.bind('enabled', grid, 'sensitive', Gio.SettingsBindFlags.GET);
        grid.connect('activated', () => Gio.Subprocess.new(
            ['/usr/bin/python3', `${this.path}/app/grid_folders.py`], Gio.SubprocessFlags.NONE));
        settings.bind('font-size', builder.get_object('font_size_row'), 'value', Gio.SettingsBindFlags.DEFAULT);

        const animation = builder.get_object('animation_row');
        animation.set_selected(settings.get_string('animation') === 'flow' ? 1 : 0);
        animation.connect('notify::selected', row => {
            settings.set_string('animation', row.get_selected() ? 'flow' : 'scale');
        });
        const changed = settings.connect('changed::animation', () => {
            animation.set_selected(settings.get_string('animation') === 'flow' ? 1 : 0);
        });
        window.connect('close-request', () => {
            settings.disconnect(changed);
            return false;
        });
    }
}
