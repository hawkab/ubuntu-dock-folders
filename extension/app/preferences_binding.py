# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Bind GTK preference rows using the portable settings contract."""

import json
from gi.repository import Gio, Gtk
from settings import ROOT
from i18n import _
from window_lifecycle import on_window_close

CONTRACT = json.loads((ROOT / "core/contract.json").read_text())


def bind_preferences(builder, settings, window):
    """Bind both directions and disconnect settings listeners when the window closes."""
    signals = []
    for preference in CONTRACT["preferences"]:
        if preference["name"] == "blurStrength" and settings.get_int(preference["key"]) < 0:
            settings.set_int(preference["key"], CONTRACT["legacy"]["blurStrength"] if settings.get_boolean("glass") else 0)
        identifier = preference["key"].replace("-", "_")
        row = builder.get_object(identifier + "_row")
        if row is None:
            continue
        if preference["type"] == "enum":
            choices = CONTRACT["animations" if preference["name"] == "animation" else "hoverEffects"]
            row.set_model(Gtk.StringList.new([_(item["label"]) for item in choices]))

            def update(*_args, row=row, choices=choices, key=preference["key"]):
                row.set_selected(next((index for index, item in enumerate(choices) if item["key"] == settings.get_string(key)), 0))

            update()
            row.connect("notify::selected", lambda row, _p, key=preference["key"], choices=choices:
                        settings.set_string(key, choices[row.get_selected()]["key"]))
            signals.append(settings.connect("changed::" + preference["key"], update))
        else:
            adjustment = builder.get_object(identifier + "_adjustment")
            scale = builder.get_object(identifier + "_scale")
            if scale:
                suffix = " " + preference["unit"] if preference.get("unit") else " px" if preference["name"] == "popupIconSize" else "°" if preference["name"] == "hoverAngle" else "%"
                scale.set_format_value_func(lambda _scale, value, suffix=suffix: f"{round(value)}{suffix}")
            if adjustment:
                lower, upper, step = preference["range"]
                adjustment.configure(adjustment.get_value(), lower, upper, step, step * 2, 0)
            control=builder.get_object(identifier + "_check") or adjustment or row
            settings.bind(preference["key"], control,
                          "active" if preference["type"] == "bool" else "value", Gio.SettingsBindFlags.DEFAULT)
        if preference["key"] != "enabled":
            settings.bind("enabled", row, "sensitive", Gio.SettingsBindFlags.GET)
    rotate, cards = builder.get_object("hover_rotate_check"), builder.get_object("hover_cards_check")
    updating = False

    def hover_changed(*_args):
        nonlocal updating
        value = next(item for item in CONTRACT["hoverEffects"] if item["key"] == settings.get_string("hover-effect"))
        updating = True
        rotate.set_active(value["rotate"]); cards.set_active(value["cards"])
        updating = False
        enabled = settings.get_boolean("enabled")
        builder.get_object("hover_rotate_row").set_sensitive(enabled)
        builder.get_object("hover_cards_row").set_sensitive(enabled)
        builder.get_object("hover_angle_row").set_sensitive(enabled and value["rotate"])
        builder.get_object("hover_angle_row").set_visible(value["rotate"])
        builder.get_object("hover_speed_row").set_sensitive(enabled and (value["rotate"] or value["cards"]))
        builder.get_object("hover_speed_row").set_visible(value["rotate"] or value["cards"])

    def save_hover(*_args):
        if not updating:
            value = next(item for item in CONTRACT["hoverEffects"]
                         if item["rotate"] == rotate.get_active() and item["cards"] == cards.get_active())
            settings.set_string("hover-effect", value["key"])

    rotate.connect("notify::active", save_hover); cards.connect("notify::active", save_hover)
    signals.extend([settings.connect("changed::hover-effect", hover_changed),settings.connect("changed::enabled", hover_changed)])
    hover_changed()
    speed = builder.get_object("animation_speed_row")

    def sensitive(*_args):
        speed.set_sensitive(settings.get_boolean("enabled") and settings.get_string("animation") != "none")

    signals.extend([settings.connect("changed::animation", sensitive), settings.connect("changed::enabled", sensitive)])
    sensitive()
    on_window_close(window, lambda _window: [settings.disconnect(signal) for signal in signals])
