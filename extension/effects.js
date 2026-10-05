// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

export function roundedPath(cr, x, y, width, height, radius) {
    cr.newSubPath();
    cr.arc(x + width - radius, y + radius, radius, -Math.PI / 2, 0);
    cr.arc(x + width - radius, y + height - radius, radius, 0, Math.PI / 2);
    cr.arc(x + radius, y + height - radius, radius, Math.PI / 2, Math.PI);
    cr.arc(x + radius, y + radius, radius, Math.PI, Math.PI * 1.5);
    cr.closePath();
}

// Mask the blurred backdrop, rather than blurring the icons or the shadow.
export const RoundedBackdrop = GObject.registerClass({GTypeName: 'DockGroupsRoundedBackdropV1'},
class RoundedBackdrop extends Clutter.ShaderEffect {
    _init() {
        super._init({shader_type: Clutter.ShaderType.FRAGMENT_SHADER});
        this._values = new Map();
        this._dimensions = new Map();
        this.set_shader_source(`
            uniform sampler2D tex;
            uniform float width;
            uniform float height;
            uniform float radius;
            void main() {
                vec2 size = vec2(width, height);
                vec2 p = cogl_tex_coord_in[0].xy * size - size * 0.5;
                vec2 q = abs(p) - (size * 0.5 - vec2(radius));
                float distance = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - radius;
                float alpha = 1.0 - smoothstep(-0.75, 0.75, distance);
                cogl_color_out = texture2D(tex, cogl_tex_coord_in[0].xy) * cogl_color_in * alpha;
            }`);
    }

    vfunc_paint_target(...args) {
        const actor = this.get_actor();
        if (!actor || !Number.isFinite(actor.width) || !Number.isFinite(actor.height) ||
            actor.width <= 0 || actor.height <= 0)
            return;
        for (const [name, number] of [['width', actor.width], ['height', actor.height],
            ['radius', Math.min(24, actor.width / 2, actor.height / 2)]]) {
            if (this._dimensions.get(name) === number)
                continue;
            let value = this._values.get(name);
            if (!value) {
                value = new GObject.Value();
                value.init(GObject.TYPE_FLOAT);
                this._values.set(name, value);
            }
            value.set_float(number);
            this.set_uniform_value(name, value);
            this._dimensions.set(name, number);
        }
        super.vfunc_paint_target(...args);
    }
});

// Deform only while animating: a tapered ribbon flows from the dock icon.
export const FlowEffect = GObject.registerClass({GTypeName: 'DockGroupsFlowV2'},
class FlowEffect extends Clutter.DeformEffect {
    _init(side) {
        super._init();
        this.side = side;
        this.progress = 1;
        this.originX = 0;
        this.originY = 0;
        this.set_n_tiles(12, 10);
    }

    vfunc_deform_vertex(width, height, vertex) {
        if (![width, height, this.originX, this.originY, this.progress].every(Number.isFinite) ||
            width <= 0 || height <= 0)
            return;
        if (vertex.tx === 0 && vertex.ty === 0) {
            const actor = this.get_actor();
            const volume = actor?.get_paint_volume();
            const origin = volume?.get_origin();
            const usable = volume && origin &&
                [origin.x, origin.y, volume.get_width(), volume.get_height()].every(Number.isFinite);
            const offsetX = usable ? Math.ceil(origin.x + volume.get_width() + .75) -
                Math.round(volume.get_width()) - 3 : -2;
            const offsetY = usable ? Math.ceil(origin.y + volume.get_height() + .75) -
                Math.round(volume.get_height()) - 3 : -2;
            const scale = actor?.get_resource_scale() ?? 1;
            this._textureX = (this.originX - offsetX) * scale;
            this._textureY = (this.originY - offsetY) * scale;
        }
        if (![this._textureX, this._textureY, vertex.x, vertex.y].every(Number.isFinite))
            return;
        const p = Math.max(0, Math.min(1, this.progress));
        const horizontal = this.side === St.Side.LEFT || this.side === St.Side.RIGHT;
        const reversed = this.side === St.Side.RIGHT || this.side === St.Side.BOTTOM;
        const length = horizontal ? width : height;
        const originalAlong = horizontal ? vertex.x : vertex.y;
        const originalAcross = horizontal ? vertex.y : vertex.x;
        const along = reversed ? length - originalAlong : originalAlong;
        const t = along / Math.max(1, length);
        const ribbon = Math.pow(p, 0.7 + 2.4 * (1 - t));
        const sourceAlong = horizontal ? this._textureX : this._textureY;
        const sourceAcross = horizontal ? this._textureY : this._textureX;
        const deformedAlong = sourceAlong + (originalAlong - sourceAlong) * p;
        const deformedAcross = sourceAcross + (originalAcross - sourceAcross) * ribbon;
        if (horizontal) {
            vertex.x = deformedAlong;
            vertex.y = deformedAcross;
        } else {
            vertex.x = deformedAcross;
            vertex.y = deformedAlong;
        }
    }
});
