// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {bindPreferences} from './preferencesBinding.js';
import {attachPreviews} from './settingsPreview.js';
import {attachExistingFolders} from './existingFolders.js';
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
        window.set_default_size(620, 800);
        window.set_search_enabled(false);

        const settings = this.getSettings('org.gnome.shell.extensions.dock-groups');
        window._settings = settings;
        bindPreferences(builder,settings,window,text => this.gettext(text));
        attachPreviews(builder,settings,window,text => this.gettext(text));
        attachExistingFolders(builder,settings,window,text => this.gettext(text));
    }
}
