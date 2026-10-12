// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';

/** Show a transient undo action for the last folder edit. */
export class FolderFeedback {
    constructor(host) { this.host = host; }

    clear() {
        this.host._notification?.destroy();
        this.host._notification = null;
    }

    show(undo) {
        this.clear();
        const source = MessageTray.getSystemSource();
        const notification = new MessageTray.Notification({source, title: _('Dock folders'),
            body: _('Folder updated'), isTransient: true});
        notification.addAction(_('Undo'), undo);
        this.host._notification = notification;
        notification.connect('destroy', () => {
            if (this.host._notification === notification)
                this.host._notification = null;
        });
        source.addNotification(notification);
    }
}
