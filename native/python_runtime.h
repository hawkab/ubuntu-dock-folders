/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */
#pragma once
#include <Python.h>
#include <gmodule.h>

#ifndef DOCK_FOLDERS_PYTHON_LIBRARY
#define DOCK_FOLDERS_PYTHON_LIBRARY "libpython3.so"
#endif

/* Initialize the shared interpreter without replacing the host's signal handlers. */
static inline gboolean dock_folders_python_initialize(void) {
    if (Py_IsInitialized()) return TRUE;
    GModule *library = g_module_open(DOCK_FOLDERS_PYTHON_LIBRARY, G_MODULE_BIND_LAZY);
    if (!library) {
        g_warning("Dock folders Python runtime: %s", g_module_error());
        return FALSE;
    }
    g_module_make_resident(library);
    Py_InitializeEx(0);
    PyEval_SaveThread();
    return TRUE;
}
