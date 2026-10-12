/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */
#pragma once
#include <gio/gio.h>

/* Return an owned window using the shared GTK preferences, or NULL on failure. */
GObject *dock_preferences_open(GObject *parent, const char *extension_path);
