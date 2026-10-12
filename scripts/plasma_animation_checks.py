# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Compare ordinary transition frames with the settled folder material."""

import json
import os
import shutil
import time
from pathlib import Path

PROBE = '''
    property int animationReviewTick: 0
    property Timer animationReview: Timer {
        interval:80; repeat:true
        onTriggered: {
            const modes=[0,1,4,5,7,8,10,3];
            const step=root.animationReviewTick++;
            const index=Math.floor(step/24);
            if(index>=modes.length) {console.log("ANIMATION_REVIEW_DONE");stop();return;}
            if(step%24===0) {
                popup.dismiss();
                Plasmoid.configuration.animation=modes[index];
                Plasmoid.configuration.animationSpeed=50;
                root.appearance("blurStrength",100);
                root.appearance("backgroundOpacity",.42);
                root.openFolder(popup.sourceDesktop,popup.findAnchor(root.fullRepresentationItem).parent);
            }
            if(step%24===12) popup.close();
        }
    }
    property Timer animationReviewDelay: Timer {
        interval:1800
        onTriggered:root.animationReview.start()
    }
'''


def instrument(source):
    return source.replace('    Component.onCompleted: {\n        properties.updateAll();',
                          PROBE+'    Component.onCompleted: {\n        properties.updateAll();')


def instrument_transition(source):
    marker = '+ ":" + (popup.surface.backgroundOpacity < .98 && !controller.currentGroup?.wallpaper ? "1" : "0")'
    return source.replace(marker, marker + ' + ":" + progress.toFixed(6) + ":" + live + ":" + animationStyle')


def verify(output, destination):
    """Check fixed blur radius, material continuity and animation endpoints."""
    from gi.repository import Gio, GLib
    from PIL import Image, ImageChops, ImageStat

    connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def call(command):
        return connection.call_sync('org.kde.KWin','/Effects','org.kde.kwin.Effects','debug',
            GLib.Variant('(ss)',('presentedframe',command)),None,Gio.DBusCallFlags.NONE,1000,None)
    call('record')
    try:
        deadline=time.monotonic()+20
        while 'ANIMATION_REVIEW_DONE' not in Path(output.name).read_text():
            if time.monotonic()>deadline: raise RuntimeError('Animation frame review did not finish')
            time.sleep(.05)
    finally:
        call('stop')
    review=Path(destination)/('animation-frames-'+os.environ['DOCK_FOLDERS_TEST_PLASMA_BACKEND'])
    review.mkdir(exist_ok=True)
    for file in review.glob('animation-*'): file.unlink()
    for file in Path(os.environ['XDG_CACHE_HOME']).glob('animation-*'): shutil.copy2(file,review/file.name)
    frames={}
    for metadata in sorted(review.glob('animation-*.json')):
        value=json.loads(metadata.read_text())
        parts=value['caption'].split(':')
        if len(parts)!=8: continue
        value.update(strength=float(parts[1]),mix=float(parts[2]),progress=float(parts[5]),
                     live=parts[6]=='true',style=int(parts[7]),file=metadata.with_suffix('.png'))
        frames.setdefault(value['style'],[]).append(value)
    results={}
    for style in (0,1,4,5,7,8,10,3):
        sequence=frames.get(style,[])
        settled=[f for f in sequence if f['live'] and f['progress']==1]
        assert settled, ('No settled frame',style)
        moving=[f for f in sequence if not f['live'] and f['progress']>0]
        if style!=3: assert len(moving)>=3, ('Animation frames missing',style,len(moving))
        if os.environ['DOCK_FOLDERS_TEST_PLASMA_BACKEND']=='wayland':
            missing=[f for f in moving if .25<f['progress']<1 and f['left']==0 and f['top']==0
                     and f['right']==f['width'] and f['bottom']==f['height']]
            assert not missing, ('Blur region disappeared during animation',style)
        assert all(f['strength']==1 for f in sequence), ('Animation changed blur radius',style)
        if style!=10: assert all(f['mix']==1 for f in sequence), ('Geometry animation faded blur',style)
        final=settled[-1]
        image=Image.open(final['file']).convert('RGB')
        box=(final['x']+final['left']+24,final['y']+final['bottom']-24,
             final['x']+final['right']-24,final['y']+final['bottom']-12)
        reference=image.crop(box)
        near=[f for f in moving if f['progress']>.97]
        changes=[]
        for frame in [*near,*settled]:
            candidate=Image.open(frame['file']).convert('RGB').crop(box)
            changes.append(sum(ImageStat.Stat(ImageChops.difference(reference,candidate)).mean)/3)
        assert changes and max(changes)<4, ('Material flashed at animation end',style,changes)
        results[style]={'movingFrames':len(moving),'settledFrames':len(settled),'largestEndChange':max(changes)}
        image.save(Path(destination)/f'plasma-animation-{style}-settled.png')
        if near:
            Image.open(near[-1]['file']).save(Path(destination)/f'plasma-animation-{style}-near-end.png')
    (Path(destination)/('plasma-animation-metrics-'+os.environ['DOCK_FOLDERS_TEST_PLASMA_BACKEND']+'.json')).write_text(json.dumps(results,indent=2))
    output.seek(0,2)
    output.write('ANIMATION_MATERIAL_PASSED '+json.dumps(results)+'\n')
    output.flush()
    print('Ordinary animation frames:',results)
