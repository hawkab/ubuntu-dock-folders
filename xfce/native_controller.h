/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */
#pragma once
#include <gtk/gtk.h>

typedef struct NativeController NativeController;

/* Create a native GTK controller; return NULL on initialization failure. */
NativeController *native_controller_new(GtkWidget *plugin, int size, int orientation,
                                        const char *path);
void native_controller_layout(NativeController *controller, int size, int orientation);
void native_controller_configure(NativeController *controller);
void native_controller_free(NativeController *controller);
