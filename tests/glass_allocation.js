// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

/** Verify an open folder restores blur after its dock anchor is rebuilt. */
export async function checkGlassAllocation(folders, key, third, until, assert) {
    const saved = folders._settings.get_string('groups');
    const sync = folders._syncGlass;
    const ready = folders._animation._anchorReady;
    let deferred = 0;
    let forcedReads = 0;
    let unblurredFrames = 0;
    let shiftedFrames = 0;
    const paint = global.stage.connect('after-paint', () => {
        for (const {menu} of folders._icons.values()) {
            if (!menu.isOpen || !menu.actor.mapped || !menu.actor.has_allocation() || menu.actor.opacity === 0 || !menu._useGlass)
                continue;
            if (!menu._glassClone) {
                unblurredFrames++;
                continue;
            }
            const expected = global.window_group.get_transformed_position();
            const actual = menu._glassClone.get_transformed_position();
            if (!actual.every(Number.isFinite) || actual.some((coordinate, index) => Math.abs(coordinate - expected[index]) > .1))
                shiftedFrames++;
        }
    });
    folders._syncGlass = function (menu) {
        const allocation = menu._glass.get_allocation_box;
        menu._glass.get_allocation_box = function () {
            forcedReads++;
            return allocation.call(this);
        };
        try {
            return sync.call(this, menu);
        } finally {
            menu._glass.get_allocation_box = allocation;
        }
    };
    folders._animation._anchorReady = function (menu) {
        const allocated = ready.call(this, menu);
        if (!allocated)
            deferred++;
        return allocated;
    };
    try {
        const current = [...folders._icons.values()].find(item => item.group.key === key && item.icon.mapped);
        if (!current.menu.isOpen)
            folders._openGroup(key);
        await until(() => current.menu._glassClone, 'Initial folder blur did not map');
        const groups = JSON.parse(saved);
        groups['allocation-probe'] = {id: 'local.groups.AllocationProbe', name: 'Allocation probe', apps: [third]};
        folders._settings.set_string('groups', JSON.stringify(groups));
        await until(() => [...folders._icons.values()].some(item => item.group.key === key &&
            item.menu !== current.menu && item.menu.isOpen && item.menu._glassClone && item.menu._blurEffect.radius > 0),
        'Rebuilt folder did not restore its backdrop blur', 5000);
        assert(deferred > 0, 'Rebuilding did not exercise pending actor allocation');
        assert(forcedReads === 0, 'Blur forced layout before its dock anchor was allocated');
        assert(unblurredFrames === 0, 'The open folder painted a frame without its backdrop blur');
        assert(shiftedFrames === 0, 'The open folder painted a shifted backdrop blur');
    } finally {
        global.stage.disconnect(paint);
        folders._syncGlass = sync;
        folders._animation._anchorReady = ready;
        folders._settings.set_string('groups', saved);
        await until(() => !folders._groups['allocation-probe'] && [...folders._icons.values()].some(item =>
            item.group.key === key && item.menu.isOpen && item.menu._glassClone),
        'Restoring folders did not restore their blur', 5000);
    }
    print('GLASS_ALLOCATION_OK deferred layout and restored backdrop blur');
}
