# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Attach live dock and opening previews to GTK's general settings tabs."""

import json
import sys
from gi.repository import Gio, GLib, Gtk
from settings import ROOT
from preferences_binding import CONTRACT
from preview_paint import PreviewPaint
from i18n import _
from window_lifecycle import on_window_close
sys.path.insert(0,str(ROOT/"adapters"))
from runtime import CoreRuntime


class SettingsPreview(Gtk.DrawingArea):
    """Render shared geometry; animate only while hovered or explicitly replaying."""

    def __init__(self, settings, core, mode, desktop):
        super().__init__(hexpand=True,content_height=214)
        self.settings,self.core,self.mode,self.desktop=settings,core,mode,desktop
        self.paint=PreviewPaint(self)
        self.scene,self.card,self.frame=None,None,None
        self.tick,self.phase,self.hover=0,None,0
        self.hover_target,self.hover_start=0,0
        self.orbit,self.orbit_last,self.hovered=0.,0,False
        self.orbit_velocity=0.
        self.apps=self.sample_apps()
        self.set_draw_func(self.draw)
        self.set_tooltip_text(_("Dock icon preview") if mode=="dock" else _("Open folder preview"))
        motion=Gtk.EventControllerMotion()
        motion.connect("enter",lambda *_args:self.hover_to(1))
        motion.connect("leave",lambda *_args:self.hover_to(0))
        self.add_controller(motion)
        self.connect("map",lambda *_args:self.sync_motion())
        self.connect("unmap",lambda *_args:self.close())

    def values(self):
        return {item["name"]:self.settings.get_value(item["key"]).unpack() for item in CONTRACT["preferences"]}

    def sample_apps(self):
        """Resolve examples once, outside drawing and animation callbacks."""
        groups=json.loads(self.settings.get_string("groups"))
        apps=next((group["apps"] for group in groups.values() if group.get("apps")),[])
        return apps or [{"desktop":info.get_id(),"label":info.get_name()} for info in Gio.AppInfo.get_all()
                       if info.get_id() and info.should_show() and not info.get_id().startswith("local.groups.")][:3]

    def refresh(self, _settings=None, key=None):
        if key=="groups":self.apps=self.sample_apps()
        self.phase=None
        self.scene,self.card,self.frame=None,None,None
        self.queue_draw()
        self.sync_motion()

    def orbit_request(self, elapsed=0):
        return {"angle":self.orbit,"velocity":self.orbit_velocity,"elapsed":elapsed,"values":self.values(),"hovered":self.hovered,
            "allowed":self.mode=="dock" and self.get_mapped()
                and Gtk.Settings.get_default().get_property("gtk-enable-animations")}

    def sync_motion(self):
        if self.phase or self.hover!=self.hover_target or self.core.call("orbitFrame",self.orbit_request())["active"]:
            self.animate()

    def hover_to(self, value):
        self.hovered=bool(value)
        if self.mode=="dock" and self.settings.get_boolean("enabled") and self.settings.get_string("hover-effect")!="none":
            self.hover_target,self.hover_origin,self.hover_start=value,self.hover,GLib.get_monotonic_time()
        self.sync_motion()

    def replay(self):
        if not self.settings.get_boolean("enabled") or self.settings.get_string("animation")=="none":return
        self.phase,self.started="closing",GLib.get_monotonic_time()
        self.animate()

    def animate(self):
        if not self.tick:
            self.orbit_last=GLib.get_monotonic_time()
            self.tick=self.add_tick_callback(self.advance)

    def advance(self, _widget, _clock):
        now=GLib.get_monotonic_time()
        orbit=self.core.call("orbitFrame",self.orbit_request((now-self.orbit_last)/1000))
        self.orbit_last=now
        self.orbit_velocity=orbit["velocity"]
        if self.orbit!=orbit["angle"]:
            self.scene=None
        self.orbit=orbit["angle"]
        if self.hover!=self.hover_target:
            duration=self.core.call("hoverDuration",self.settings.get_int("hover-speed"))
            p=min(1,(now-self.hover_start)/(duration*1000)) if duration else 1
            progress=self.hover_origin+(self.hover_target-self.hover_origin)*(1-(1-p)**3)
            self.orbit=self.core.call("orbitHoverFrame",{"angle":self.orbit,"velocity":self.orbit_velocity,
                "previous":self.hover,"progress":progress,"values":self.values()})["angle"]
            self.hover=progress
            self.scene=None
        if self.phase and self.scene:
            effect=next(item for item in CONTRACT["animations"] if item["key"]==self.settings.get_string("animation"))
            duration=effect["duration"]*100/self.settings.get_int("animation-speed")
            p=min(1,(now-self.started)/max(1,duration*1000))
            self.frame=self.core.call("settingsPreviewFrame",{"scene":self.scene,"time":p,"opening":self.phase=="opening"})
            if p==1:
                if self.phase=="closing":self.phase,self.started="opening",now
                else:self.phase,self.frame=None,None
        self.queue_draw()
        if self.phase or self.hover!=self.hover_target or orbit["active"]:return GLib.SOURCE_CONTINUE
        self.tick=0
        return GLib.SOURCE_REMOVE

    def draw(self, _widget, context, width, height):
        if width<1 or height<1:return
        if not self.scene or getattr(self,"dimensions",None)!=(width,height):
            self.scene=self.core.call("settingsPreview",{"values":self.values(),"apps":self.apps,"name":_("Dock folders"),
                "width":width,"height":height,"mode":self.mode,"hover":self.hover,"orbit":self.orbit,"labels":self.desktop!="plasma"})
            self.dimensions=width,height
            self.card=None
        self.paint.commands(context,self.scene["background"])
        if self.frame:
            if self.card is None:self.card=self.paint.surface(self.scene,width,height)
            self.paint.mesh(context,self.card,self.frame)
        else:self.paint.commands(context,self.scene["commands"])

    def close(self):
        if self.tick:self.remove_tick_callback(self.tick)
        self.tick=0
        self.orbit_velocity=0.


def attach_previews(builder, settings, window, desktop):
    core=CoreRuntime(ROOT)
    previews=[SettingsPreview(settings,core,mode,desktop) for mode in ("dock","popup")]
    for preview in previews:builder.get_object(preview.mode+"_preview_box").append(preview)
    content=Gtk.Box(spacing=6)
    content.append(Gtk.Image(icon_name="media-playback-start-symbolic"))
    content.append(Gtk.Label(label=_("Preview animation")))
    button=Gtk.Button(child=content,halign=Gtk.Align.CENTER)
    button.set_name("preview-animation")
    button.connect("clicked",lambda *_args:previews[1].replay())
    builder.get_object("popup_preview_box").append(button)
    def refresh(settings,key=None):
        for preview in previews:preview.refresh(settings,key)
        button.set_sensitive(settings.get_boolean("enabled") and settings.get_string("animation")!="none")
    signal=settings.connect("changed",refresh)
    refresh(settings)
    def close(_window):
        settings.disconnect(signal)
        for preview in previews:preview.close()
        core.close()
        return False
    on_window_close(window,close)
    window._settings_previews=previews
    return core
