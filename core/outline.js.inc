/** Return the rounded card's deformed outline for compositor blur. */
export function outline(rect, anchor, progress, edge, style, radius) {
    const points = [];
    const corners = [[rect.x + rect.width - radius, rect.y + radius, -Math.PI / 2],
                     [rect.x + rect.width - radius, rect.y + rect.height - radius, 0],
                     [rect.x + radius, rect.y + rect.height - radius, Math.PI / 2],
                     [rect.x + radius, rect.y + radius, Math.PI]];
    for (const corner of corners) {
        for (let step = 0; step <= 8; step++) {
            const angle = corner[2] + step * Math.PI / 16;
            points.push({x: corner[0] + radius * Math.cos(angle), y: corner[1] + radius * Math.sin(angle)});
        }
    }
    const outline = [];
    for (let index = 0; index < points.length; index++) {
        const start = points[index], end = points[(index + 1) % points.length];
        outline.push(start);
        if (Math.hypot(start.x - end.x, start.y - end.y) > radius * 2) {
            for (let step = 1; step < 12; step++) outline.push({x: start.x + (end.x - start.x) * step / 12,
                y: start.y + (end.y - start.y) * step / 12});
        }
    }
    return outline.map(point => {
        const mapped = deform(point, rect, anchor, progress, edge, style);
        return mapped;
    });
}
