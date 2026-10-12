/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

#include "python_runtime.h"
#include <pygobject.h>
#include "preferences-host.h"

GObject *dock_preferences_open(GObject *parent, const char *extension_path) {
    if (!parent || !extension_path || !dock_folders_python_initialize()) return NULL;
    GObject *window = NULL;
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *gobject = pygobject_init(-1, -1, -1);
    g_autofree char *app_path = g_build_filename(extension_path, "app", NULL);
    PyObject *path = PyUnicode_FromString(app_path);
    PyObject *module = NULL, *open = NULL, *wrapper = NULL, *result = NULL;
    if (!gobject || !path || PyList_Insert(PySys_GetObject("path"), 0, path) < 0) goto finish;
    module = PyImport_ImportModule("global_preferences");
    if (!module) goto finish;
    open = PyObject_GetAttrString(module, "open_embedded");
    wrapper = pygobject_new(parent);
    if (!open || !wrapper) goto finish;
    result = PyObject_CallFunctionObjArgs(open, wrapper, NULL);
    if (result && pygobject_check(result, &PyGObject_Type))
        window = g_object_ref(pygobject_get(result));
finish:
    if (PyErr_Occurred()) PyErr_Print();
    Py_XDECREF(result);
    Py_XDECREF(wrapper);
    Py_XDECREF(open);
    Py_XDECREF(module);
    Py_XDECREF(path);
    Py_XDECREF(gobject);
    PyGILState_Release(state);
    return window;
}
