import os
import random
import sys

import numpy as np
import pytest

# The repo directory is the `stratum` package itself, and it also holds an
# old `stratum/` copy. Put the parent first so `import stratum` is this one.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from stratum.world import WorldMap  # noqa: E402

SEA = 0.20
LAND = 0.50


def make_world(h=40, w=60, sea_cols=20):
    """A small hand-built world: sea on the left, flat plains on the right.

    Built like save.load does, so no terrain generation runs.
    """
    world = WorldMap.__new__(WorldMap)
    world.seed = 0
    world.year = 0
    world.tick = 0
    world.elev = np.full((h, w), LAND, dtype=np.float32)
    world.elev[:, :sea_cols] = SEA
    world.base_elev = world.elev.copy()
    world.moisture = np.full((h, w), 0.6, dtype=np.float32)
    world.base_moist = world.moisture.copy()
    world.rivers = np.zeros((h, w), dtype=bool)
    world.soil = np.full((h, w), 0.7, dtype=np.float32)
    world.overlay = np.zeros((h, w), dtype=np.uint8)
    return world


@pytest.fixture
def world():
    return make_world()


@pytest.fixture(autouse=True)
def seeded():
    random.seed(1234)
    np.random.seed(1234)
