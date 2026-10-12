// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

.import "Core.js" as Core

/** Apply a shared folder decision to the persistent Plasma popup. */
function apply(controller, popup, decision, desktop, anchor) {
    if (decision.close && !decision.open) { popup.close(); return; }
    if (!decision.open) return;
    if (decision.close) popup.dismiss();
    controller.currentKey = decision.open;
    popup.sourceDesktop = desktop;
    popup.visualParent = anchor.iconAnchor;
    popup.open();
}

/** Activate a mapped folder from pointer, keyboard or accessibility input. */
function activate(controller, popup, desktop, anchor) {
    const key = controller.groupKey(controller.groupFor(desktop));
    if (!key) return;
    apply(controller, popup, Core.folderInteraction({current: popup.visible ? controller.currentKey : null,
        target: key}), desktop, anchor);
}

/** Route a captured animation-envelope press to the clicked dock folder. */
function press(controller, popup, point) {
    const anchors = controller.fullRepresentationItem?.folderAnchors() || [];
    const decision = Core.folderInteraction({current: popup.visible ? controller.currentKey : null,
        point, anchors});
    if (!decision.target) return false;
    const target = anchors[decision.anchorIndex].button;
    apply(controller, popup, decision, target.desktop, target);
    return true;
}
