// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include "compat.h"
#include "effect/effect.h"
#include "effect/effecthandler.h"
#include "effect/effectwindow.h"
#include <epoxy/gl.h>

using namespace KWin;

/** Exercise folder blur with a clip and texture unit left by an earlier effect. */
class InheritedGLState : public Effect {
    Q_OBJECT
public:
    int requestedEffectChainPosition() const override { return 18; }
    bool isActive() const override { return true; }
    void drawWindow(const RenderTarget &target, const RenderViewport &viewport,
                    EffectWindow *window, int mask, const Region &damage, WindowPaintData &data) override
    {
        if (!window->caption().startsWith(QStringLiteral("io.github.hawkab.DockFolders.Glass."))
            || window->caption().section(QLatin1Char(':'),1,1).toDouble() <= 0) {
            effects->drawWindow(target, viewport, window, mask, damage, data);
            return;
        }
        const GLboolean scissor = glIsEnabled(GL_SCISSOR_TEST);
        GLint box[4], unit;
        glGetIntegerv(GL_SCISSOR_BOX, box);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &unit);
        glEnable(GL_SCISSOR_TEST);
        glScissor(0, 0, 1, 1);
        glActiveTexture(GL_TEXTURE1);
        effects->drawWindow(target, viewport, window, mask, damage, data);
        glActiveTexture(unit);
        glScissor(box[0], box[1], box[2], box[3]);
        if (!scissor) glDisable(GL_SCISSOR_TEST);
    }
};

KWIN_EFFECT_FACTORY_SUPPORTED_ENABLED(InheritedGLState, "inherited-gl-state.json",
    return effects->isOpenGLCompositing();, return false;)

#include "inherited-gl-state.moc"
