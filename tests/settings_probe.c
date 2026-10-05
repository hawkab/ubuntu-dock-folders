// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/* Check companion removal while the real Ubuntu Settings panel is open. */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <gio/gio.h>
#include <stdlib.h>
typedef GObject GtkWidget;
extern GtkWidget *gtk_widget_get_first_child(GtkWidget *);
extern GtkWidget *gtk_widget_get_next_sibling(GtkWidget *);
extern GtkWidget *gtk_widget_get_root(GtkWidget *);
extern const char *gtk_window_get_title(GObject *);
extern gboolean gtk_window_get_modal(GObject *);
static GObject *find_row(GtkWidget *widget) {
    if (g_object_class_find_property(G_OBJECT_GET_CLASS(widget), "title")) {
        char *title = NULL;
        g_object_get(widget, "title", &title, NULL);
        gboolean found = g_strcmp0(title, "Dock folders") == 0;
        g_free(title);
        if (found) return widget;
    }
    for (GtkWidget *child = gtk_widget_get_first_child(widget); child;
         child = gtk_widget_get_next_sibling(child)) {
        GObject *row = find_row(child);
        if (row) return row;
    }
    return NULL;
}
static gboolean check_removal(gpointer row) {
    gboolean visible = TRUE;
    g_object_get(row, "visible", &visible, NULL);
    GWeakRef *ref = g_object_get_data(row, "dock-groups-window");
    GObject *window = ref ? g_weak_ref_get(ref) : NULL;
    if (window) g_object_unref(window);
    if (visible || window) return G_SOURCE_CONTINUE;
    g_print("DOCK_FOLDERS_SETTINGS_REMOVE_OK\n");
    g_application_quit(g_application_get_default());
    return G_SOURCE_REMOVE;
}

static gboolean check_panel(gpointer panel) {
    GObject *row = find_row(panel);
    if (!row || !gtk_widget_get_root(row)) return G_SOURCE_CONTINUE;
    g_signal_emit_by_name(row, "activated");
    GWeakRef *ref = g_object_get_data(row, "dock-groups-window");
    GObject *window = ref ? g_weak_ref_get(ref) : NULL;
    if (!window || g_strcmp0(gtk_window_get_title(window), "Dock folders") || !gtk_window_get_modal(window)) {
        g_printerr("SETTINGS_PROBE_FAILED\n");
        exit(1);
    }
    g_object_unref(window);
    g_print("DOCK_FOLDERS_SETTINGS_OK\n");
    char *filename = g_build_filename(g_getenv("DOCK_GROUPS_DATA"), "preferences.ui", NULL);
    GFile *file = g_file_new_for_path(filename);
    g_assert(g_file_delete(file, NULL, NULL));
    g_object_unref(file);
    g_free(filename);
    g_timeout_add_full(G_PRIORITY_DEFAULT, 50, check_removal, g_object_ref(row), g_object_unref);
    return G_SOURCE_REMOVE;
}
void gtk_widget_init_template(GtkWidget *widget) {
    static void (*original)(GtkWidget *) = NULL;
    if (!original) original = dlsym(RTLD_NEXT, "gtk_widget_init_template");
    original(widget);
    if (g_strcmp0(G_OBJECT_TYPE_NAME(widget), "CcUbuntuPanel") == 0)
        g_timeout_add_full(G_PRIORITY_DEFAULT, 100, check_panel, g_object_ref(widget), g_object_unref);
}
