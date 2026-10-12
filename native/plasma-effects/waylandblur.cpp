// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "waylandblur.h"
#include "wayland-blur-client.h"
#include <QGuiApplication>
#include <QWindow>
#include <qpa/qplatformnativeinterface.h>
#include <cstring>
#include <wayland-client.h>

namespace {
QPlatformNativeInterface *native()
{
    return QGuiApplication::platformName() == QStringLiteral("wayland") ? qGuiApp->platformNativeInterface() : nullptr;
}
}

WaylandBlur::WaylandBlur(std::function<void()> ready) : m_ready(std::move(ready))
{
    auto platform = native();
    auto display = platform ? static_cast<wl_display *>(platform->nativeResourceForIntegration("display")) : nullptr;
    if (!display) return;
    m_registry = wl_display_get_registry(display);
    static const wl_registry_listener listener = {announced, removed};
    wl_registry_add_listener(m_registry, &listener, this);
    wl_display_flush(display);
}

WaylandBlur::~WaylandBlur()
{
    clear();
    if (m_manager) org_kde_kwin_blur_manager_destroy(m_manager);
    if (m_registry) wl_registry_destroy(m_registry);
}

void WaylandBlur::announced(void *data, wl_registry *registry, uint32_t name, const char *interface, uint32_t)
{
    auto self = static_cast<WaylandBlur *>(data);
    if (self->m_manager || std::strcmp(interface,"org_kde_kwin_blur_manager")) return;
    self->m_manager = static_cast<org_kde_kwin_blur_manager *>(wl_registry_bind(registry,name,&org_kde_kwin_blur_manager_interface,1));
    self->m_name = name;
    self->m_ready();
}

void WaylandBlur::removed(void *data, wl_registry *, uint32_t name)
{
    auto self = static_cast<WaylandBlur *>(data);
    if (name != self->m_name) return;
    self->clear();
    org_kde_kwin_blur_manager_destroy(self->m_manager);
    self->m_manager = nullptr;
    self->m_name = 0;
    self->m_ready();
}

void WaylandBlur::clear()
{
    if (m_blur) org_kde_kwin_blur_release(m_blur);
    if (m_surface && m_manager) org_kde_kwin_blur_manager_unset(m_manager,m_surface);
    m_blur = nullptr;
    m_surface = nullptr;
    m_region = {};
}

bool WaylandBlur::apply(QWindow *window, bool enabled, const QRegion &region)
{
    auto platform = native();
    if (!platform) return false;
    if (!enabled) { clear(); return true; }
    if (!m_manager) return true;
    auto surface = static_cast<wl_surface *>(platform->nativeResourceForWindow("surface",window));
    auto compositor = static_cast<wl_compositor *>(platform->nativeResourceForIntegration("compositor"));
    if (!surface || !compositor) return true;
    if (m_surface != surface) clear();
    if (m_blur && m_region == region) return true;
    if (!m_blur) {
        m_surface = surface;
        m_blur = org_kde_kwin_blur_manager_create(m_manager,surface);
    }
    auto clip = wl_compositor_create_region(compositor);
    for (const auto &rect : region) wl_region_add(clip,rect.x(),rect.y(),rect.width(),rect.height());
    org_kde_kwin_blur_set_region(m_blur,clip);
    org_kde_kwin_blur_commit(m_blur);
    wl_region_destroy(clip);
    m_region = region;
    return true;
}
