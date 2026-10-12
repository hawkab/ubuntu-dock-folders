/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/Xcomposite.h>
#include <gdk/gdkx.h>
#include <gdk-pixbuf/gdk-pixbuf.h>

/* Capture a compositor-backed window without exposing windows in front of it. */
gboolean dock_folders_capture(gulong xid, const gchar *filename) {
    GdkDisplay *gdk = gdk_display_get_default();
    if (!GDK_IS_X11_DISPLAY(gdk))
        return FALSE;
    Display *display = gdk_x11_display_get_xdisplay(gdk);
    gint event, error;
    if (!XCompositeQueryExtension(display, &event, &error))
        return FALSE;
    gdk_x11_display_error_trap_push(gdk);
    Pixmap pixmap = XCompositeNameWindowPixmap(display, xid);
    Window root;
    unsigned int width = 0, height = 0, border, depth;
    int x, y;
    gboolean valid = pixmap && XGetGeometry(display, pixmap, &root, &x, &y,
        &width, &height, &border, &depth) && width && height && width <= 8192 && height <= 8192 &&
        (guint64)width * height <= 16777216;
    XImage *image = valid ? XGetImage(display, pixmap, 0, 0, width, height, AllPlanes, ZPixmap) : NULL;
    if (pixmap)
        XFreePixmap(display, pixmap);
    XSync(display, False);
    if (gdk_x11_display_error_trap_pop(gdk) || !image) {
        if (image)
            XDestroyImage(image);
        return FALSE;
    }
    double ratio = MIN(1., MIN(360. / width, 240. / height));
    gint target_width = MAX(1, (gint)(width * ratio));
    gint target_height = MAX(1, (gint)(height * ratio));
    GdkPixbuf *preview = gdk_pixbuf_new(GDK_COLORSPACE_RGB, FALSE, 8, target_width, target_height);
    if (!preview) {
        XDestroyImage(image);
        return FALSE;
    }
    guchar *pixels = gdk_pixbuf_get_pixels(preview);
    gint stride = gdk_pixbuf_get_rowstride(preview);
    unsigned long masks[] = {image->red_mask, image->green_mask, image->blue_mask};
    if (!masks[0]) {
        masks[0] = 0xff0000; masks[1] = 0x00ff00; masks[2] = 0x0000ff;
    }
    if (!masks[1] || !masks[2]) {
        XDestroyImage(image);
        g_object_unref(preview);
        return FALSE;
    }
    for (gint row = 0; row < target_height; row++)
        for (gint col = 0; col < target_width; col++) {
            unsigned long pixel = XGetPixel(image, col * width / target_width, row * height / target_height);
            for (gint channel = 0; channel < 3; channel++) {
                unsigned long mask = masks[channel];
                gint shift = 0;
                while (!(mask & 1)) { mask >>= 1; shift++; }
                pixels[row * stride + col * 3 + channel] = ((pixel >> shift) & mask) * 255 / mask;
            }
        }
    XDestroyImage(image);
    gboolean saved = gdk_pixbuf_save(preview, filename, "png", NULL, NULL);
    g_object_unref(preview);
    return saved;
}
