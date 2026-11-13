import os
import pickle
import time

import numpy as np
import pytest

from stratum import save as save_mod
from stratum.civ import CivLayer
from stratum.geo import GeologyLayer


@pytest.fixture
def save_dir(tmp_path, monkeypatch):
    monkeypatch.delenv('STRATUM_SAVE_DIR', raising=False)
    monkeypatch.setattr(save_mod, 'SAVE_DIR', tmp_path)
    return tmp_path


def test_a_saved_world_loads_back_the_same(world, save_dir):
    world.year, world.tick = 37, 2
    world.overlay[3, 30] = 1
    geo = GeologyLayer()
    geo.eruptions = [(40, 20, 35)]
    civ = CivLayer()
    civ.found(world, 30, 10, parent='dawn')
    civ.found(world, 50, 30)
    a, b = civ.settlements
    a.pop, a.age, a.state, a.farm_radius = 140.5, 30, 'stable', 6
    a.roads_to.append(b)
    b.roads_to.append(a)

    path = save_mod.save(world, geo, civ)
    assert path.parent == save_dir
    assert path.name == 'seed00000_year00037.stratum'

    w2, g2, c2 = save_mod.load(path)
    assert (w2.seed, w2.year, w2.tick) == (0, 37, 2)
    for name in ('elev', 'base_elev', 'moisture', 'base_moist', 'rivers', 'soil', 'overlay'):
        assert np.array_equal(getattr(w2, name), getattr(world, name)), name
    assert g2.eruptions == [(40, 20, 35)]
    assert c2.history == civ.history

    a2, b2 = c2.settlements
    for orig, got in ((a, a2), (b, b2)):
        for field in ('name', 'x', 'y', 'pop', 'age', 'state',
                      'founded_year', 'founded_by', 'farm_radius'):
            assert getattr(got, field) == getattr(orig, field), field
    assert a2.roads_to == [b2] and b2.roads_to == [a2]


def test_a_loaded_world_keeps_running(world, save_dir):
    civ = CivLayer()
    civ.found(world, 40, 20)
    w2, g2, c2 = save_mod.load(save_mod.save(world, GeologyLayer(), civ))
    for _ in range(20):
        w2.year += 1
        g2.step_year(w2)
        c2.step_year(w2)
    assert c2.settlements


def test_latest_save_is_the_newest_file(world, save_dir):
    assert save_mod.latest_save() is None
    civ, geo = CivLayer(), GeologyLayer()
    first = save_mod.save(world, geo, civ)
    world.year = 5
    second = save_mod.save(world, geo, civ)
    os.utime(first, (time.time() - 60, time.time() - 60))
    assert save_mod.latest_save() == second


def test_the_save_dir_follows_stratum_save_dir(tmp_path, monkeypatch):
    # The README documents STRATUM_SAVE_DIR.
    monkeypatch.setenv('STRATUM_SAVE_DIR', str(tmp_path))
    assert save_mod._save_dir() == tmp_path


def test_saves_from_before_founding_was_stored_still_load(world, save_dir):
    civ = CivLayer()
    civ.found(world, 40, 20, parent='dawn')
    path = save_mod.save(world, GeologyLayer(), civ)
    payload = pickle.loads(path.read_bytes())
    for sd in payload['settlements']:
        for key in ('founded_year', 'founded_by', 'farm_radius'):
            del sd[key]
    path.write_bytes(pickle.dumps(payload))
    s = save_mod.load(path)[2].settlements[0]
    assert (s.founded_year, s.founded_by, s.farm_radius) == (0, '', 4)
