// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once
#include <QRegion>
#include <functional>

class QWindow;
struct wl_registry;
struct wl_surface;
struct org_kde_kwin_blur;
struct org_kde_kwin_blur_manager;

/** Keep one Wayland blur object while updating an animated window's region. */
class WaylandBlur {
public:
    explicit WaylandBlur(std::function<void()> ready);
    ~WaylandBlur();
    /** Update the surface; return false for other display backends. */
    bool apply(QWindow *window, bool enabled, const QRegion &region);
    /** Release blur before the platform surface is destroyed. */
    void clear();
private:
    static void announced(void *data, wl_registry *registry, uint32_t name, const char *interface, uint32_t version);
    static void removed(void *data, wl_registry *registry, uint32_t name);
    std::function<void()> m_ready;
    wl_registry *m_registry = nullptr;
    org_kde_kwin_blur_manager *m_manager = nullptr;
    org_kde_kwin_blur *m_blur = nullptr;
    wl_surface *m_surface = nullptr;
    QRegion m_region;
    uint32_t m_name = 0;
};
