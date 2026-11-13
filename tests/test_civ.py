import random

import numpy as np
import pytest

from stratum import civ as civ_mod
from stratum.civ import CivLayer, Settlement
from stratum.world import (OVERLAY_BRIDGE, OVERLAY_BURN, OVERLAY_FARM,
                           OVERLAY_NONE, OVERLAY_ROAD, OVERLAY_RUINS)


def test_founding_on_sea_is_refused(world):
    civ = CivLayer()
    assert civ.found(world, 5, 5) is None
    assert civ.settlements == []


def test_founding_on_land_adds_a_settlement_and_its_fields(world):
    civ = CivLayer()
    msg = civ.found(world, 40, 20, parent='dawn')
    assert msg is not None and 'founded' in msg and '[dawn]' in msg
    s = civ.settlements[0]
    assert (s.x, s.y, s.founded_by) == (40, 20, 'dawn')
    assert world.overlay[20, 40] == OVERLAY_FARM
    assert civ.history == [msg]


def test_farms_never_spill_into_the_sea(world):
    civ = CivLayer()
    civ.found(world, 21, 20)
    assert not (world.overlay[:, :20] == OVERLAY_FARM).any()


@pytest.mark.parametrize('pop,label', [
    (0, 'ruins'), (10, 'hamlet'), (50, 'village'),
    (200, 'town'), (600, 'city'), (1500, 'metropolis'),
])
def test_size_labels(pop, label):
    assert Settlement('X', 0, 0, pop=pop).size_label() == label


def test_a_starving_settlement_is_abandoned_and_leaves_ruins(world):
    civ = CivLayer()
    civ.found(world, 40, 20)
    s = civ.settlements[0]
    s.pop = 1.0
    world.soil[:] = 0.0
    world.moisture[:] = 0.0
    civ._grow_settlements(world)
    assert s.state == 'abandoned'
    assert world.overlay[20, 40] == OVERLAY_RUINS
    assert any('abandoned' in m for m in civ.history)


def test_roads_cross_rivers_as_bridges(world):
    world.rivers[:, 40] = True
    civ = CivLayer()
    a = Settlement('A', 30, 20)
    b = Settlement('B', 50, 20)
    bridges = civ._draw_road(world, a, b)
    assert bridges == [(40, 20)]
    assert world.overlay[20, 40] == OVERLAY_BRIDGE
    assert world.overlay[20, 35] == OVERLAY_ROAD


def test_fields_do_not_pave_over_roads_or_ruins(world):
    world.overlay[20, 41] = OVERLAY_ROAD
    world.overlay[20, 39] = OVERLAY_RUINS
    civ = CivLayer()
    civ.found(world, 40, 20)
    assert world.overlay[20, 41] == OVERLAY_ROAD
    assert world.overlay[20, 39] == OVERLAY_RUINS


def test_the_larger_side_wins_a_war_and_the_loser_burns(world):
    civ = CivLayer()
    big = Settlement('Big', 30, 20, pop=500)
    small = Settlement('Small', 45, 20, pop=100)
    msg = civ._do_conflict(world, small, big)
    assert 'Big defeats Small' in msg
    assert small.pop <= 55 and 410 <= big.pop <= 480
    assert world.overlay[20, 45] == OVERLAY_BURN


def test_ruins_near_an_abandoned_town_fade(world, monkeypatch):
    # Regression: civ.py used OVERLAY_NONE without importing it, so this
    # raised NameError the first time a ruin was due to fade.
    civ = CivLayer()
    civ.settlements = [Settlement('Gone', 40, 20, pop=0, state='abandoned')]
    world.overlay[20, 41] = OVERLAY_RUINS
    monkeypatch.setattr(civ_mod.random, 'random', lambda: 0.0)
    civ._decay_structures(world)
    assert world.overlay[20, 41] == OVERLAY_NONE


def test_roads_near_an_abandoned_town_crumble(world, monkeypatch):
    civ = CivLayer()
    civ.settlements = [Settlement('Gone', 40, 20, pop=0, state='abandoned')]
    world.overlay[20, 45] = OVERLAY_ROAD
    rolls = iter([0.0, 1.0])  # crumble, then skip the fade
    monkeypatch.setattr(civ_mod.random, 'random', lambda: next(rolls))
    civ._decay_structures(world)
    assert world.overlay[20, 45] == OVERLAY_RUINS
    assert any('crumbles' in m for m in civ.history)


def test_only_the_last_twenty_ruins_are_kept(world):
    civ = CivLayer()
    live = Settlement('Live', 40, 20, pop=100)
    dead = [Settlement(f'D{i}', 40, 20, pop=0, state='abandoned') for i in range(25)]
    civ.settlements = dead + [live]
    civ._purge_abandoned(world)
    assert civ.settlements[0] is live
    assert civ.settlements[1:] == dead[-20:]


def test_drought_dries_land_but_not_sea(world):
    civ = CivLayer()
    civ.trigger_drought(world)
    assert world.moisture[0, 40] == pytest.approx(0.48)
    assert world.moisture[0, 5] == pytest.approx(0.6)


def test_a_century_on_the_small_world_runs_and_settles_it(world):
    civ = CivLayer()
    civ.found(world, 40, 20)
    for _ in range(100):
        world.year += 1
        civ.step_year(world)
    active = [s for s in civ.settlements if s.state != 'abandoned']
    assert active
    assert all(world.elev[s.y, s.x] >= 0.39 for s in civ.settlements)
    assert len(active) <= civ_mod.MAX_SETTLEMENTS
