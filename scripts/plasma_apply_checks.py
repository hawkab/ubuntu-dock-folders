# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise both confirmation buttons in the native Plasma appearance window."""

import copy
import json


def prepare(package, settings, apps):
    """Add private test folders and instrument the real settings component."""
    groups = json.loads(settings.get_string("groups"))
    groups["test"].update(blurStrength=37, backgroundOpacity=.18, iconRotation=60, alwaysStack=True)
    other = copy.deepcopy(groups["test"])
    other.update(id="local.groups.other", name="Other", blurStrength=100, backgroundOpacity=.95,
                 iconRotation=0, alwaysStack=False)
    other["apps"] = []
    for name in ("editor", "browser"):
        desktop = f"test.other-{name}.desktop"
        (apps / desktop).write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\n")
        other["apps"].append({"desktop":desktop, "label":name})
    groups["other"] = other
    settings.set_string("groups", json.dumps(groups))
    source = package / "contents/ui/main.qml"
    text = source.read_text().replace("    Component.onCompleted: {\n        properties.updateAll();", '''
    Timer {
        interval: 1000; running: true
        onTriggered: { root.currentKey="test"; folderSettings.show(); }
    }
    Component.onCompleted: {
        properties.updateAll();''')
    folder = package / "contents/ui/FolderSettings.qml"
    folder.write_text(folder.read_text().replace("    id: window", '''    id: window
    property int bulkTestStep: -4
    property string bulkTestBefore: ""
    function findControl(item, name) {
        if (item.objectName === name) return item;
        for (const child of item.children) { const found=findControl(child,name); if(found) return found; }
        return null;
    }
    Timer {
        interval: 250; repeat: true; running: window.visible
        onTriggered: {
            switch (window.bulkTestStep++) {
            case -4:
                const picker=window.findControl(window.contentItem,"dock-background-color");
                if(picker.color.toString()!=="#263d4a") { console.error("PALETTE_INITIAL_COLOR_FAILED");stop();return; }
                picker.clicked(); break;
            case -3:
                const activePicker=window.findControl(window.contentItem,"dock-background-color");
                const dialog=activePicker.data.find(item => item.selectedColor !== undefined);
                if(!dialog || !dialog.visible || dialog.selectedColor.toString()!=="#263d4a")
                    { console.error("PALETTE_OPEN_COLOR_FAILED");stop();return; }
                dialog.selectedColor="#397d4f";dialog.accepted();dialog.close();break;
            case -2:
                if(window.group.dockColor!=="#397d4f") {console.error("PALETTE_SAVE_FAILED");stop();return;}
                const reopened=window.findControl(window.contentItem,"dock-background-color");
                reopened.clicked();break;
            case -1:
                const colorButton=window.findControl(window.contentItem,"dock-background-color");
                const colorDialog=colorButton.data.find(item => item.selectedColor !== undefined);
                if(colorDialog.selectedColor.toString()!=="#397d4f") {console.error("PALETTE_REOPEN_FAILED");stop();return;}
                colorDialog.close();console.log("PLASMA_PALETTE_PASSED");break;
            case 0:
                window.bulkTestBefore=JSON.stringify(window.controller.state);
                window.findControl(window.contentItem,"apply-appearance-to-all").clicked(); break;
            case 1:
                if(!applyConfirmation.visible || JSON.stringify(window.controller.state)!==window.bulkTestBefore)
                    { console.error("BULK_CONFIRMATION_FAILED"); stop(); return; }
                applyConfirmation.standardButton(Kirigami.Dialog.Cancel).clicked(); break;
            case 2:
                if(applyConfirmation.visible || JSON.stringify(window.controller.state)!==window.bulkTestBefore)
                    { console.error("BULK_CANCEL_FAILED"); stop(); return; }
                window.findControl(window.contentItem,"apply-appearance-to-all").clicked(); break;
            case 3: applyConfirmation.customFooterActions[0].trigger(); break;
            case 4:
                const before=JSON.parse(window.bulkTestBefore);
                const state=window.controller.state, copied=state.groups.other;
                if(applyConfirmation.visible || copied.blurStrength!==37 || copied.backgroundOpacity!==.18
                    || copied.iconRotation!==60 || !copied.alwaysStack || copied.name!=="Other"
                    || copied.id!=="local.groups.other" || JSON.stringify(copied.apps)!==JSON.stringify(before.groups.other.apps)
                    || JSON.stringify(state.favorites)!==JSON.stringify(before.favorites)
                    || JSON.stringify(state.groups.test)!==JSON.stringify(before.groups.test))
                    console.error("BULK_APPLY_FAILED",JSON.stringify(state));
                else console.log("PLASMA_BULK_APPLY_PASSED");
                stop(); break;
            }
        }
    }'''))
    return text
