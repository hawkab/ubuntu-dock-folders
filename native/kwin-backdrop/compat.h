// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#pragma once
#include "core/renderviewport.h"
#if __has_include("core/region.h")
#include "core/region.h"
#define DOCK_KWIN_REGIONS 1
#else
#include <QRect>
#include <QRegion>
#define DOCK_KWIN_REGIONS 0
namespace KWin {
using Region = QRegion;
using Rect = QRect;
}
#endif

/** Adapt repaint coordinates to the installed KWin SDK. */
inline KWin::Region logicalDamage(const KWin::RenderViewport &viewport, const KWin::Region &damage)
{
#if DOCK_KWIN_REGIONS
    return viewport.mapFromDeviceCoordinatesContained(damage);
#else
    Q_UNUSED(viewport)
    return damage;
#endif
}

inline KWin::Region targetClip(const KWin::RenderViewport &viewport, const KWin::Region &shape,
                              const KWin::Region &damage)
{
#if DOCK_KWIN_REGIONS
    return viewport.mapToRenderTarget(shape & logicalDamage(viewport, damage));
#else
    return viewport.mapToRenderTarget(shape & damage);
#endif
}

inline auto rectangles(const KWin::Region &region)
{
#if DOCK_KWIN_REGIONS
    return region.rects();
#else
    return region;
#endif
}
