"""Headless world chronicle -- generate a continent and watch history unfold in text.

Runs the real STRATUM simulation (heightmap, climate, rivers, then settlements
founding, growing, roading, warring, and collapsing over centuries) with no
curses and no interaction. It streams the notable events year by year and prints
a downsampled ASCII relief map at intervals, so you can watch civilizations rise
and fall on the terrain that shaped them.

    python3 -m stratum.chronicle                       # from /home/god/projects
    python3 chronicle.py --years 400 --every 100        # from inside stratum/
    python3 chronicle.py --seed 7 --cols 110 --rows 34

Terrain:  ' ' deep sea   ~ sea   . coast   , plains   ; savanna   : desert
          + river   # forest   ^ hills   M mountains   A snow
Towns:    o hamlet   O village   @ town   % city   & metropolis   x ruins
"""

import argparse
import random

import numpy as np

try:
    from .world import (WorldMap, WORLD_W, WORLD_H,
                        SEA_DEEP, COAST, PLAINS, FOREST, HILLS, MOUNTAIN, SNOW,
                        M_ARID, M_DRY)
    from .geo import GeologyLayer
    from .civ import CivLayer
except ImportError:  # running from inside the package directory
    from world import (WorldMap, WORLD_W, WORLD_H,
                       SEA_DEEP, COAST, PLAINS, FOREST, HILLS, MOUNTAIN, SNOW,
                       M_ARID, M_DRY)
    from geo import GeologyLayer
    from civ import CivLayer


def ascii_terrain(elev, moist, river):
    """A single relief glyph for one world cell."""
    if elev < SEA_DEEP:  return ' '
    if elev < COAST:     return '~'
    if river:            return '+'
    if elev < PLAINS:
        return ':' if moist < M_ARID else '.'
    if elev < FOREST:
        if moist < M_ARID: return ':'
        if moist < M_DRY:  return ';'
        return ','
    if elev < HILLS:
        return ';' if moist < M_DRY else '#'
    if elev < MOUNTAIN:  return '^'
    if elev < SNOW:      return 'M'
    return 'A'


def settlement_glyph(s):
    """Marker for a settlement, scaled by population (ruins for the abandoned)."""
    if s.state == 'abandoned':
        return 'x'
    p = s.ipop
    if p < 30:   return 'o'
    if p < 120:  return 'O'
    if p < 400:  return '@'
    if p < 1000: return '%'
    return '&'


# Bigger settlements should win a shared cell, so paint in this order.
_GLYPH_RANK = {'x': 0, 'o': 1, 'O': 2, '@': 3, '%': 4, '&': 5}


def ascii_frame(world, civ, cols, rows):
    """Downsample the world to an `rows` x `cols` relief map with settlements."""
    elev = world.elev
    moist = world.moisture
    rivers = world.rivers
    H, W = elev.shape

    grid = []
    for r in range(rows):
        wy = min(H - 1, int((r + 0.5) / rows * H))
        row = []
        for c in range(cols):
            wx = min(W - 1, int((c + 0.5) / cols * W))
            river = bool(rivers[wy, wx])
            row.append(ascii_terrain(float(elev[wy, wx]), float(moist[wy, wx]), river))
        grid.append(row)

    # Overlay settlements; larger markers overwrite smaller ones in a shared cell.
    for s in civ.settlements:
        c = min(cols - 1, int(s.x / W * cols))
        r = min(rows - 1, int(s.y / H * rows))
        g = settlement_glyph(s)
        cur = grid[r][c]
        if _GLYPH_RANK.get(g, 0) >= _GLYPH_RANK.get(cur, -1):
            grid[r][c] = g

    return ["".join(row) for row in grid]


def _best_land_sites(world, n, spacing=90):
    """Pick a few high-quality, well-spaced land tiles to seed the first towns."""
    picks = []
    tries = 0
    while len(picks) < n and tries < 8000:
        tries += 1
        x = random.randint(2, world.width - 3)
        y = random.randint(2, world.height - 3)
        if not world.is_land(x, y):
            continue
        if world.biome_score(x, y) < 0.35:
            continue
        if any(abs(x - px) < spacing and abs(y - py) < spacing for px, py in picks):
            continue
        picks.append((x, y))
    return picks


def stats_line(world, civ):
    active = [s for s in civ.settlements if s.state != 'abandoned']
    pop = int(sum(s.pop for s in active))
    ruins = sum(1 for s in civ.settlements if s.state == 'abandoned')
    largest = max(active, key=lambda s: s.pop, default=None)
    lead = f"{largest.name} ({largest.size_label()}, {largest.ipop})" if largest else "none"
    return (f"  Year {world.year:>4} | pop {pop:>6} | towns {len(active):>2} "
            f"| ruins {ruins:>2} | largest: {lead}")


def run(years, every, cols, rows, seeds):
    print("=" * (cols + 2))
    print("  STRATUM CHRONICLE  -- generating a world...")
    print("=" * (cols + 2))

    def progress(msg):
        print(f"    {msg}", flush=True)

    world = WorldMap(seeds, on_progress=progress)
    geo = GeologyLayer()
    civ = CivLayer()

    # Seed a couple of founding settlements on good land so history starts early;
    # the simulation spawns the rest organically from there.
    for (x, y) in _best_land_sites(world, 2):
        civ.found(world, x, y, parent='dawn')

    print()
    print(stats_line(world, civ))
    for line in ascii_frame(world, civ, cols, rows):
        print("  " + line)

    founded = wars = droughts = 0
    peak_pop = 0
    peak_year = 0

    for _ in range(years * 4):
        world.step()
        if world.tick != 0:          # only cross year boundaries
            continue
        geo.step_year(world)
        for msg in civ.step_year(world):
            low = msg.lower()
            if 'found' in low or 'establish' in low or 'settlers' in low:
                founded += 1
            elif 'war' in low or 'sack' in low or 'conquer' in low or 'raid' in low or 'clash' in low:
                wars += 1
            elif 'drought' in low:
                droughts += 1
            print("   ", msg)

        pop = int(sum(s.pop for s in civ.settlements if s.state != 'abandoned'))
        if pop > peak_pop:
            peak_pop, peak_year = pop, world.year

        if world.year % every == 0:
            print()
            print(stats_line(world, civ))
            for line in ascii_frame(world, civ, cols, rows):
                print("  " + line)

    # Closing chronicle.
    active = sorted((s for s in civ.settlements if s.state != 'abandoned'),
                    key=lambda s: -s.pop)
    print()
    print("=" * (cols + 2))
    print(f"  After {years} years: {len(active)} settlements standing, "
          f"{founded} ever founded, {wars} wars, {droughts} droughts.")
    print(f"  Peak population: {peak_pop} in year {peak_year}.")
    if active:
        print("  Surviving powers:")
        for s in active[:8]:
            born = f"founded {s.founded_year}" if s.founded_year else "ancient"
            print(f"    {s.name:<14} {s.size_label():<10} pop {s.ipop:>5}  ({born})")
    else:
        print("  The world emptied -- no settlement outlived the centuries.")
    print("=" * (cols + 2))


def main():
    ap = argparse.ArgumentParser(description="Headless ASCII chronicle of a STRATUM world.")
    ap.add_argument("--years", type=int, default=400, help="years of history to simulate")
    ap.add_argument("--every", type=int, default=100, help="print a map every N years")
    ap.add_argument("--cols", type=int, default=100, help="ASCII map width")
    ap.add_argument("--rows", type=int, default=30, help="ASCII map height")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    random.seed(seed)
    np.random.seed(seed)
    run(args.years, args.every, args.cols, args.rows, seed)


if __name__ == "__main__":
    main()
