// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/* Add folder preferences to Ubuntu Settings through the user-local launcher. */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <gio/gio.h>
#include <libintl.h>
#include "preferences-host.h"

#define GETTEXT_DOMAIN "ubuntu-dock-folders"
#define _(text) dgettext(GETTEXT_DOMAIN, text)

typedef GObject GtkWidget;
extern GObject *gtk_widget_get_template_child(GtkWidget *, GType, const char *);
extern GtkWidget *gtk_widget_get_root(GtkWidget *);
extern GtkWidget *gtk_image_new_from_icon_name(const char *);
extern void gtk_window_present(GObject *);
extern void gtk_window_destroy(GObject *);
extern GtkWidget *adw_action_row_new(void);
extern void adw_preferences_row_set_title(GObject *, const char *);
extern void adw_action_row_set_subtitle(GObject *, const char *);
extern void adw_action_row_add_suffix(GObject *, GtkWidget *);
extern void adw_preferences_group_add(GObject *, GtkWidget *);

__attribute__((constructor)) static void scope_preload(void) {
    const char *original = g_getenv("DOCK_GROUPS_PRELOAD_ORIGINAL");
    if (original && *original) g_setenv("LD_PRELOAD", original, TRUE);
    else g_unsetenv("LD_PRELOAD");
    g_unsetenv("DOCK_GROUPS_PRELOAD_ORIGINAL");
}

static void weak_ref_free(gpointer data) {
    g_weak_ref_clear(data);
    g_free(data);
}

static void window_unrealized(GObject *window, GObject *row) {
    (void) window;
    GWeakRef *ref = g_object_get_data(row, "dock-groups-window");
    if (ref) g_weak_ref_set(ref, NULL);
}

static void open_preferences(GObject *row, gpointer unused) {
    (void) unused;
    g_autofree char *filename = g_build_filename(g_getenv("DOCK_GROUPS_DATA"), "preferences.ui", NULL);
    if (!g_file_test(filename, G_FILE_TEST_IS_REGULAR)) {
        g_object_set(row, "visible", FALSE, NULL);
        return;
    }
    GWeakRef *window_ref = g_object_get_data(row, "dock-groups-window");
    if (window_ref) {
        g_autoptr(GObject) existing = g_weak_ref_get(window_ref);
        if (existing) { gtk_window_present(existing); return; }
    }
    g_autoptr(GObject) window = dock_preferences_open(gtk_widget_get_root(row), g_getenv("DOCK_GROUPS_DATA"));
    if (!window) return;
    if (!window_ref) {
        window_ref = g_new0(GWeakRef, 1);
        g_weak_ref_init(window_ref, NULL);
        g_object_set_data_full(row, "dock-groups-window", window_ref, weak_ref_free);
    }
    g_weak_ref_set(window_ref, window);
    g_signal_connect_object(window, "unrealize", G_CALLBACK(window_unrealized), row, 0);
    gtk_window_present(window);
}

static gboolean open_preferences_idle(gpointer row) {
    g_object_set_data(row, "dock-groups-open-pending", NULL);
    if (gtk_widget_get_root(row)) open_preferences(row, NULL);
    return G_SOURCE_REMOVE;
}

static void (*panel_set_property)(GObject *, guint, const GValue *, GParamSpec *);

static void set_panel_property(GObject *panel, guint id, const GValue *value, GParamSpec *pspec) {
    GObject *row = g_object_get_data(panel, "dock-groups-row");
    if (row && g_str_equal(pspec->name, "parameters")) {
        GVariant *parameters = g_value_get_variant(value);
        if (parameters && g_variant_n_children(parameters)) {
            g_autoptr(GVariant) first = g_variant_get_child_value(parameters, 0);
            g_autoptr(GVariant) argument = g_variant_get_variant(first);
            if (g_variant_is_of_type(argument, G_VARIANT_TYPE_STRING) &&
                g_str_equal(g_variant_get_string(argument, NULL), "dock-groups")) {
                if (!g_object_get_data(row, "dock-groups-open-pending")) {
                    g_object_set_data(row, "dock-groups-open-pending", GINT_TO_POINTER(1));
                    g_idle_add_full(G_PRIORITY_DEFAULT_IDLE, open_preferences_idle,
                        g_object_ref(row), g_object_unref);
                }
                return;
            }
        }
    }
    panel_set_property(panel, id, value, pspec);
}

static void companion_changed(GFileMonitor *monitor, GFile *file, GFile *other,
                              GFileMonitorEvent event, GObject *row) {
    (void) monitor;
    (void) other;
    (void) event;
    g_autofree char *filename = g_file_get_path(file);
    if (g_file_test(filename, G_FILE_TEST_IS_REGULAR)) return;
    g_object_set(row, "visible", FALSE, NULL);
    GWeakRef *ref = g_object_get_data(row, "dock-groups-window");
    if (ref) {
        g_autoptr(GObject) window = g_weak_ref_get(ref);
        if (window) gtk_window_destroy(window);
    }
}

void gtk_widget_init_template(GtkWidget *widget) {
    static void (*original)(GtkWidget *) = NULL;
    if (!original) original = dlsym(RTLD_NEXT, "gtk_widget_init_template");
    original(widget);
    if (g_strcmp0(G_OBJECT_TYPE_NAME(widget), "CcUbuntuPanel") != 0) return;
    const char *data = g_getenv("DOCK_GROUPS_DATA");
    if (!data) return;
    g_autofree char *filename = g_build_filename(data, "preferences.ui", NULL);
    if (!g_file_test(filename, G_FILE_TEST_IS_REGULAR)) return;
    g_autofree char *locale_directory = g_build_filename(data, "locale", NULL);
    bindtextdomain(GETTEXT_DOMAIN, locale_directory);
    bind_textdomain_codeset(GETTEXT_DOMAIN, "UTF-8");
    GObject *group = gtk_widget_get_template_child(widget, G_OBJECT_TYPE(widget), "dock_preferences_group");
    if (!group || g_object_get_data(group, "dock-groups-added")) return;
    GtkWidget *row = adw_action_row_new();
    adw_preferences_row_set_title(row, _("Dock folders"));
    adw_action_row_set_subtitle(row, _("Application folders, appearance, and animation"));
    g_object_set(row, "activatable", TRUE, "focusable", TRUE, NULL);
    adw_action_row_add_suffix(row, gtk_image_new_from_icon_name("go-next-symbolic"));
    g_signal_connect(row, "activated", G_CALLBACK(open_preferences), NULL);
    adw_preferences_group_add(group, row);
    g_autoptr(GFile) file = g_file_new_for_path(filename);
    GFileMonitor *monitor = g_file_monitor_file(file, G_FILE_MONITOR_NONE, NULL, NULL);
    if (monitor) {
        g_signal_connect_object(monitor, "changed", G_CALLBACK(companion_changed), row, 0);
        g_object_set_data_full(G_OBJECT(row), "dock-groups-monitor", monitor, g_object_unref);
    }
    g_object_set_data(group, "dock-groups-added", GINT_TO_POINTER(1));
    g_object_set_data(G_OBJECT(widget), "dock-groups-row", row);
    if (!panel_set_property) {
        GParamSpec *parameters = g_object_class_find_property(G_OBJECT_GET_CLASS(widget), "parameters");
        if (parameters) {
            GObjectClass *owner = g_type_class_peek(parameters->owner_type);
            panel_set_property = owner->set_property;
            owner->set_property = set_panel_property;
        }
    }
}
