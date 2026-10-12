# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Exercise folder selection through the native Plasma configuration selector."""

def prepare(package, apps, text):
    from gi.repository import Gio
    for name in ("editor","browser"):
        (apps/f"test.{name}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={name.title()}\nExec=true\nIcon=applications-internet\n")
    grid=Gio.Settings.new("org.gnome.desktop.app-folders")
    grid.set_strv("folder-children",["Imported"])
    source=Gio.Settings.new_with_path("org.gnome.desktop.app-folders.folder",grid.props.path+"folders/Imported/")
    source.set_string("name","Internet");source.set_boolean("translate",False)
    source.set_strv("apps",["test.editor.desktop","test.browser.desktop"])
    source.set_strv("categories",[])
    text=text.replace("    Component.onCompleted: {\n        properties.updateAll();", '''
    Timer {
        interval:1500; running:true
        onTriggered:Plasmoid.internalAction("configure").trigger()
    }
    property bool folderSawUnpin:false
    Timer {
        interval:100; running:true; repeat:true
        onTriggered:{
            if(!root.state.groups.test)return;
            const pinned=root.state.favorites.includes("local.groups.test.desktop");
            if(root.grouped("test.terminal.desktop")!==pinned){console.error("FOLDER_RUNNING_FILTER_FAILED");stop();return;}
            if(!pinned)root.folderSawUnpin=true;
            else if(root.folderSawUnpin){console.log("FOLDER_RUNNING_FILTER_PASSED");stop();}
        }
    }
    Component.onCompleted: {
        properties.updateAll();''')
    config=package/"contents/ui/ConfigGeneral.qml"
    config.write_text(config.read_text().replace("    property bool ready: false", '''
    Timer { interval:300; running:globalSettings.ready; onTriggered:tabs.currentIndex=2 }
    property bool ready: false'''))
    selector=package/"contents/ui/ExistingFolders.qml"
    selector.write_text(selector.read_text().replace("    property var folders: []", '''
    property int testStep:0
    property int waitTicks:0
    property string savedFolder:""
    Timer {
        id:cleanupTest; interval:2200
        onTriggered:{
            selector.parent.currentIndex=0;
            Qt.callLater(()=>{
                if(selector.visible)console.error("FOLDER_LIFETIME_FAILED");
                else console.log("FOLDER_LIFETIME_PASSED");
            });
        }
    }
    function button(id,item) {
        if(item.objectName===id)return item;
        for(const child of item.children){const found=button(id,child);if(found)return found;}
        return null;
    }
    Timer {
        interval:600; repeat:true; running:selector.visible
        onTriggered: {
            if(selector.pending || !selector.folders.length) {
                if(++selector.waitTicks>20){console.error("FOLDER_TIMEOUT");stop();}
                return;
            }
            const row=selector.folders.find(item=>item.id==="group:test");
            switch(selector.testStep++){
            case 0:
                if(!row?.pinned || selector.folders.length!==2){console.error("FOLDER_INITIAL_FAILED",JSON.stringify(selector.folders));stop();return;}
                selector.savedFolder=JSON.stringify(row);
                console.log("FOLDER_SELECTOR_VISIBLE");
                selector.button(row.id,selector).clicked();break;
            case 1:
                if(row?.pinned){selector.testStep--;return;}
                selector.button(row.id,selector).clicked();break;
            case 2:
                if(!row?.pinned){selector.testStep--;return;}
                if(JSON.stringify(row)!==selector.savedFolder){console.error("FOLDER_REPIN_FAILED");stop();return;}
                console.log("FOLDER_REPIN_PASSED");
                selector.button("gnome-grid:Imported",selector).clicked();break;
            case 3:
                const imported=selector.folders.find(item=>item.gridFolder==="Imported");
                if(!imported?.pinned || imported.id.startsWith("gnome-grid:")){selector.testStep--;return;}
                if(selector.folders.length!==2){console.error("FOLDER_IMPORT_FAILED");stop();return;}
                console.log("PLASMA_FOLDERS_PASSED");cleanupTest.start();stop();break;
            }
        }
    }
    property var folders: []'''))
    return text
