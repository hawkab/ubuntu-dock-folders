// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';
import {contract} from './core/contract.js';
import {hoverEffect, hoverChoice, blurLevel} from './core/preferences.js';
import {onWindowClose} from './windowLifecycle.js';

/** Bind GTK rows to the shared settings contract and release listeners on close. */
export function bindPreferences(builder, settings, window, translate) {
    if (settings.get_int('blur-strength') < 0)
        settings.set_int('blur-strength',blurLevel(-1,settings.get_boolean('glass')));
    const signals = [];
    for (const preference of contract.preferences) {
        const id = preference.key.replaceAll('-', '_'), row = builder.get_object(id + '_row');
        if (!row) continue;
        if (preference.type === 'enum') {
            const choices = contract[preference.name === 'animation' ? 'animations' : 'hoverEffects'];
            row.set_model(Gtk.StringList.new(choices.map(item => translate(item.label))));
            const update = () => row.set_selected(Math.max(0,choices.findIndex(item => item.key === settings.get_string(preference.key))));
            update();
            row.connect('notify::selected', () => settings.set_string(preference.key,choices[row.get_selected()].key));
            signals.push(settings.connect('changed::'+preference.key,update));
        } else {
            const adjustment = builder.get_object(id + '_adjustment');
            const scale = builder.get_object(id + '_scale');
            if (scale) scale.set_format_value_func((_scale,value) => Math.round(value) + (preference.unit ? ' ' + preference.unit : preference.name === 'popupIconSize' ? ' px' : preference.name === 'hoverAngle' ? '°' : '%'));
            if (adjustment) {
                adjustment.lower = preference.range[0]; adjustment.upper = preference.range[1];
                adjustment.step_increment = preference.range[2];
            }
            settings.bind(preference.key,builder.get_object(id+'_check') || adjustment || row,preference.type === 'bool' ? 'active' : 'value',Gio.SettingsBindFlags.DEFAULT);
        }
        if (preference.key !== 'enabled') settings.bind('enabled',row,'sensitive',Gio.SettingsBindFlags.GET);
    }
    const rotate=builder.get_object('hover_rotate_check'), cards=builder.get_object('hover_cards_check');
    let updating=false;
    const hoverChanged=() => {
        const value=hoverEffect(settings.get_string('hover-effect'));
        updating=true; rotate.active=value.rotate; cards.active=value.cards; updating=false;
        const enabled=settings.get_boolean('enabled');
        builder.get_object('hover_rotate_row').sensitive=enabled;
        builder.get_object('hover_cards_row').sensitive=enabled;
        builder.get_object('hover_angle_row').sensitive=enabled && value.rotate;
        builder.get_object('hover_angle_row').visible=value.rotate;
        builder.get_object('hover_speed_row').sensitive=enabled && (value.rotate || value.cards);
        builder.get_object('hover_speed_row').visible=value.rotate || value.cards;
    };
    const saveHover=() => { if (!updating) settings.set_string('hover-effect',hoverChoice(rotate.active,cards.active).key); };
    rotate.connect('notify::active',saveHover); cards.connect('notify::active',saveHover);
    signals.push(settings.connect('changed::hover-effect',hoverChanged),settings.connect('changed::enabled',hoverChanged));
    hoverChanged();
    const speed = builder.get_object('animation_speed_row');
    const sensitive = () => speed.sensitive = settings.get_boolean('enabled') && settings.get_string('animation') !== 'none';
    signals.push(settings.connect('changed::animation',sensitive),settings.connect('changed::enabled',sensitive));
    sensitive();
    onWindowClose(window, () => {
        for (const signal of signals)
            settings.disconnect(signal);
    });
}
