/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 Grigory Olshansky
 */

/** Advance shared orbital motion while its visible owner permits animation. */
import QtQuick
import "Core.js" as Core

Timer {
    required property var values
    property bool hovered: false
    property bool allowed: true
    property real angle: 0
    property real velocity: 0
    property real hoverProgress: 0
    property real previousProgress: 0
    property double last: 0
    interval: Core.contract.layout.orbitFrameInterval
    repeat: true
    onHoverProgressChanged: {
        const frame = Core.orbitHoverFrame({angle, velocity, previous:previousProgress, progress:hoverProgress, values});
        angle = frame.angle;
        previousProgress = frame.progress;
    }
    running: allowed && values.enabled !== false && (Core.orbitVelocity(values, hovered) !== 0 || velocity !== 0)
    onRunningChanged: {
        if (running) last = Date.now();
        else velocity = 0;
    }
    onTriggered: {
        const now = Date.now();
        const frame = Core.orbitFrame({angle, velocity, elapsed: now-last, values, hovered, allowed});
        angle = frame.angle;
        velocity = frame.velocity;
        last = now;
    }
}
