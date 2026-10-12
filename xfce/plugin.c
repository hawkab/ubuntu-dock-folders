/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

#include <gio/gio.h>
#include <gdk/gdkx.h>
#include <gtk/gtkx.h>
#include <libxfce4panel/libxfce4panel.h>
#include <string.h>
#include <libintl.h>
#include "native_controller.h"

#define GETTEXT_PACKAGE "ubuntu-dock-folders"
#include <glib/gi18n.h>

#ifndef DOCK_FOLDERS_BACKEND
#define DOCK_FOLDERS_BACKEND "/usr/share/ubuntu-dock-folders/xfce/panel.py"
#endif

/* Host folder controls for the panel's active display backend. */
typedef struct {
    XfcePanelPlugin *plugin;
    GtkWidget *socket;
    GSubprocess *controller;
    NativeController *native;
    guint start_source;
    guint layout_source;
} FolderPlugin;

static void written(GObject *stream, GAsyncResult *result, gpointer data) {
    (void)data;
    GError *error = NULL;
    g_output_stream_write_bytes_finish(G_OUTPUT_STREAM(stream), result, &error);
    g_clear_error(&error);
}

static void send_message(FolderPlugin *folders, const gchar *message) {
    if (!folders->controller)
        return;
    GOutputStream *stream = g_subprocess_get_stdin_pipe(folders->controller);
    if (g_output_stream_has_pending(stream))
        return;
    GBytes *bytes = g_bytes_new(message, strlen(message));
    g_output_stream_write_bytes_async(stream, bytes, G_PRIORITY_DEFAULT, NULL, written, NULL);
    g_bytes_unref(bytes);
}

static void send_layout(FolderPlugin *folders) {
    if (folders->native) {
        native_controller_layout(folders->native, xfce_panel_plugin_get_size(folders->plugin),
                                 xfce_panel_plugin_get_orientation(folders->plugin));
        return;
    }
    gchar *message = g_strdup_printf("layout %d %d\n",
        xfce_panel_plugin_get_size(folders->plugin),
        xfce_panel_plugin_get_orientation(folders->plugin));
    send_message(folders, message);
    g_free(message);
}

static gboolean layout_ready(gpointer data) {
    FolderPlugin *folders = data;
    folders->layout_source = 0;
    send_layout(folders);
    return G_SOURCE_REMOVE;
}

static void queue_layout(FolderPlugin *folders) {
    if (!folders->layout_source)
        folders->layout_source = g_idle_add(layout_ready, folders);
}

static gboolean size_changed(XfcePanelPlugin *plugin, gint size, FolderPlugin *folders) {
    (void)plugin;
    (void)size;
    queue_layout(folders);
    return TRUE;
}

static void orientation_changed(XfcePanelPlugin *plugin, GtkOrientation orientation,
                                FolderPlugin *folders) {
    (void)plugin;
    (void)orientation;
    queue_layout(folders);
}

static void start_controller(GtkWidget *socket, FolderPlugin *folders) {
    if (folders->controller)
        return;
    gchar *id = g_strdup_printf("%lu", (gulong)gtk_socket_get_id(GTK_SOCKET(socket)));
    gchar *size = g_strdup_printf("%d", xfce_panel_plugin_get_size(folders->plugin));
    gchar *orientation = g_strdup_printf("%d", xfce_panel_plugin_get_orientation(folders->plugin));
    GError *error = NULL;
    folders->controller = g_subprocess_new(G_SUBPROCESS_FLAGS_STDIN_PIPE, &error,
        "/usr/bin/python3", DOCK_FOLDERS_BACKEND, "--socket", id,
        "--size", size, "--orientation", orientation, NULL);
    if (error) {
        g_warning("Cannot start Dock folders: %s", error->message);
        g_error_free(error);
    }
    g_free(id);
    g_free(size);
    g_free(orientation);
}

static gboolean plug_removed(GtkSocket *socket, FolderPlugin *folders) {
    (void)socket;
    (void)folders;
    return TRUE;
}

static gboolean start_embedded(gpointer data) {
    FolderPlugin *folders = data;
    folders->start_source = 0;
    gtk_widget_realize(folders->socket);
    start_controller(folders->socket, folders);
    queue_layout(folders);
    return G_SOURCE_REMOVE;
}

static void configure(XfcePanelPlugin *plugin, FolderPlugin *folders) {
    (void)plugin;
    if (folders->native) {
        native_controller_configure(folders->native);
        return;
    }
    send_message(folders, "preferences\n");
}

static void free_data(XfcePanelPlugin *plugin, FolderPlugin *folders) {
    (void)plugin;
    if (folders->start_source)
        g_source_remove(folders->start_source);
    if (folders->layout_source)
        g_source_remove(folders->layout_source);
    if (folders->controller) {
        g_subprocess_force_exit(folders->controller);
        g_clear_object(&folders->controller);
    }
    native_controller_free(folders->native);
    g_free(folders);
}

static void construct(XfcePanelPlugin *plugin) {
    FolderPlugin *folders = g_new0(FolderPlugin, 1);
    folders->plugin = plugin;
    gboolean x11 = GDK_IS_X11_DISPLAY(gtk_widget_get_display(GTK_WIDGET(plugin)));
    if (!x11) {
        gchar *directory = g_path_get_dirname(DOCK_FOLDERS_BACKEND);
        folders->native = native_controller_new(GTK_WIDGET(plugin),
            xfce_panel_plugin_get_size(plugin), xfce_panel_plugin_get_orientation(plugin), directory);
        g_free(directory);
    }
    if (!x11 && !folders->native) {
        bindtextdomain(GETTEXT_PACKAGE, "/usr/share/ubuntu-dock-folders/xfce/shared/locale");
        bind_textdomain_codeset(GETTEXT_PACKAGE, "UTF-8");
        GtkWidget *label = gtk_label_new(_("Dock folders"));
        gtk_widget_set_tooltip_text(label, _("Could not open the application"));
        gtk_container_add(GTK_CONTAINER(plugin), label);
        xfce_panel_plugin_set_small(plugin, FALSE);
        gtk_widget_show_all(GTK_WIDGET(plugin));
        g_free(folders);
        return;
    }
    if (x11) {
        folders->socket = gtk_socket_new();
        gtk_widget_set_size_request(folders->socket, 1, 1);
        gtk_container_add(GTK_CONTAINER(plugin), folders->socket);
        g_signal_connect(folders->socket, "plug-removed", G_CALLBACK(plug_removed), folders);
    }
    xfce_panel_plugin_set_small(plugin, FALSE);
    xfce_panel_plugin_set_expand(plugin, TRUE);
    xfce_panel_plugin_menu_show_configure(plugin);
    g_signal_connect(plugin, "size-changed", G_CALLBACK(size_changed), folders);
    g_signal_connect(plugin, "orientation-changed", G_CALLBACK(orientation_changed), folders);
    g_signal_connect(plugin, "configure-plugin", G_CALLBACK(configure), folders);
    g_signal_connect(plugin, "free-data", G_CALLBACK(free_data), folders);
    gtk_widget_show_all(GTK_WIDGET(plugin));
    if (x11)
        folders->start_source = g_idle_add(start_embedded, folders);
}

XFCE_PANEL_PLUGIN_REGISTER(construct)
