// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';

/** Check continuous, hover-only and paused motion on real dock actors. */
export async function checkOrbitMotion(folders, key, until, assert) {
    const record = () => [...folders._icons.values()].find(item => item.group.key===key && item.icon.mapped);
    const actor = () => record()?.icon.icon.icon;
    const glyphAngles = () => actor().get_children().slice(1).map(item => item.rotation_angle_z+item.get_child().rotation_angle_z);
    const positions = () => actor().get_children().slice(1).map(item => [item.x,item.y]);
    folders._settings.set_string('hover-effect','none');
    folders._settings.set_int('orbit-speed',90);
    await until(() => actor()?._orbit.timer, 'Continuous orbit did not start');
    const first = actor()._orbit.angle, glyphs = glyphAngles(), initialPositions = positions();
    await Scripting.sleep(150);
    assert(actor()._orbit.angle!==first,'Continuous orbit did not advance');
    assert(JSON.stringify(positions())!==JSON.stringify(initialPositions),'The clock advanced but panel miniatures did not move');
    glyphAngles().forEach((angle,index)=>assert(Math.abs(angle-glyphs[index])<.001,'Orbital motion tilted an application glyph'));
    for (const [base, hover] of [[180,30],[30,180],[-180,-30],[180,-180],[-180,180]]) {
        record().icon.set_hover(false);
        folders._settings.set_int('orbit-speed',base);
        folders._settings.set_int('hover-orbit-speed',hover);
        await until(()=>Math.abs(actor()._orbit.velocity-base)<1,'Continuous speed did not settle');
        const previous=actor()._orbit.velocity;
        record().icon.set_hover(true);
        assert(actor()._orbit.velocity===previous,'Hover changed velocity instantly');
        await until(()=>Math.abs(actor()._orbit.velocity-previous)>1,'Hover did not change velocity');
        assert(Math.sign(actor()._orbit.velocity-previous)===Math.sign(hover-base),'Hover speed moved in the wrong direction');
        await until(()=>Math.abs(actor()._orbit.velocity-hover)<1,'Hover speed did not settle');
        const entered=actor()._orbit.velocity;
        record().icon.set_hover(false);
        assert(actor()._orbit.velocity===entered,'Pointer leave changed velocity instantly');
        await until(()=>Math.abs(actor()._orbit.velocity-base)<1,'Pointer leave did not restore the continuous speed');
    }
    folders._settings.set_int('orbit-speed',0);
    folders._settings.set_int('hover-orbit-speed',180);
    record().icon.set_hover(false);
    await until(()=>!actor()._orbit.timer,'Hover-only orbit did not coast to rest');
    assert(!actor()._orbit.timer,'Hover-only orbit kept running outside the icon');
    const idle = actor()._orbit.angle;
    await Scripting.sleep(150);
    assert(actor()._orbit.angle===idle,'Paused orbit reset or advanced its phase');
    record().icon.set_hover(true);
    await until(()=>actor()._orbit.timer,'Hover-only orbit did not start');
    await Scripting.sleep(150);
    const turned = actor()._orbit.angle;
    assert(turned!==idle,'Hover-only orbit did not move');
    record().icon.set_hover(false);
    assert(actor()._orbit.timer && actor()._orbit.velocity>0,'Pointer leave stopped motion instantly');
    await until(()=>!actor()._orbit.timer,'Orbit did not stop after pointer leave');
    assert(actor()._orbit.angle!==turned,'Deceleration did not advance the orbital phase');
    const stopped=actor()._orbit.angle;
    await Scripting.sleep(150);
    assert(actor()._orbit.angle===stopped,'Stopped orbit retained an active clock');
    folders._settings.set_int('hover-orbit-speed',0);
    await Scripting.sleep(250);
    assert(!actor()._orbit.timer,'Zero speeds retained an orbital timer');
    folders._settings.set_string('hover-effect','rotate-cards');
    folders._settings.set_int('hover-angle',45);
    folders._settings.set_int('hover-speed',78);
    folders._settings.set_int('orbit-speed',5);
    folders._settings.set_int('hover-orbit-speed',360);
    folders._view._closeMenus();
    await Scripting.sleep(400);
    assert(GLib.getenv('DOCK_FOLDERS_TEST_SESSION'),'Orbital pointer check requires a private desktop');
    const backend=global.stage.context?.get_backend() ?? Clutter.get_default_backend();
    const pointer=backend.get_default_seat()
        .create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
    try {
        const [x,y]=record().icon.get_transformed_position();
        const [width,height]=record().icon.get_transformed_size();
        pointer.notify_absolute_motion(GLib.get_monotonic_time(),x+width/2,y+height/2);
        await until(()=>actor()._hoverProgress===1 && actor()._orbit.velocity>350,
            ()=>`Combined hover effect did not settle: hover=${record().icon.hover}, progress=${actor()._hoverProgress}, velocity=${actor()._orbit.velocity}`);
        let shown=actor().get_children()[1].rotation_angle_z;
        pointer.notify_absolute_motion(GLib.get_monotonic_time(),global.stage.width-20,global.stage.height-20);
        for(let index=0;index<55;index++) {
            await Scripting.sleep(16);
            const next=actor().get_children()[1].rotation_angle_z;
            const delta=((next-shown+540)%360)-180;
            assert(delta>=-.01,'Returning hover effect reversed the orbital rotation: '+delta);
            shown=next;
        }
        assert(actor()._hoverProgress===0,'Combined hover effect remained delayed after pointer leave');
    } finally {
        pointer.run_dispose();
    }
    folders._settings.set_int('orbit-speed',0);
    folders._settings.set_int('hover-orbit-speed',0);
    folders._settings.set_int('hover-speed',-999);
    await Scripting.sleep(400);
    await until(()=>!actor()._orbit.timer,'Signed hover check retained its orbital clock');
    record().icon.set_hover(false);
    await until(()=>actor()._hoverProgress===0,'Signed hover did not return');
    const baseline=actor().get_children()[1].rotation_angle_z;
    record().icon.set_hover(true);
    await until(()=>actor()._hoverProgress===1,'Negative hover did not settle');
    const delta=((actor().get_children()[1].rotation_angle_z-baseline+540)%360)-180;
    assert(Math.abs(delta+45)<.01,'Negative hover speed did not reverse the temporary turn: '+delta);
    record().icon.set_hover(false);
    await until(()=>actor()._hoverProgress===0,'Negative hover did not return');
    folders._settings.set_int('hover-speed',0);
    await Scripting.sleep(400);
    record().icon.set_hover(true);
    assert(actor()._hoverProgress===1,'Zero hover speed did not apply immediately');
    record().icon.set_hover(false);
    assert(actor()._hoverProgress===0,'Zero hover speed retained animation');
    folders._settings.set_string('hover-effect','none');
    folders._settings.set_int('orbit-speed',0);
    folders._settings.set_int('hover-orbit-speed',0);
    await until(()=>!actor()._orbit.timer,'Combined hover effect retained its idle clock');
    print('GNOME: combined hover return preserves forward rotation without a delayed reversal');
    print('GNOME: visible panel movement, smooth acceleration and deceleration, upright glyphs and idle cleanup passed');
}
