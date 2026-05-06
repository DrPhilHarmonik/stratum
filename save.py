"""
Save/load world state using pickle.
Default save directory: ~/.local/share/stratum/
"""

import os
import pickle
import numpy as np
from pathlib import Path

from .world import WorldMap, WORLD_W, WORLD_H
from .geo   import GeologyLayer
from .civ   import CivLayer, Settlement, _used_names

SAVE_DIR = Path.home() / '.local' / 'share' / 'stratum'


def _save_path(seed: int, year: int) -> Path:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    return SAVE_DIR / f'seed{seed:05d}_year{year:05d}.stratum'


def save(world: WorldMap, geo: GeologyLayer, civ: CivLayer) -> Path:
    path = _save_path(world.seed, world.year)

    # Settlements: strip live object references (roads_to holds refs)
    def _ser_settlement(s: Settlement) -> dict:
        return {
            'name':     s.name,
            'x':        s.x,
            'y':        s.y,
            'pop':      s.pop,
            'age':      s.age,
            'state':    s.state,
            'roads_to': [r.name for r in s.roads_to],
        }

    payload = {
        # World
        'seed':        world.seed,
        'year':        world.year,
        'tick':        world.tick,
        'elev':        world.elev,
        'base_elev':   world.base_elev,
        'moisture':    world.moisture,
        'base_moist':  world.base_moist,
        'rivers':      world.rivers,
        'soil':        world.soil,
        'overlay':     world.overlay,
        # Geology
        'eruptions':   list(geo.eruptions),
        # Civ
        'settlements': [_ser_settlement(s) for s in civ.settlements],
        'history':     list(civ.history),
    }
    with open(path, 'wb') as f:
        pickle.dump(payload, f)
    return path


def load(path: str | Path) -> tuple[WorldMap, GeologyLayer, CivLayer]:
    with open(path, 'rb') as f:
        d = pickle.load(f)

    # Reconstruct WorldMap without regenerating (use saved arrays)
    world            = WorldMap.__new__(WorldMap)
    world.seed       = d['seed']
    world.year       = d['year']
    world.tick       = d['tick']
    world.elev       = d['elev']
    world.base_elev  = d['base_elev']
    world.moisture   = d['moisture']
    world.base_moist = d['base_moist']
    world.rivers     = d['rivers']
    world.soil       = d['soil']
    world.overlay    = d['overlay']

    geo           = GeologyLayer()
    geo.eruptions = d['eruptions']

    civ           = CivLayer()
    civ.history   = d['history']

    # Rebuild settlements (roads_to by name lookup after all are created)
    name_map: dict[str, Settlement] = {}
    raw = d['settlements']
    for sd in raw:
        s = Settlement(
            name=sd['name'], x=sd['x'], y=sd['y'],
            pop=sd['pop'],   age=sd['age'], state=sd['state'],
        )
        _used_names.add(s.name)
        civ.settlements.append(s)
        name_map[s.name] = s
    for s, sd in zip(civ.settlements, raw):
        s.roads_to = [name_map[n] for n in sd['roads_to'] if n in name_map]

    return world, geo, civ


def latest_save() -> Path | None:
    """Return the most recently modified save file, or None."""
    if not SAVE_DIR.exists():
        return None
    saves = sorted(SAVE_DIR.glob('*.stratum'), key=lambda p: p.stat().st_mtime)
    return saves[-1] if saves else None
