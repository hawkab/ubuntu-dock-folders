# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Assemble the folder appearance window from reusable controls."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
from i18n import _
from settings import SETTINGS
from folder_preview import FolderPreview

def build_folder_window(self, group):
    window = Adw.Window(
        title=f"{_('Folder appearance')} — {group['name']}",
        default_width=600, default_height=660, modal=True
    )
    self.appearance_window = window
    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    self.window_title = Adw.WindowTitle(title=_("Folder appearance"), subtitle=group["name"])
    header.set_title_widget(self.window_title)
    toolbar.add_top_bar(header)
    window.set_content(toolbar)
    layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    toolbar.set_content(layout)
    scroll = Gtk.ScrolledWindow(
        hscrollbar_policy=Gtk.PolicyType.NEVER,
        vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        vexpand=True,
    )
    layout.append(scroll)
    clamp = Adw.Clamp(maximum_size=560, tightening_threshold=440)
    scroll.set_child(clamp)
    body = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=16,
        margin_start=24,
        margin_end=24,
        margin_top=12,
        margin_bottom=16,
    )
    clamp.set_child(body)
    general = Adw.PreferencesGroup()
    body.append(general)
    name = Adw.EntryRow(title=_("Name"), text=group["name"])

    def rename(row):
        value = row.get_text().strip()
        if value:
            self.save("name", value[:80])

    name.connect("changed", rename)
    general.add(name)
    stack = Gtk.Stack(
        transition_type=Gtk.StackTransitionType.CROSSFADE,
        transition_duration=150,
        hhomogeneous=True,
        vhomogeneous=True,
    )
    switcher = Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.CENTER)
    switcher.add_css_class("linked")
    body.append(switcher)
    body.append(stack)
    self.folder_previews = []
    pages = {}
    for mode, title in (("dock", _("On the dock")), ("popup", _("When opened"))):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        preview = FolderPreview(
            group,
            mode,
            glass=SETTINGS.get_boolean("glass"),
            font_size=SETTINGS.get_double("font-size"), core=self.core,
        )
        preview.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Dock icon preview") if mode == "dock" else _("Open folder preview")],
        )
        page.append(preview)
        self.folder_previews.append(preview)
        controls = Adw.PreferencesGroup()
        page.append(controls)
        pages[mode] = controls
        stack.add_titled(page, mode, title)
    opacity = group["dockOpacity"]
    pages["dock"].add(
        self.color_row(group, "dockColor", _("Background color"), group["dockColor"])
    )
    pages["dock"].add(self.transparency_row("dockOpacity", opacity))
    rotation_row = Adw.ActionRow(title=_("Icon rotation"))
    rotation = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, digits=0, draw_value=True,
        width_request=200, valign=Gtk.Align.CENTER,
        adjustment=Gtk.Adjustment(value=group["iconRotation"], lower=0, upper=self.appearance_range("iconRotation")[1],
                                  step_increment=self.appearance_range("iconRotation")[2], page_increment=15))
    rotation.set_name("icon-rotation")
    rotation.set_format_value_func(lambda _scale, value: f"{round(value)}°")
    rotation.update_property([Gtk.AccessibleProperty.LABEL], [_("Icon rotation")])
    rotation.connect("value-changed", lambda row: self.save("iconRotation", round(row.get_value()) % 360))
    rotation_row.add_suffix(rotation)
    pages["dock"].add(rotation_row)
    cards = Adw.SwitchRow(title=_("Always use card stack"), active=group.get("alwaysStack", False))
    cards.connect("notify::active", lambda row, _p: self.save("alwaysStack", row.get_active()))
    pages["dock"].add(cards)
    labels = Adw.SwitchRow(
        title=_("Label below the icon"), active=group["showLabel"]
    )
    labels.connect("notify::active", lambda row, _p: self.save("showLabel", row.get_active()))
    pages["dock"].add(labels)
    pages["popup"].add(self.color_row(group, "popupColor", _("Background color"), "#26262a"))
    pages["popup"].add(
        self.transparency_row(
            "backgroundOpacity",
            group["backgroundOpacity"],
        )
    )
    blur_row = Adw.ActionRow(title=_("Background blur"))
    blur = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, digits=0, draw_value=True,
        width_request=200, valign=Gtk.Align.CENTER,
        adjustment=Gtk.Adjustment(value=group["blurStrength"], lower=0, upper=self.appearance_range("blurStrength")[1],
                                  step_increment=self.appearance_range("blurStrength")[2], page_increment=10))
    blur.set_name("folder-background-blur")
    blur.set_format_value_func(lambda _scale, value: f"{round(value)}%")
    blur.update_property([Gtk.AccessibleProperty.LABEL], [_("Background blur")])
    blur.connect("value-changed", lambda row:self.save("blurStrength",round(row.get_value())))
    blur_row.add_suffix(blur)
    pages["popup"].add(blur_row)
    self.glass_hint = Gtk.Label(
        label=_("Transparency affects the background color; blur is independent."),
        visible=True,
        wrap=True,
        xalign=0,
    )
    self.glass_hint.add_css_class("caption")
    self.glass_hint.add_css_class("dim-label")
    stack.get_child_by_name("popup").append(self.glass_hint)
    self.wallpaper_row = Adw.ActionRow(title=_("Wallpaper"))
    self.wallpaper_select = Gtk.Button(label=_("Choose…"), valign=Gtk.Align.CENTER)
    self.wallpaper_select.connect("clicked", lambda _button: self.choose_wallpaper(window))
    self.wallpaper_clear = Gtk.Button(
        icon_name="user-trash-symbolic",
        tooltip_text=_("Remove wallpaper"),
        valign=Gtk.Align.CENTER,
    )
    self.wallpaper_clear.update_property(
        [Gtk.AccessibleProperty.LABEL], [_("Remove wallpaper")]
    )
    self.wallpaper_clear.add_css_class("flat")
    self.wallpaper_clear.connect("clicked", lambda _button: self.set_wallpaper(""))
    self.wallpaper_row.add_suffix(self.wallpaper_select)
    self.wallpaper_row.add_suffix(self.wallpaper_clear)
    pages["popup"].add(self.wallpaper_row)
    self.update_wallpaper_row(group)
    apply_to_all = Gtk.Button(label=_("Apply to all folders…"), halign=Gtk.Align.CENTER)
    apply_to_all.set_name("apply-appearance-to-all")
    apply_to_all.connect("clicked", lambda _button: self.confirm_apply_to_all(window))
    body.append(apply_to_all)
    system_settings = Gtk.Button(
        label=_("General folder settings"),
        halign=Gtk.Align.CENTER,
        margin_top=4,
        tooltip_text=_("Settings → Ubuntu Desktop → Dock → Dock folders"),
    )
    system_settings.add_css_class("flat")
    system_settings.get_child().add_css_class("accent")
    system_settings.connect("clicked", lambda _button: self.open_system_settings(window))
    layout.append(system_settings)
    status = Gtk.Label(
        label=_("Changes are saved automatically"), margin_top=4, margin_bottom=16
    )
    status.add_css_class("dim-label")
    status.add_css_class("caption")
    layout.append(status)
    window.set_focus(switcher.get_first_child())
    return window
