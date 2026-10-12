/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

#define _GNU_SOURCE
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/mman.h>
#include <unistd.h>
#include "virtual-pointer.h"
#include "virtual-keyboard.h"

static struct zwlr_virtual_pointer_manager_v1 *manager;
static struct zwp_virtual_keyboard_manager_v1 *keyboards;
static struct wl_seat *seat;

static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    (void)data;
    (void)version;
    if (strcmp(interface, "zwlr_virtual_pointer_manager_v1") == 0)
        manager = wl_registry_bind(registry, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
    else if (strcmp(interface, "zwp_virtual_keyboard_manager_v1") == 0)
        keyboards = wl_registry_bind(registry, name, &zwp_virtual_keyboard_manager_v1_interface, 1);
    else if (strcmp(interface, "wl_seat") == 0)
        seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
}

static void removed(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data;
    (void)registry;
    (void)name;
}

/* Send pointer gestures only to an isolated headless test compositor. */
int main(void) {
    const char *marker = getenv("DOCK_FOLDERS_TEST_SESSION");
    const char *backends = getenv("WLR_BACKENDS");
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    const char *home = getenv("HOME");
    if (!marker || !backends || strcmp(backends, "headless") != 0 ||
        !runtime || !home || strncmp(runtime, home, strlen(home)) != 0)
        return 2;
    struct wl_display *display = wl_display_connect(NULL);
    if (!display)
        return 3;
    struct wl_registry *registry = wl_display_get_registry(display);
    static const struct wl_registry_listener listener = {global, removed};
    wl_registry_add_listener(registry, &listener, NULL);
    wl_display_roundtrip(display);
    if (!manager)
        return 4;
    struct zwp_virtual_keyboard_v1 *keyboard = NULL;
    if (keyboards && seat) {
        struct xkb_context *context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
        struct xkb_keymap *keymap = xkb_keymap_new_from_names(context, NULL, XKB_KEYMAP_COMPILE_NO_FLAGS);
        char *keys = xkb_keymap_get_as_string(keymap, XKB_KEYMAP_FORMAT_TEXT_V1);
        int fd = memfd_create("private-test-keymap", MFD_CLOEXEC);
        if (fd < 0 || write(fd, keys, strlen(keys)+1) < 0)
            return 5;
        keyboard = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(keyboards, seat);
        zwp_virtual_keyboard_v1_keymap(keyboard, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, strlen(keys)+1);
        wl_display_roundtrip(display);
        close(fd);
        free(keys);
        xkb_keymap_unref(keymap);
        xkb_context_unref(context);
    }
    struct zwlr_virtual_pointer_v1 *pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, NULL);
    char operation;
    unsigned int x, y, width, height;
    while (scanf(" %c", &operation) == 1) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        uint32_t timestamp = (uint32_t)(now.tv_sec * 1000 + now.tv_nsec / 1000000);
        if (operation == 'm' && scanf("%u %u %u %u", &x, &y, &width, &height) == 4)
            zwlr_virtual_pointer_v1_motion_absolute(pointer, timestamp, x, y, width, height);
        else if (operation == 'b' && scanf("%u", &x) == 1)
            zwlr_virtual_pointer_v1_button(pointer, timestamp, 0x110, x);
        else
            break;
        zwlr_virtual_pointer_v1_frame(pointer);
        if (wl_display_roundtrip(display) < 0)
            break;
    }
    zwlr_virtual_pointer_v1_destroy(pointer);
    if (keyboard)
        zwp_virtual_keyboard_v1_destroy(keyboard);
    zwlr_virtual_pointer_manager_v1_destroy(manager);
    wl_registry_destroy(registry);
    wl_display_disconnect(display);
    return 0;
}
