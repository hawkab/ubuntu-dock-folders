// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/* Add folder preferences to Ubuntu Settings through the user-local launcher. */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <gio/gio.h>
#include <libintl.h>

#define GETTEXT_DOMAIN "ubuntu-dock-folders"
#define _(text) dgettext(GETTEXT_DOMAIN, text)

typedef GObject GtkWidget;
typedef GObject GtkBuilder;
extern GObject *gtk_widget_get_template_child(GtkWidget *, GType, const char *);
extern GtkWidget *gtk_widget_get_root(GtkWidget *);
extern GtkWidget *gtk_image_new_from_icon_name(const char *);
extern GtkBuilder *gtk_builder_new(void);
extern guint gtk_builder_add_from_file(GtkBuilder *, const char *, GError **);
extern void gtk_builder_set_translation_domain(GtkBuilder *, const char *);
extern GObject *gtk_builder_get_object(GtkBuilder *, const char *);
extern void gtk_window_set_transient_for(GObject *, GObject *);
extern void gtk_window_set_destroy_with_parent(GObject *, gboolean);
extern void gtk_window_present(GObject *);
extern void gtk_window_destroy(GObject *);
extern GtkWidget *adw_action_row_new(void);
extern void adw_preferences_row_set_title(GObject *, const char *);
extern void adw_action_row_set_subtitle(GObject *, const char *);
extern void adw_action_row_add_suffix(GObject *, GtkWidget *);
extern void adw_preferences_group_add(GObject *, GtkWidget *);
extern void adw_combo_row_set_selected(GObject *, guint);
extern guint adw_combo_row_get_selected(GObject *);

__attribute__((constructor)) static void scope_preload(void) {
    const char *original = g_getenv("DOCK_GROUPS_PRELOAD_ORIGINAL");
    if (original && *original) g_setenv("LD_PRELOAD", original, TRUE);
    else g_unsetenv("LD_PRELOAD");
    g_unsetenv("DOCK_GROUPS_PRELOAD_ORIGINAL");
}

static GSettings *settings_new(void) {
    const char *data = g_getenv("DOCK_GROUPS_DATA");
    if (!data) return NULL;
    g_autofree char *directory = g_build_filename(data, "schemas", NULL);
    g_autoptr(GError) error = NULL;
    g_autoptr(GSettingsSchemaSource) source = g_settings_schema_source_new_from_directory(
        directory, g_settings_schema_source_get_default(), FALSE, &error);
    if (!source) { g_warning("Dock Groups: %s", error->message); return NULL; }
    g_autoptr(GSettingsSchema) schema = g_settings_schema_source_lookup(
        source, "org.gnome.shell.extensions.dock-groups", FALSE);
    return schema ? g_settings_new_full(schema, NULL, NULL) : NULL;
}

static void animation_changed(GObject *row, GParamSpec *pspec, GSettings *settings) {
    (void) pspec;
    g_settings_set_string(settings, "animation", adw_combo_row_get_selected(row) ? "flow" : "scale");
}

static void weak_ref_free(gpointer data) {
    g_weak_ref_clear(data);
    g_free(data);
}

static void open_grid_folders(GObject *row, gpointer unused) {
    (void) row;
    (void) unused;
    g_autofree char *filename = g_build_filename(g_getenv("DOCK_GROUPS_DATA"), "app", "grid_folders.py", NULL);
    const char *argv[] = {"/usr/bin/python3", filename, NULL};
    g_autoptr(GError) error = NULL;
    g_autoptr(GSubprocess) process = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_NONE, &error);
    if (!process) g_warning("Dock Groups: %s", error->message);
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
    g_autoptr(GSettings) settings = settings_new();
    if (!settings) return;
    GtkBuilder *builder = gtk_builder_new();
    gtk_builder_set_translation_domain(builder, GETTEXT_DOMAIN);
    g_autoptr(GError) error = NULL;
    if (!gtk_builder_add_from_file(builder, filename, &error)) {
        g_warning("Dock Groups: %s", error->message);
        g_object_unref(builder); return;
    }
    GObject *window = gtk_builder_get_object(builder, "preferences_window");
    const char *keys[] = {"enabled", "customization", "glass"};
    const char *ids[] = {"enabled_row", "customization_row", "glass_row"};
    for (guint i = 0; i < G_N_ELEMENTS(keys); i++)
        g_settings_bind(settings, keys[i], gtk_builder_get_object(builder, ids[i]), "active", G_SETTINGS_BIND_DEFAULT);
    g_settings_bind(settings, "enabled", gtk_builder_get_object(builder, "customization_row"), "sensitive", G_SETTINGS_BIND_GET);
    g_settings_bind(settings, "enabled", gtk_builder_get_object(builder, "glass_row"), "sensitive", G_SETTINGS_BIND_GET);
    GObject *grid = gtk_builder_get_object(builder, "grid_folders_row");
    g_settings_bind(settings, "enabled", grid, "sensitive", G_SETTINGS_BIND_GET);
    g_signal_connect(grid, "activated", G_CALLBACK(open_grid_folders), NULL);
    GObject *animation = gtk_builder_get_object(builder, "animation_row");
    g_settings_bind(settings, "font-size", gtk_builder_get_object(builder, "font_size_row"), "value", G_SETTINGS_BIND_DEFAULT);
    g_autofree char *value = g_settings_get_string(settings, "animation");
    adw_combo_row_set_selected(animation, g_str_equal(value, "flow") ? 1 : 0);
    g_signal_connect(animation, "notify::selected", G_CALLBACK(animation_changed), settings);
    g_object_set_data_full(window, "dock-groups-settings", g_object_ref(settings), g_object_unref);
    gtk_window_set_transient_for(window, gtk_widget_get_root(row));
    gtk_window_set_destroy_with_parent(window, TRUE);
    if (!window_ref) {
        window_ref = g_new0(GWeakRef, 1);
        g_weak_ref_init(window_ref, NULL);
        g_object_set_data_full(row, "dock-groups-window", window_ref, weak_ref_free);
    }
    g_weak_ref_set(window_ref, window);
    gtk_window_present(window);
    g_object_unref(builder);
}

static gboolean open_preferences_idle(gpointer row) {
    g_object_set_data(row, "dock-groups-open-pending", NULL);
    if (gtk_widget_get_root(row)) open_preferences(row, NULL);
    return G_SOURCE_REMOVE;
}

static void subpage_changed(GObject *panel, GParamSpec *pspec, GObject *row) {
    (void) pspec;
    g_autofree char *subpage = NULL;
    g_object_get(panel, "subpage", &subpage, NULL);
    if (g_strcmp0(subpage, "dock-groups") != 0 ||
        g_object_get_data(row, "dock-groups-open-pending")) return;
    g_object_set_data(row, "dock-groups-open-pending", GINT_TO_POINTER(1));
    g_idle_add_full(G_PRIORITY_DEFAULT_IDLE, open_preferences_idle,
        g_object_ref(row), g_object_unref);
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
    g_signal_connect_object(widget, "notify::subpage", G_CALLBACK(subpage_changed), row, 0);
}
