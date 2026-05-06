"""
CivilizationLayer: settlements, roads, bridges, history, and player interventions.
"""

import random
import math
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from .world import (WorldMap, COAST, PLAINS, FOREST, HILLS, MOUNTAIN,
                    SEA_SHALLOW, M_ARID, M_DRY,
                    OVERLAY_ROAD, OVERLAY_FARM, OVERLAY_RUINS,
                    OVERLAY_BURN, OVERLAY_BRIDGE)


# ── Name generation ───────────────────────────────────────────────

_PREFIXES = [
    'Iron', 'Grey', 'Ash', 'Stone', 'Thorn', 'Marsh', 'Elder',
    'Crow', 'Mere', 'Hollow', 'Frost', 'Amber', 'Dark', 'Salt',
    'Whit', 'Wick', 'Briar', 'Glen', 'Dun', 'Raven', 'Crag',
    'Mist', 'Flint', 'Gale', 'Heath', 'Loch', 'Peat', 'Reed',
]
_SUFFIXES = [
    'haven', 'feld', 'vast', 'mouth', 'ford', 'wick', 'hold',
    'moor', 'crest', 'burg', 'ton', 'gate', 'mere', 'keep',
    'dell', 'reach', 'worth', 'holm', 'mark', 'fell', 'cross',
    'bridge', 'ferry', 'mill', 'steading', 'barrow', 'rise',
]
_used_names: set[str] = set()


def _new_name() -> str:
    for _ in range(400):
        name = random.choice(_PREFIXES) + random.choice(_SUFFIXES)
        if name not in _used_names:
            _used_names.add(name)
            return name
    return 'Settlement'


# ── Tile description (used for founding narratives) ───────────────

def _tile_desc(world: WorldMap, x: int, y: int) -> str:
    e = float(world.elev[y, x])
    m = float(world.moisture[y, x])
    r = bool(world.rivers[y, x])

    if e < SEA_SHALLOW: return 'at sea'
    if e < COAST:       return 'on the shoals'

    if e < PLAINS:
        biome = 'dry coast' if m < M_ARID else 'coast'
    elif e < FOREST:
        if   m < M_ARID: biome = 'desert'
        elif m < M_DRY:  biome = 'savanna'
        else:             biome = 'plains'
    elif e < HILLS:
        biome = 'scrubland' if m < M_DRY else 'forest'
    elif e < MOUNTAIN:
        biome = 'hills'
    else:
        biome = 'mountains'

    mods = []
    if r:             mods.append('by the river')
    if e < PLAINS + 0.04: mods.append('near the coast')
    suffix = ', '.join(mods)
    return f'on the {biome}' + (f' {suffix}' if suffix else '')


# ── Settlement ────────────────────────────────────────────────────

@dataclass
class Settlement:
    name: str
    x: int
    y: int
    pop: float        = 10.0
    age: int          = 0
    state: str        = 'growing'
    roads_to: list    = field(default_factory=list)
    founded_year: int = 0
    founded_by: str   = ''      # parent name, or '' for organic founding
    farm_radius: int  = 4
    _size_label: str  = ''      # cached for milestone detection

    @property
    def ipop(self) -> int:
        return max(0, int(self.pop))

    def size_label(self) -> str:
        p = self.ipop
        if p == 0:    return 'ruins'
        if p < 30:    return 'hamlet'
        if p < 120:   return 'village'
        if p < 400:   return 'town'
        if p < 1000:  return 'city'
        return 'metropolis'


# ── Constants ─────────────────────────────────────────────────────

MAX_SETTLEMENTS    = 30
SPAWN_CHANCE       = 0.20    # per year
ROAD_DIST          = 70
ROAD_MIN_POP       = 40
CONFLICT_DIST      = 28
CONFLICT_CHANCE    = 0.007   # low -- wars are notable events, not routine
CONFLICT_MIN_POP   = 30
FARM_BASE_RADIUS   = 4
FARM_POP_PER_RING  = 60      # gain 1 radius ring per N pop
DEFOREST_SOIL_HIT  = 0.0008
DECAY_CHANCE       = 0.30    # chance per year that one road cell near ruin crumbles
RUIN_FADE_CHANCE   = 0.15    # chance per year that a ruin cell fully clears


class CivLayer:
    def __init__(self):
        self.settlements: list[Settlement] = []
        self.history: list[str] = []
        self.recent:  list[str] = []

    # ── Public interventions ──────────────────────────────────────

    def found(self, world: WorldMap, x: int, y: int,
              parent: str = '[player]') -> Optional[str]:
        if not world.is_land(x, y):
            return None
        name = _new_name()
        s = Settlement(name=name, x=x, y=y,
                       founded_year=world.year, founded_by=parent)
        s._size_label = s.size_label()
        self.settlements.append(s)
        loc = _tile_desc(world, x, y)
        msg = f'Year {world.year}: {name} founded {loc} [{parent}]'
        self._log(msg)
        self._stamp_farm(world, s)
        return msg

    def trigger_conflict(self, world: WorldMap) -> Optional[str]:
        pairs = self._close_pairs(CONFLICT_DIST * 2)
        if not pairs:
            return None
        a, b = random.choice(pairs)
        return self._do_conflict(world, a, b)

    def trigger_drought(self, world: WorldMap) -> str:
        land = world.elev >= COAST
        world.moisture[land] = np.maximum(0.0, world.moisture[land] - 0.12)
        msg = f'Year {world.year}: Drought scorches the land'
        self._log(msg)
        return msg

    # ── Yearly step ───────────────────────────────────────────────

    def step_year(self, world: WorldMap) -> list[str]:
        self.recent = []
        self._grow_settlements(world)
        self._expand_farms(world)
        self._try_spawn(world)
        self._try_roads(world)
        self._try_conflicts(world)
        self._decay_structures(world)
        self._purge_abandoned(world)
        return list(self.recent)

    # ── Internal: growth ─────────────────────────────────────────

    def _log(self, msg: str):
        self.history.append(msg)
        self.recent.append(msg)

    def _grow_settlements(self, world: WorldMap):
        for s in self.settlements:
            if s.state == 'abandoned':
                continue
            s.age += 1

            soil  = float(world.soil    [s.y, s.x])
            moist = float(world.moisture[s.y, s.x])
            fertility = (soil + moist) / 2.0

            carry = max(5.0, fertility * 1400)
            rate  = 0.06 * fertility * (1.0 - s.pop / carry)
            s.pop = max(0.0, s.pop + s.pop * rate + random.uniform(-0.3, 0.3))

            # Soil depletion under the settlement itself
            world.soil[s.y, s.x] = max(0.0, world.soil[s.y, s.x] - DEFOREST_SOIL_HIT)

            # Milestone transitions
            new_label = s.size_label()
            if new_label != s._size_label and s._size_label:
                if s.ipop > 0:
                    self._log(
                        f'Year {world.year}: {s.name} grows to {new_label} '
                        f'(pop {s.ipop})')
                elif s.state != 'abandoned':
                    self._log(
                        f'Year {world.year}: {s.name} dwindles -- '
                        f'soil exhausted, settlers scatter')
            s._size_label = new_label

            # State transitions
            if s.pop < 2:
                s.state = 'abandoned'
                world.overlay[s.y, s.x] = OVERLAY_RUINS
                self._log(f'Year {world.year}: {s.name} abandoned')
            elif s.pop < 20:
                s.state = 'declining'
            elif rate < 0.01:
                s.state = 'stable'
            else:
                s.state = 'growing'

    # Radii at which farm expansion is notable enough to log
    _FARM_LOG_RADII = {6, 8, 10, 12, 15, 18}

    def _expand_farms(self, world: WorldMap):
        """Grow farm radius as population rises; log at notable milestones."""
        for s in self.settlements:
            if s.state == 'abandoned':
                continue
            new_r = FARM_BASE_RADIUS + int(s.pop / FARM_POP_PER_RING)
            new_r = min(new_r, 18)
            if new_r > s.farm_radius:
                old_r = s.farm_radius
                s.farm_radius = new_r
                self._stamp_farm(world, s)
                if new_r in self._FARM_LOG_RADII and old_r not in self._FARM_LOG_RADII:
                    size = s.size_label()
                    self._log(
                        f'Year {world.year}: {s.name} ({size}) '
                        f'expands fields to {new_r} cells')

    def _stamp_farm(self, world: WorldMap, s: Settlement, radius: int = 0):
        r = radius or s.farm_radius
        h, w = world.height, world.width
        x0 = max(0, s.x - r);  x1 = min(w, s.x + r + 1)
        y0 = max(0, s.y - r);  y1 = min(h, s.y + r + 1)
        yi, xi = np.ogrid[y0:y1, x0:x1]
        mask = ((yi - s.y)**2 + (xi - s.x)**2 <= r**2) & \
               (world.elev[y0:y1, x0:x1] >= COAST)
        sub_ov   = world.overlay[y0:y1, x0:x1]
        sub_soil = world.soil   [y0:y1, x0:x1]
        # Don't overwrite roads, bridges, or ruins with farmland
        placeable = mask & ~np.isin(sub_ov, [OVERLAY_ROAD, OVERLAY_BRIDGE, OVERLAY_RUINS])
        sub_ov  [placeable] = OVERLAY_FARM
        sub_soil[placeable] = np.maximum(0.0, sub_soil[placeable] - 0.02)

    # ── Internal: roads & bridges ─────────────────────────────────

    def _try_roads(self, world: WorldMap):
        active = [s for s in self.settlements
                  if s.state != 'abandoned' and s.pop >= ROAD_MIN_POP]
        for a in active:
            for b in active:
                if b is a or b in a.roads_to:
                    continue
                d = math.hypot(a.x - b.x, a.y - b.y)
                if d > ROAD_DIST or random.random() > 0.12:
                    continue
                a.roads_to.append(b)
                b.roads_to.append(a)
                bridges = self._draw_road(world, a, b)
                if bridges:
                    for bx, by in bridges:
                        self._log(
                            f'Year {world.year}: Bridge built at ({bx},{by}) '
                            f'on road from {a.name} to {b.name}')
                else:
                    self._log(
                        f'Year {world.year}: Road built between '
                        f'{a.name} and {b.name}')

    def _draw_road(self, world: WorldMap,
                   a: Settlement, b: Settlement) -> list[tuple[int, int]]:
        """Bresenham from a to b.  Returns list of bridge positions."""
        x0, y0, x1, y1 = a.x, a.y, b.x, b.y
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        bridges: list[tuple[int, int]] = []

        while True:
            if 0 <= y0 < world.height and 0 <= x0 < world.width:
                if world.rivers[y0, x0] and world.elev[y0, x0] >= COAST:
                    world.overlay[y0, x0] = OVERLAY_BRIDGE
                    bridges.append((x0, y0))
                elif world.is_land(x0, y0):
                    if world.overlay[y0, x0] not in (OVERLAY_BRIDGE,):
                        world.overlay[y0, x0] = OVERLAY_ROAD
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:  err -= dy;  x0 += sx
            if e2 <  dx:  err += dx;  y0 += sy

        return bridges

    # ── Internal: spawning ────────────────────────────────────────

    def _try_spawn(self, world: WorldMap):
        active = [s for s in self.settlements if s.state != 'abandoned']
        if len(active) >= MAX_SETTLEMENTS or random.random() > SPAWN_CHANCE:
            return

        occupied = {(s.x, s.y) for s in active}
        h, w     = world.height, world.width

        # 65% chance: daughter colony from a large settlement
        parents = [s for s in active if s.pop > 80]
        use_parent = parents and random.random() < 0.65
        parent = random.choice(parents) if use_parent else None

        best_s, best_x, best_y = -1.0, -1, -1

        for _ in range(100):
            if parent:
                # Search near parent, biased outward
                angle  = random.uniform(0, 2 * math.pi)
                dist_r = random.randint(12, 35)
                rx = int(parent.x + math.cos(angle) * dist_r)
                ry = int(parent.y + math.sin(angle) * dist_r)
                rx = max(2, min(w - 3, rx))
                ry = max(2, min(h - 3, ry))
            else:
                rx = random.randint(2, w - 3)
                ry = random.randint(2, h - 3)

            if (rx, ry) in occupied:
                continue
            score = world.biome_score(rx, ry)
            for s in active:
                d = math.hypot(rx - s.x, ry - s.y)
                if d < 10:
                    score -= (10 - d) * 0.12
            if score > best_s:
                best_s, best_x, best_y = score, rx, ry

        if best_s < 0.12:
            return

        name = _new_name()
        s = Settlement(name=name, x=best_x, y=best_y,
                       founded_year=world.year,
                       founded_by=parent.name if parent else '')
        s._size_label = s.size_label()
        self.settlements.append(s)
        self._stamp_farm(world, s)
        loc = _tile_desc(world, best_x, best_y)

        if parent:
            self._log(
                f'Year {world.year}: Settlers from {parent.name} '
                f'found {name} {loc}')
        else:
            self._log(f'Year {world.year}: {name} established {loc}')

    # ── Internal: conflict ────────────────────────────────────────

    def _close_pairs(self, max_d: float) -> list[tuple]:
        active = [s for s in self.settlements if s.state != 'abandoned']
        pairs  = []
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                if math.hypot(a.x - b.x, a.y - b.y) <= max_d:
                    pairs.append((a, b))
        return pairs

    def _try_conflicts(self, world: WorldMap):
        for a, b in self._close_pairs(CONFLICT_DIST):
            if (a.pop >= CONFLICT_MIN_POP and b.pop >= CONFLICT_MIN_POP
                    and random.random() < CONFLICT_CHANCE):
                self._do_conflict(world, a, b)

    def _do_conflict(self, world: WorldMap,
                     a: Settlement, b: Settlement) -> str:
        if a.pop >= b.pop:
            winner, loser = a, b
        else:
            winner, loser = b, a

        loser.pop  *= random.uniform(0.25, 0.55)
        winner.pop *= random.uniform(0.82, 0.96)

        # Burn scar around loser (bounding-box approach for speed)
        r = 5
        h, w = world.height, world.width
        x0 = max(0, loser.x - r);  x1 = min(w, loser.x + r + 1)
        y0 = max(0, loser.y - r);  y1 = min(h, loser.y + r + 1)
        yi, xi = np.ogrid[y0:y1, x0:x1]
        mask = ((yi - loser.y)**2 + (xi - loser.x)**2 <= r**2) & \
               (world.elev[y0:y1, x0:x1] >= COAST)
        world.overlay[y0:y1, x0:x1][mask] = OVERLAY_BURN

        msg = (f'Year {world.year}: War -- {winner.name} defeats '
               f'{loser.name} (pop now {loser.ipop})')
        self._log(msg)
        return msg

    # ── Internal: decay ───────────────────────────────────────────

    def _decay_structures(self, world: WorldMap):
        """Roads near abandoned settlements crumble; ruins eventually clear."""
        h, w = world.height, world.width
        for s in self.settlements:
            if s.state != 'abandoned':
                continue
            r = 12
            x0 = max(0, s.x - r);  x1 = min(w, s.x + r + 1)
            y0 = max(0, s.y - r);  y1 = min(h, s.y + r + 1)
            sub = world.overlay[y0:y1, x0:x1]

            # Road cells slowly become ruins
            if random.random() < DECAY_CHANCE:
                road_idx = np.argwhere(sub == OVERLAY_ROAD)
                if len(road_idx):
                    py, px = road_idx[random.randrange(len(road_idx))]
                    sub[py, px] = OVERLAY_RUINS
                    self._log(
                        f'Year {world.year}: Road near {s.name} crumbles')

            # Ruin cells eventually vanish
            if random.random() < RUIN_FADE_CHANCE:
                ruin_idx = np.argwhere(sub == OVERLAY_RUINS)
                if len(ruin_idx):
                    py, px = ruin_idx[random.randrange(len(ruin_idx))]
                    sub[py, px] = OVERLAY_NONE

    # ── Internal: cleanup ─────────────────────────────────────────

    def _purge_abandoned(self, world: WorldMap):
        ruins  = [s for s in self.settlements if s.state == 'abandoned']
        active = [s for s in self.settlements if s.state != 'abandoned']
        self.settlements = active + ruins[-20:]
