"""Smoke tests on one real generated world (generation takes a few seconds)."""
import random

import numpy as np
import pytest

from stratum import chronicle
from stratum.civ import CivLayer
from stratum.geo import GeologyLayer
from stratum.world import COAST, SEA_SHALLOW, WORLD_H, WORLD_W, WorldMap


@pytest.fixture(scope='module')
def generated():
    return WorldMap(42)


def test_a_world_has_the_full_size_and_both_land_and_sea(generated):
    assert generated.elev.shape == (WORLD_H, WORLD_W)
    land = (generated.elev >= COAST).mean()
    sea = (generated.elev < SEA_SHALLOW).mean()
    assert 0.1 < land < 0.9
    assert 0.1 < sea < 0.9
    assert generated.rivers.any()
    assert not generated.overlay.any()


def test_the_same_seed_makes_the_same_world(generated):
    again = WorldMap(42)
    assert np.array_equal(again.elev, generated.elev)
    assert np.array_equal(again.rivers, generated.rivers)


def test_bounds_and_habitability(world):
    assert not world.is_land(-1, 0) and not world.is_sea(0, 10_000)
    assert world.is_sea(5, 5) and world.is_land(40, 5)
    assert world.biome_score(5, 5) == 0.0
    assert world.biome_score(40, 5) > 0.0
    world.elev[5, 41] = 0.9
    assert world.biome_score(41, 5) == 0.0


def test_four_ticks_make_a_year(world):
    for _ in range(3):
        world.step()
    assert (world.year, world.tick) == (0, 3)
    world.step()
    assert (world.year, world.tick) == (1, 0)


def test_two_centuries_of_history_on_a_real_world(generated):
    world = generated
    random.seed(7)
    geo, civ = GeologyLayer(), CivLayer()
    for x, y in chronicle._best_land_sites(world, 2):
        civ.found(world, x, y, parent='dawn')
    assert len(civ.settlements) == 2
    for _ in range(200 * 4):
        world.step()
        if world.tick == 0:
            geo.step_year(world)
            civ.step_year(world)
    assert world.year == 200
    assert len(civ.settlements) > 2
    assert all(world.is_land(s.x, s.y) for s in civ.settlements)


def test_the_chronicle_prints_a_closing_summary(capsys):
    random.seed(3)
    np.random.seed(3)
    chronicle.run(years=30, every=30, cols=40, rows=10, seeds=3)
    out = capsys.readouterr().out
    assert 'STRATUM CHRONICLE' in out
    assert 'After 30 years:' in out
    assert 'Year   30' in out
