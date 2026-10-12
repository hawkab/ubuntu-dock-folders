# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise live global settings in a private Plasma configuration dialog."""


def prepare(package,text):
    import os
    translation_check = ''
    if os.environ.get("DOCK_FOLDERS_TEST_LANGUAGE") == "ru":
        translation_check = '''
                    function texts(item) {
                        var result=typeof item.text==="string" ? [item.text]:[];
                        for(const child of item.children)result=result.concat(texts(child));
                        return result;
                    }
                    const labels=texts(dockTab);
                    for(const expected of ["Скорость постоянного вращения","Скорость вращения при наведении","0 отключает соответствующий режим"])
                        if(!labels.some(label=>label.includes(expected)))throw new Error("Missing Russian orbital label: "+expected);
                    console.log("PLASMA_ORBIT_TRANSLATIONS_PASSED");
'''
    config=package/"contents/ui/ConfigGeneral.qml"
    config.write_text(config.read_text().replace("    property bool ready: false", '''
    property int testStep:0
    property var savedValues:({})
    property real savedIconSize:0
    function find(id,item){
        if(item.objectName===id)return item;
        for(const child of item.children){const found=find(id,child);if(found)return found;}
        return null;
    }
    Timer {
        interval:500;running:globalSettings.ready;repeat:true
        onTriggered:{
            try {
                if(testStep===0){
                    savedValues={enabled:cfg_enabled,customization:cfg_customization,groupIconSize:cfg_groupIconSize,
                        groupMiniIconSize:cfg_groupMiniIconSize,hoverEffect:cfg_hoverEffect,popupIconSize:cfg_popupIconSize,
                        animation:cfg_animation,animationSpeed:cfg_animationSpeed,orbitSpeed:cfg_orbitSpeed,hoverOrbitSpeed:cfg_hoverOrbitSpeed,hoverSpeed:cfg_hoverSpeed};
                    if(tabs.count!==3 || customization.y<=grouping.y)throw new Error("Header order");
                    if(globalSettings.title.length)throw new Error("Duplicate heading");
                    if(grouping.width!==customization.width)throw new Error("Unequal toggle alignment");
                    const preview=find("dock-settings-preview",dockTab);
                    if(!preview || preview.width<200)throw new Error("Missing dock preview");
                    if(sample.apps[0].desktop!=="test.terminal.desktop")throw new Error("Sample applications not loaded");
                    savedIconSize=preview.scene.commands.find(item=>item.type==="icon").size;
                    cfg_groupIconSize=200;cfg_groupMiniIconSize=300;
                    cfg_hoverEffect=Core.hoverChoice(true,true).id;
                    cfg_orbitSpeed=60;cfg_hoverOrbitSpeed=-999;
                    cfg_hoverSpeed=-999;
                }else if(testStep===1){
                    const preview=find("dock-settings-preview",dockTab);
                    if(preview.scene.commands.find(item=>item.type==="icon").size<=savedIconSize)throw new Error("Stale size");
                    const orbitalSpeed=find("hoverOrbitSpeed",dockTab);
                    if(!orbitalSpeed || orbitalSpeed.from!==-999 || orbitalSpeed.to!==999)throw new Error("Signed orbital range missing");
                    const speed=find("hoverSpeed",dockTab);
                    if(!speed || speed.from!==-999 || speed.to!==999)throw new Error("Signed hover range missing");
                    preview.hoverProgress=1;
                    if(Plasmoid.configuration.groupIconSize!==200)throw new Error("Size not saved");
                    if(Plasmoid.configuration.orbitSpeed!==60 || Plasmoid.configuration.hoverOrbitSpeed!==-999)throw new Error("Orbit speeds not saved");
                    if(Plasmoid.configuration.hoverSpeed!==-999)throw new Error("Hover speed endpoint not saved");
                    tabs.currentIndex=1;cfg_popupIconSize=80;cfg_animation=Core.animation("sheet").id;cfg_animationSpeed=100;
                }else if(testStep===2){
                    const preview=find("opened-settings-preview",openedTab);
                    if(!preview || !preview.visible || preview.scene.commands.find(item=>item.type==="icon").size!==80)throw new Error("Missing opening preview");
                    console.log("SETTINGS_PREVIEW_BACKEND",preview.software ? "software":"shader");
                    find("preview-animation",openedTab).clicked();
                }else if(testStep===3){
                    const preview=find("opened-settings-preview",openedTab);
                    if(preview.progress===1)throw new Error("Preview did not animate");
                    cfg_customization=false;
                }else if(testStep===4){
                    if(Plasmoid.configuration.customization!==false)throw new Error("Customization not saved");
                    cfg_enabled=false;
                }else if(testStep===5){
                    if(customization.enabled || find("preview-animation",openedTab).enabled)throw new Error("Disabled state ignored");
                    for(const key in savedValues)globalSettings["cfg_"+key]=savedValues[key];
                    console.log("PLASMA_SETTINGS_PASSED");stop();
                }
                testStep++;
            }catch(error){console.error("PLASMA_SETTINGS_FAILED",error);stop();}
        }
    }
    property bool ready: false'''))
    if translation_check:
        config.write_text(config.read_text().replace('                    savedIconSize=preview.scene.commands',
            translation_check+'                    savedIconSize=preview.scene.commands'))
    return text.replace("    Component.onCompleted: {\n        properties.updateAll();", '''
    Timer {interval:1500;running:true;onTriggered:Plasmoid.internalAction("configure").trigger()}
    Component.onCompleted: {
        properties.updateAll();''')
