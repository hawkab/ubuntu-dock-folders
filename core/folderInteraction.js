// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/** Resolve a folder activation or dock hit into one close/open decision. */
export function folderInteraction({current = null, target = null, anchors = [], point = null} = {}) {
    let anchorIndex = -1;
    if (target === null && point && Number.isFinite(point.x) && Number.isFinite(point.y)) {
        anchorIndex = anchors.findIndex(item => typeof item.key === 'string' && item.key &&
            [item.x, item.y, item.width, item.height].every(Number.isFinite) &&
            item.width > 0 && item.height > 0 &&
            point.x >= item.x && point.x < item.x + item.width &&
            point.y >= item.y && point.y < item.y + item.height);
        target = anchors[anchorIndex]?.key ?? null;
    }
    current = typeof current === 'string' && current ? current : null;
    target = typeof target === 'string' && target ? target : null;
    return {target, close: current, open: target !== current ? target : null, anchorIndex};
}
