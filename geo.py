"""
GeologyLayer: slow terrain mutation driven by erosion and rare volcanic events.
Runs once per year (every 4 ticks).
"""

import random
import numpy as np
from .world import WorldMap, COAST, SEA_SHALLOW, MOUNTAIN, HILLS, OVERLAY_LAVA


# How much elevation rivers erode per year along their path
RIVER_EROSION   = 0.00015
# Soil washed into rivers raises downstream moisture slightly
MOISTURE_GAIN   = 0.00008
# Chance per year of a volcanic event
VOLCANO_CHANCE  = 0.012
# Radius and height boost of a volcanic eruption
VOLCANO_RADIUS  = 5
VOLCANO_BOOST   = 0.08


class GeologyLayer:
    def __init__(self):
        self.eruptions: list[tuple[int,int,int]] = []  # (x, y, year_formed)

    def step_year(self, world: WorldMap) -> list[str]:
        """Called once per year. Returns list of history strings."""
        events = []
        self._erode_rivers(world)
        if random.random() < VOLCANO_CHANCE:
            msg = self._erupt(world)
            if msg:
                events.append(msg)
        self._cool_lava(world)
        return events

    # ── River erosion ─────────────────────────────────────────────

    def _erode_rivers(self, world: WorldMap):
        mask = world.rivers & (world.elev >= COAST)
        world.elev[mask] = np.maximum(
            COAST, world.elev[mask] - RIVER_EROSION
        )
        # Slight moisture boost in eroded valleys
        world.moisture[mask] = np.minimum(
            1.0, world.moisture[mask] + MOISTURE_GAIN
        )

    # ── Volcanism ─────────────────────────────────────────────────

    def _erupt(self, world: WorldMap) -> str | None:
        h, w = world.height, world.width
        # Pick a random high-elevation land cell as the vent
        candidates = np.argwhere(world.elev > HILLS)
        if len(candidates) == 0:
            return None
        idx = random.randrange(len(candidates))
        cy, cx = int(candidates[idx, 0]), int(candidates[idx, 1])

        r = VOLCANO_RADIUS
        yi, xi = np.ogrid[:h, :w]
        dist2  = (yi - cy)**2 + (xi - cx)**2
        mask   = dist2 <= r**2

        # Raise terrain and mark lava overlay
        boost = VOLCANO_BOOST * (1.0 - np.sqrt(dist2[mask]) / r)
        world.elev[mask]    = np.minimum(1.0, world.elev[mask] + boost)
        world.overlay[mask] = OVERLAY_LAVA

        self.eruptions.append((cx, cy, world.year))
        return f"Volcanic eruption at ({cx}, {cy})"

    def _cool_lava(self, world: WorldMap):
        # Lava cells become rock after 3 years; clear overlay then
        current_year = world.year
        fresh = []
        for (x, y, yr) in self.eruptions:
            if current_year - yr >= 3:
                world.overlay[y, x] = 0  # revert to normal render
            else:
                fresh.append((x, y, yr))
        self.eruptions = fresh
