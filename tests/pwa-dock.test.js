// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const source = readFileSync(new URL('../extension/pwaDock.js',import.meta.url),'utf8')
    .replace(/^import .*;\n/gm,'').replace('export class PwaDock','class PwaDock');

test('a standalone PWA shows its windows and activates them without relaunching Chrome', () => {
    const desktop='chrome-'+ 'a'.repeat(32)+'-Default.desktop';
    let activated=0, launched=0, updates=0, modifiers=0;
    const window={has_focus:()=>false,minimized:false};
    const app={get_id:()=>desktop,get_name:()=> 'PWA',activate:()=>launched++};
    const global={display:{focus_window:window}};
    const PwaDock=runInNewContext(source+'\nPwaDock',{global,
        Main:{activateWindow:w=>{assert.equal(w,window);activated++;},overview:{hide:()=>{}}}});
    const icon={app,mapped:true,windowsCount:0,running:false,get_stage:()=>true,
        _updateRunningState:()=>{},activate:()=>{if(modifiers)launched++;else app.activate();}};
    icon.getInterestingWindows=()=>icon.getWindows();
    icon._updateWindows=()=>{updates++;icon.windowsCount=icon.getWindows().length;icon._updateRunningState();icon._updateFocusState();};
    const host={_pwaDesktops:new Set([desktop]),_windowsAdapter:{applicationWindows:()=>[window]},
        _dock:{_docks:()=>[{dash:{getAppIcons:()=>[icon]}}]}};
    const adapter=new PwaDock(host);
    adapter.decorate(icon);
    const callback=icon.activate;
    adapter.decorate(icon);
    assert.equal(icon.activate,callback);
    adapter.update();
    assert.equal(icon.running,true);
    assert.equal(icon.focused,true);
    icon.activate(1);
    assert.equal(activated,1);
    assert.equal(launched,0);
    app.activate();
    assert.equal(launched,1);
    adapter.update();
    assert.equal(updates,1);
    modifiers=2;icon.activate(1);
    assert.equal(launched,2);
});
