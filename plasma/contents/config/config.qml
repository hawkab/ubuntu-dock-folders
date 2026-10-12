/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

import org.kde.plasma.configuration

ConfigModel {
    ConfigCategory {
        name: i18nd("ubuntu-dock-folders", "Dock folders")
        icon: "folder-applications"
        source: "ConfigGeneral.qml"
    }
}
