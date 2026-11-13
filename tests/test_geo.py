import numpy as np

from stratum import geo as geo_mod
from stratum.geo import GeologyLayer
from stratum.world import COAST, OVERLAY_LAVA


def test_rivers_erode_their_bed_but_never_below_the_coast(world):
    world.rivers[:, 40] = True
    world.rivers[:, 5] = True  # a river cell out at sea is left alone
    world.elev[0, 40] = COAST + 0.00001
    GeologyLayer()._erode_rivers(world)
    assert world.elev[10, 40] < 0.5
    assert world.elev[0, 40] == np.float32(COAST)
    assert world.elev[10, 5] == np.float32(0.20)
    assert world.moisture[10, 40] > 0.6


def test_an_eruption_raises_the_land_and_lays_lava(world):
    world.elev[20, 40] = 0.80
    geo = GeologyLayer()
    msg = geo._erupt(world)
    assert msg == 'Volcanic eruption at (40, 20)'
    assert world.elev[20, 40] > 0.80
    assert world.overlay[20, 40] == OVERLAY_LAVA
    assert world.overlay[20, 42] == OVERLAY_LAVA
    assert geo.eruptions == [(40, 20, 0)]


def test_no_high_ground_means_no_eruption(world):
    assert GeologyLayer()._erupt(world) is None


def test_lava_cools_after_three_years(world):
    world.elev[20, 40] = 0.80
    geo = GeologyLayer()
    geo._erupt(world)
    world.year = 2
    geo._cool_lava(world)
    assert (world.overlay == OVERLAY_LAVA).any()
    world.year = 3
    geo._cool_lava(world)
    assert not (world.overlay == OVERLAY_LAVA).any()
    assert geo.eruptions == []


def test_step_year_erupts_only_on_the_roll(world, monkeypatch):
    world.elev[20, 40] = 0.80
    geo = GeologyLayer()
    monkeypatch.setattr(geo_mod.random, 'random', lambda: 0.5)
    assert geo.step_year(world) == []
    monkeypatch.setattr(geo_mod.random, 'random', lambda: 0.0)
    assert geo.step_year(world) == ['Volcanic eruption at (40, 20)']
