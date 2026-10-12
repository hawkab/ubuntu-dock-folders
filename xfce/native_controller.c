/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

#include "python_runtime.h"
#include <pygobject.h>
#include "native_controller.h"

/* Keep the interpreter alive while panels create and remove native widgets. */
struct NativeController {
    PyObject *instance;
};

static void call(NativeController *controller, const char *method) {
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *result = PyObject_CallMethod(controller->instance, method, NULL);
    if (!result)
        PyErr_Print();
    Py_XDECREF(result);
    PyGILState_Release(state);
}

NativeController *native_controller_new(GtkWidget *plugin, int size, int orientation,
                                        const char *path) {
    if (!plugin || !path || !dock_folders_python_initialize())
        return NULL;
    NativeController *controller = NULL;
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *gobject = pygobject_init(-1, -1, -1);
    PyObject *directory = PyUnicode_FromString(path);
    PyObject *module = NULL, *type = NULL, *wrapper = NULL, *instance = NULL, *box = NULL;
    if (!gobject || !directory || PyList_Insert(PySys_GetObject("path"), 0, directory) < 0)
        goto finish;
    module = PyImport_ImportModule("native_host");
    if (!module)
        goto finish;
    type = PyObject_GetAttrString(module, "NativeHost");
    wrapper = pygobject_new(G_OBJECT(plugin));
    if (!type || !wrapper)
        goto finish;
    instance = PyObject_CallFunction(type, "Oii", wrapper, size, orientation);
    if (!instance)
        goto finish;
    box = PyObject_GetAttrString(instance, "box");
    if (!box || !pygobject_check(box, &PyGObject_Type) || !GTK_IS_WIDGET(pygobject_get(box)))
        goto finish;
    gtk_container_add(GTK_CONTAINER(plugin), GTK_WIDGET(pygobject_get(box)));
    controller = g_new0(NativeController, 1);
    controller->instance = instance;
    instance = NULL;
finish:
    if (PyErr_Occurred())
        PyErr_Print();
    Py_XDECREF(box);
    Py_XDECREF(instance);
    Py_XDECREF(wrapper);
    Py_XDECREF(type);
    Py_XDECREF(module);
    Py_XDECREF(directory);
    Py_XDECREF(gobject);
    PyGILState_Release(state);
    return controller;
}

void native_controller_layout(NativeController *controller, int size, int orientation) {
    PyGILState_STATE state = PyGILState_Ensure();
    PyObject *result = PyObject_CallMethod(controller->instance, "layout", "ii", size, orientation);
    if (!result)
        PyErr_Print();
    Py_XDECREF(result);
    PyGILState_Release(state);
}

void native_controller_configure(NativeController *controller) {
    call(controller, "preferences");
}

void native_controller_free(NativeController *controller) {
    if (!controller)
        return;
    call(controller, "shutdown");
    PyGILState_STATE state = PyGILState_Ensure();
    Py_DECREF(controller->instance);
    PyGILState_Release(state);
    g_free(controller);
}
