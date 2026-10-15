#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Grigory Olshansky

"""Build the GNOME bundle and Ubuntu package."""

import argparse
import copy
import gettext
import shutil
import subprocess
import sysconfig
import xml.etree.ElementTree as ET
from pathlib import Path

from catalog import add_legacy_developer
from package_layout import finalize
from native_build import compiler, flags as build_flags
import build_core
from localization import validate as validate_translations
from publication_files import copy_media
from package_control import description as package_description

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
DOMAIN = "ubuntu-dock-folders"
UUID = "dock-groups@local"
VERSION = subprocess.check_output(
    ["dpkg-parsechangelog", "-S", "Version"], cwd=ROOT, text=True
).strip()
APP_ID = "io.github.hawkab.UbuntuDockFolders"


def run(*args):
    subprocess.run(args, check=True)


def build():
    validate_translations()
    build_core.generate()
    extension = BUILD / "extension"
    if extension.exists():
        shutil.rmtree(extension)
    shutil.copytree(
        ROOT / "extension",
        extension,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "gschemas.compiled", "locale"),
    )
    build_core.install(extension / "core")
    DIST.mkdir(parents=True, exist_ok=True)
    for source in sorted((ROOT / "po").glob("*.po")):
        destination = extension / "locale" / source.stem / "LC_MESSAGES" / f"{DOMAIN}.mo"
        destination.parent.mkdir(parents=True, exist_ok=True)
        run("msgfmt", "--check", str(source), "-o", str(destination))
    run("glib-compile-schemas", "--strict", str(extension / "schemas"))
    extras = [
        "groupStore.js",
        "folderCommands.js",
        "folderFeedback.js",
        "dockAdapter.js",
        "folderDetails.js",
        "dockDragDrop.js",
        "dockWindows.js",
        "pwaDock.js",
        "folderView.js",
        "folderAnimation.js", "animationGeometry.js", "iconGeometry.js", "folderHover.js",
        "core", "adapters", "settingsPreview.js", "previewPaint.js", "existingFolders.js", "windowLifecycle.js",
        "app",
        "icons",
        "effects.js",
        "compat.js",
        "rendering.js", "popupSurface.js", "backdropContrast.js",
        "gridFolders.js",
        "windowPreviews.js",
        "model.js",
        "groups.json",
        "preferences.ui", "preferencesBinding.js",
    ]
    run(
        "gnome-extensions",
        "pack",
        "--force",
        "--out-dir",
        str(DIST),
        "--podir",
        str(ROOT / "po"),
        "--gettext-domain",
        DOMAIN,
        *(f"--extra-source={name}" for name in extras),
        str(extension),
    )
    native = BUILD / "integration"
    native.mkdir(parents=True, exist_ok=True)
    flags = subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "gio-2.0", "gmodule-2.0", "pygobject-3.0", "python3-embed"], text=True
    ).split()
    run(
        *compiler(),
        "-shared",
        "-fPIC",
        *build_flags("CPPFLAGS"),
        *build_flags("CFLAGS"),
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I" + str(ROOT / "native"),
        f'-DDOCK_FOLDERS_PYTHON_LIBRARY="{sysconfig.get_config_var("LDLIBRARY")}"',
        str(ROOT / "integration/settings-integration.c"),
        str(ROOT / "integration/preferences-host.c"),
        "-o",
        str(native / "settings-integration.so"),
        *flags,
        "-l:libgtk-4.so.1",
        "-l:libadwaita-1.so.0",
        "-ldl",
        *build_flags("LDFLAGS"),
    )
    shutil.copy2(ROOT / "integration/ubuntu-settings", native / "ubuntu-settings")
    (native / "ubuntu-settings").chmod(0o755)
    return extension


def package(extension, stage_only=False):
    architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    stage = BUILD / "package"
    if stage.exists():
        shutil.rmtree(stage)
    destination = stage / "usr/share/gnome-shell/extensions" / UUID
    shutil.copytree(extension, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(extension / "locale", stage / "usr/share/locale")
    shutil.copytree(BUILD / "integration", destination / "integration")
    scripts = stage / "usr/share/ubuntu-dock-folders/scripts"
    scripts.mkdir(parents=True)
    for name in ("manage.py", "gnome_provider.py", "backup.py", "install_context.py", "settings_integration.py", "desktop_presentation.py", "package_lifecycle.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    executable = stage / "usr/bin/ubuntu-dock-folders"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        '#!/usr/bin/python3\nimport runpy\nimport sys\nsys.path.insert(0, "/usr/share/ubuntu-dock-folders/scripts")\nrunpy.run_path("/usr/share/ubuntu-dock-folders/scripts/manage.py", run_name="__main__")\n'
    )
    executable.chmod(0o755)
    desktop = stage / "usr/share/applications" / f"{APP_ID}.desktop"
    desktop.parent.mkdir(parents=True)
    desktop_text = (ROOT / "packaging" / desktop.name).read_text()
    metadata = ET.parse(ROOT / "packaging" / f"{APP_ID}.metainfo.xml")
    component = metadata.getroot()
    languages = ET.SubElement(component, "languages")
    description = component.find("description")
    for language in (ROOT / "po/LINGUAS").read_text().split():
        ET.SubElement(languages, "lang", {"percentage": "100"}).text = language
        translate = gettext.translation(DOMAIN, str(extension / "locale"), [language]).gettext
        if language == "en":
            continue
        lang = {"{http://www.w3.org/XML/1998/namespace}lang": language}
        ET.SubElement(component, "summary", lang).text = translate(
            "Application folders, appearance, and animation"
        )
        for text in (
            "Drag an icon onto another to create a folder. Reorder applications inside a folder, or drag them out to move them back to the dock.",
            "Applications in a folder share one icon and a running indicator",
            "Change names, labels, colors, and wallpaper using the gear inside a folder",
        ):
            ET.SubElement(description, "p", lang).text = translate(text)
        desktop_text += f"GenericName[{language}]=" + translate("Dock folders") + "\n"
        desktop_text += (
            f"Comment[{language}]="
            + translate("Application folders, appearance, and animation")
            + "\n"
        )
    desktop.write_text(desktop_text)
    metainfo = stage / "usr/share/metainfo" / f"{APP_ID}.metainfo.xml"
    metainfo.parent.mkdir(parents=True)
    ET.indent(metadata, space="  ")
    metadata.write(metainfo, encoding="UTF-8", xml_declaration=True)
    icon = stage / "usr/share/icons/hicolor/scalable/apps" / f"{APP_ID}.svg"
    icon.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / icon.name, icon)
    for size in (32, 48, 64, 128, 256):
        raster = stage / f"usr/share/icons/hicolor/{size}x{size}/apps" / f"{APP_ID}.png"
        raster.parent.mkdir(parents=True)
        GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon), size, size, True).savev(
            str(raster), "png", [], []
        )
    documentation = stage / "usr/share/doc/ubuntu-dock-folders"
    documentation.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/copyright", documentation / "copyright")
    for name in ("README.md", "AUTHORS"):
        shutil.copy2(ROOT / name, documentation / name)
    copy_media(ROOT / "docs", documentation / "docs")
    catalog = ET.Element("components", {"version": "1.0", "origin": "ubuntu-dock-folders-local"})
    local = copy.deepcopy(component)
    add_legacy_developer(local)
    ET.SubElement(local, "pkgname").text = "ubuntu-dock-folders"
    language_attribute = "{http://www.w3.org/XML/1998/namespace}lang"
    descriptions = {}
    description = local.find("description")
    for paragraph in list(description):
        language = paragraph.attrib.pop(language_attribute, None)
        if language:
            description.remove(paragraph)
            if language not in descriptions:
                descriptions[language] = ET.SubElement(
                    local, "description", {language_attribute: language}
                )
            descriptions[language].append(paragraph)
    local.remove(local.find("translation"))
    ET.SubElement(
        local, "icon", {"type": "local"}
    ).text = f"/usr/share/icons/hicolor/128x128/apps/{APP_ID}.png"
    for media in local.findall("screenshots/screenshot/image") + local.findall(
        "screenshots/screenshot/video"
    ):
        filename = media.text.rsplit("/", 1)[-1]
        if not (documentation / "docs" / filename).is_file():
            raise RuntimeError(f"Missing screenshot or video: {filename}")
        media.text = Path("/usr/share/doc/ubuntu-dock-folders/docs", filename).as_uri()
    catalog.append(local)
    catalog_path = stage / "usr/share/swcatalog/xml" / f"{APP_ID}.xml"
    catalog_path.parent.mkdir(parents=True)
    catalog_tree = ET.ElementTree(catalog)
    ET.indent(catalog_tree, space="  ")
    catalog_tree.write(catalog_path, encoding="UTF-8", xml_declaration=True)
    control = stage / "DEBIAN"
    control.mkdir()
    (control / "prerm").write_text((ROOT / "debian/ubuntu-dock-folders.prerm").read_text().replace("#DEBHELPER#\n", ""))
    (control / "prerm").chmod(0o755)
    dependencies = "gnome-shell (>= 46), gnome-shell (<< 47) | gnome-shell (>= 50), gnome-shell (<< 51), gnome-shell-extension-ubuntu-dock, gjs, python3, python3-gi, python3-cairo, python3-gi-cairo, python3-pil, gir1.2-gtk-4.0, gir1.2-adw-1"
    dependencies += ", " + subprocess.check_output(
        ["dpkg-shlibdeps", "-O", "-e" + str(destination / "integration/settings-integration.so")],
        cwd=ROOT, text=True).strip().removeprefix("shlibs:Depends=")
    (control / "control").write_text(
        f"Package: ubuntu-dock-folders\nVersion: {VERSION}\nSection: gnome\nPriority: optional\nArchitecture: {architecture}\n"
        "Maintainer: Grigory Olshansky <hawkab@users.noreply.github.com>\n"
        f"Depends: {dependencies}\n"
        "Homepage: https://github.com/hawkab/ubuntu-dock-folders\n"
        "Description: " + package_description() + "\n"
    )
    finalize(stage, "ubuntu-dock-folders", strip_native=not stage_only)
    if stage_only:
        return
    run(
        "dpkg-deb",
        "--root-owner-group",
        "--build",
        str(stage),
        str(DIST / f"ubuntu-dock-folders_{VERSION}_{architecture}.deb"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the GNOME bundle and Ubuntu package.")
    parser.add_argument("--zip-only", action="store_true")
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    result = build()
    if not args.zip_only:
        package(result, stage_only=args.stage_only)
