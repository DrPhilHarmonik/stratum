"""
WorldMap: holds base terrain + all mutable overlay layers.
Generated once per seed; geology and civ layers mutate it over time.
"""

import numpy as np

# ── World size ────────────────────────────────────────────────────
WORLD_W = 2400
WORLD_H = 800

# ── Elevation thresholds ──────────────────────────────────────────
SEA_DEEP    = 0.28
SEA_SHALLOW = 0.34
COAST       = 0.39
PLAINS      = 0.50
FOREST      = 0.62
HILLS       = 0.74
MOUNTAIN    = 0.84
SNOW        = 0.93

# ── Moisture thresholds ───────────────────────────────────────────
M_ARID     = 0.22
M_DRY      = 0.40
M_MODERATE = 0.60


def _bilinear(coarse, out_h, out_w):
    ch, cw = coarse.shape
    yf = np.linspace(0, ch - 1, out_h)
    xf = np.linspace(0, cw - 1, out_w)
    y0 = np.clip(np.floor(yf).astype(int), 0, ch - 2)
    x0 = np.clip(np.floor(xf).astype(int), 0, cw - 2)
    ty = (yf - y0)[:, None]
    tx = (xf - x0)[None, :]
    y1, x1 = y0 + 1, x0 + 1
    return (coarse[y0[:,None], x0[None,:]] * (1-ty) * (1-tx) +
            coarse[y0[:,None], x1[None,:]] * (1-ty) *    tx  +
            coarse[y1[:,None], x0[None,:]] *    ty  * (1-tx) +
            coarse[y1[:,None], x1[None,:]] *    ty  *    tx)


def _land_mask(h, w, rng):
    yi, xi = np.mgrid[:h, :w]
    yn = yi / h - 0.5
    xn = xi / w - 0.5

    for strength in (0.28, 0.14):
        warp_y = (_bilinear(rng.random((7, 7)), h, w) * 2 - 1) * strength
        warp_x = (_bilinear(rng.random((7, 7)), h, w) * 2 - 1) * strength
        yn = yn + warp_y
        xn = xn + warp_x

    style = rng.integers(0, 7)

    if style == 0:
        dist = np.sqrt((yn / 0.42)**2 + (xn / 0.42)**2)

    elif style == 1:
        angle  = rng.uniform(0, np.pi)
        ca, sa = np.cos(angle), np.sin(angle)
        xr     =  ca * xn + sa * yn
        yr     = -sa * xn + ca * yn
        aspect = rng.uniform(2.2, 4.0)
        dist = np.sqrt((yr / 0.35)**2 + (xr / (0.35 * aspect))**2)

    elif style == 2:
        n    = int(rng.integers(3, 7))
        dist = np.full((h, w), 2.0)
        for _ in range(n):
            cy = rng.uniform(-0.28, 0.28)
            cx = rng.uniform(-0.28, 0.28)
            ry = rng.uniform(0.09, 0.20)
            rx = ry * rng.uniform(0.6, 1.6)
            d  = np.sqrt(((yn - cy) / ry)**2 + ((xn - cx) / rx)**2)
            dist = np.minimum(dist, d)

    elif style == 3:
        r1  = rng.uniform(0.22, 0.32)
        r2  = rng.uniform(0.16, 0.26)
        off = rng.uniform(0.15, 0.28)
        ang = rng.uniform(0, np.pi)
        dy  = np.sin(ang) * off;  dx = np.cos(ang) * off
        d1  = np.sqrt(((yn - dy) / r1)**2 + ((xn - dx) / r1)**2)
        d2  = np.sqrt(((yn + dy) / r2)**2 + ((xn + dx) / r2)**2)
        dist = np.minimum(d1, d2)

    elif style == 4:
        outer  = np.sqrt((yn / 0.44)**2 + (xn / 0.44)**2)
        oy = rng.uniform(-0.12, 0.12);  ox = rng.uniform(-0.12, 0.12)
        inner  = np.sqrt(((yn - oy) / 0.30)**2 + ((xn - ox) / 0.30)**2)
        dist   = np.where(inner < 1.0, np.maximum(outer, 2.0 - inner * 2), outer)

    elif style == 5:
        edge_bias = xn + rng.uniform(-0.08, 0.08)
        dist = 1.0 - np.clip((edge_bias + 0.35) / 0.55, 0, 1)

    else:
        angle  = rng.uniform(0, np.pi)
        ca, sa = np.cos(angle), np.sin(angle)
        xr     =  ca * xn + sa * yn
        yr     = -sa * xn + ca * yn
        arm_sep = rng.uniform(0.14, 0.26)
        arm_len = rng.uniform(0.35, 0.46)
        arm_w   = rng.uniform(0.10, 0.17)
        d1  = np.sqrt(((yr - arm_sep) / arm_w)**2 + (xr / arm_len)**2)
        d2  = np.sqrt(((yr + arm_sep) / arm_w)**2 + (xr / arm_len)**2)
        dist = np.minimum(d1, d2)

    return np.clip(1.0 - dist, 0, 1) ** 1.3


def _generate_heightmap(h, w, rng):
    hmap = np.zeros((h, w))
    amp, total = 1.0, 0.0
    for scale in [3, 6, 12, 24, 48, 96]:
        gh = max(3, h // scale + 2)
        gw = max(3, w // scale + 2)
        hmap  += _bilinear(rng.random((gh, gw)), h, w) * amp
        total += amp
        amp   *= 0.52
    hmap /= total
    hmap *= _land_mask(h, w, rng)

    # Two-segment normalize: guarantee ~30-55% land coverage regardless of
    # world size.  Zero cells (land_mask==0) are always deep ocean.
    # The land/sea split is determined within the non-zero cells only.
    nz_mask = hmap > 1e-6          # cells touched by the land mask
    nz_frac = nz_mask.sum() / hmap.size

    land_frac = float(rng.uniform(0.30, 0.55))

    if nz_frac <= land_frac:
        # All non-zero cells become land; zero cells are ocean
        lo = float(hmap[nz_mask].min())
        hi = float(hmap[nz_mask].max())
        hmap[nz_mask] = COAST + (hmap[nz_mask] - lo) / max(hi - lo, 1e-6) * (1.0 - COAST)
        # zero cells stay 0 (= deep ocean)
    else:
        # Split non-zero cells: some inland sea, rest land
        land_within = land_frac / nz_frac          # fraction of nz cells that are land
        sea_within  = 1.0 - land_within
        nz_vals     = hmap[nz_mask]
        cutoff      = float(np.percentile(nz_vals, sea_within * 100))

        land_m    = nz_mask & (hmap >= cutoff)
        nz_sea_m  = nz_mask & (hmap <  cutoff)

        # Shallow ocean: remap [min_nz, cutoff) → [SEA_DEEP, COAST)
        if nz_sea_m.any():
            lo = float(hmap[nz_sea_m].min())
            hmap[nz_sea_m] = (SEA_DEEP +
                (hmap[nz_sea_m] - lo) / max(cutoff - lo, 1e-6) * (COAST - SEA_DEEP))

        # Land: remap [cutoff, max] → [COAST, 1.0]
        if land_m.any():
            hi = float(hmap[land_m].max())
            hmap[land_m] = COAST + (hmap[land_m] - cutoff) / max(hi - cutoff, 1e-6) * (1.0 - COAST)

        # Deep ocean (zero cells): remap 0 → [0, SEA_DEEP)
        deep_m = ~nz_mask
        if deep_m.any():
            # use original noise re-seeded for variety in deep ocean
            hmap[deep_m] = _bilinear(
                rng.random((8, 8)), h, w
            )[deep_m] * SEA_DEEP * 0.9

    # Sharpen peaks so mountains feel dramatic
    hi_mask = hmap > 0.70
    hmap[hi_mask] = 0.70 + (hmap[hi_mask] - 0.70) * 1.5
    return np.clip(hmap, 0.0, 1.0).astype(np.float32)


def _generate_moisture(hmap, rng):
    h, w     = hmap.shape
    sea_mask = hmap < SEA_SHALLOW

    coastal = np.where(sea_mask, 1.0, 0.0).astype(np.float32)
    for _ in range(45):
        pad     = np.pad(coastal, 1, mode='edge')
        nb      = (pad[:-2,1:-1] + pad[2:,1:-1] +
                   pad[1:-1,:-2] + pad[1:-1,2:]) / 4.0
        coastal = np.where(sea_mask, 1.0, nb * 0.97)

    moist = np.where(sea_mask, 1.0, 0.45 + coastal * 0.45).astype(np.float32)

    peak    = (hmap > MOUNTAIN).astype(np.float32)
    axis    = rng.integers(0, 2)
    reverse = bool(rng.random() > 0.5)
    shadow  = np.ones((h, w), dtype=np.float32)
    if axis == 0:
        cols    = (range(w - 1, -1, -1) if reverse else range(w))
        running = np.zeros(h, dtype=np.float32)
        for x in cols:
            running      = np.clip(running - 0.03, 0, None) + peak[:, x] * 0.20
            shadow[:, x] *= np.clip(1.0 - running * 0.30, 0.55, 1.0)
    else:
        rows    = (range(h - 1, -1, -1) if reverse else range(h))
        running = np.zeros(w, dtype=np.float32)
        for y in rows:
            running      = np.clip(running - 0.03, 0, None) + peak[y, :] * 0.20
            shadow[y, :] *= np.clip(1.0 - running * 0.30, 0.55, 1.0)
    moist *= shadow
    # Extra spatial noise to break up any residual banding
    moist += (_bilinear(rng.random((12, 12)), h, w) - 0.5) * 0.18
    return np.clip(moist, 0.0, 1.0)


def _generate_rivers(hmap, rng, max_steps=3000):
    """
    River tracing: greedy descent from highland source toward coast.

    Bilinear-noise terrain has ~30 % of land cells in closed depressions.
    Pure steepest-descent tracing gets stuck within a few steps.
    Priority-Flood pre-processing fixes this but takes ~9 s for a 2400x800
    world.

    Instead we use a greedy heuristic: at each step pick the neighbour that
    minimises  coast_dist + UPHILL_W * max(0, elev_gain).
    - Downhill steps: free -- the river follows the natural drainage.
    - Uphill steps: penalised by UPHILL_W per unit of elevation gained.
    Rivers therefore prefer downhill but take small uphill detours to escape
    local minima rather than getting permanently stuck.

    Sources are selected one-per-grid-zone from the top 25 % of land
    elevation so coverage spreads across the whole continent.
    coast_dist (distance to nearest sea cell) is computed once with
    scipy.ndimage.distance_transform_edt and reused for all rivers.
    """
    from scipy.ndimage import distance_transform_edt

    h, w     = hmap.shape
    land     = hmap >= COAST
    river    = np.zeros((h, w), dtype=bool)

    # Distance from every cell to the nearest sea cell (0 = sea, ≥1 = land)
    coast_dist = distance_transform_edt(land).astype(np.float32)

    # ── Source selection: highest land cell per grid zone ─────────
    elev_cut  = float(np.percentile(hmap[land], 75))   # top 25 %
    grid_rows, grid_cols = 9, 10                        # 90 zones
    cell_h    = max(1, h // grid_rows)
    cell_w    = max(1, w // grid_cols)

    sources = []
    for gr in range(grid_rows):
        for gc in range(grid_cols):
            y0 = gr * cell_h;  y1 = min(y0 + cell_h, h)
            x0 = gc * cell_w;  x1 = min(x0 + cell_w, w)
            sub   = hmap[y0:y1, x0:x1]
            sl    = land[y0:y1, x0:x1]
            hi    = sl & (sub >= elev_cut)
            if not hi.any():
                continue
            masked = np.where(hi, sub, -1.0)
            bi     = int(np.argmax(masked))
            by, bx = np.unravel_index(bi, sub.shape)
            sources.append((int(by + y0), int(bx + x0)))

    if not sources:
        return river

    dirs8     = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    UPHILL_W  = 800.0    # penalty per unit of uphill elevation gained

    for sy, sx in sources:
        y, x = sy, sx

        for _ in range(max_steps):
            if not (0 <= y < h and 0 <= x < w):
                break
            if hmap[y, x] < COAST:
                break            # stepped into sea

            river[y, x] = True

            if float(coast_dist[y, x]) < 1.5:
                break            # reached coast -- done

            # Greedy: pick the best land neighbour.
            # Prefer unvisited cells; if all options are already river, merge.
            # score = coast_dist + UPHILL_W * max(0, elevation_gain)
            cur_e        = float(hmap[y, x])
            best_score   = float('inf')
            best_y = best_x = -1
            merge_score  = float('inf')
            merge_y = merge_x = -1

            for dy, dx in dirs8:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and land[ny, nx]:
                    gain  = float(hmap[ny, nx]) - cur_e
                    score = float(coast_dist[ny, nx]) + UPHILL_W * max(0.0, gain)
                    if river[ny, nx]:
                        if score < merge_score:
                            merge_score = score
                            merge_y, merge_x = ny, nx
                    else:
                        if score < best_score:
                            best_score = score
                            best_y, best_x = ny, nx

            if best_y != -1:
                # Normal step into new territory
                y, x = best_y, best_x
            elif merge_y != -1:
                # All free paths exhausted -- step into existing river to merge
                river[merge_y, merge_x] = True   # ensure 4-adjacency where possible
                break
            else:
                break            # completely surrounded by sea

    return river


# ── Terrain overlays ──────────────────────────────────────────────
# These are applied on top of base elevation/moisture when rendering.

OVERLAY_NONE     = 0
OVERLAY_ROAD     = 1
OVERLAY_FARM     = 2
OVERLAY_RUINS    = 3
OVERLAY_BURN     = 4
OVERLAY_LAVA     = 5   # recent volcanic deposit
OVERLAY_BRIDGE   = 6   # road crossing a river


class WorldMap:
    """
    Holds generated terrain + mutable overlay layers modified by simulation.
    """

    def __init__(self, seed: int, on_progress=None):
        def _prog(msg):
            if on_progress:
                on_progress(msg)

        self.seed  = seed
        rng        = np.random.default_rng(seed)
        h, w       = WORLD_H, WORLD_W

        _prog('heightmap...')
        self.elev      = _generate_heightmap(h, w, rng).astype(np.float32)
        self.base_elev = self.elev.copy()

        _prog('moisture & climate...')
        self.moisture   = _generate_moisture(self.elev, rng).astype(np.float32)
        self.base_moist = self.moisture.copy()

        _prog('rivers...')
        self.rivers = _generate_rivers(self.elev, rng)

        # Soil fertility 0-1; depletes near settlements, recovers slowly
        self.soil    = np.clip(self.moisture * 0.8 + 0.2, 0, 1).astype(np.float32)

        # Per-cell overlay (uint8, see OVERLAY_* constants)
        self.overlay = np.zeros((h, w), dtype=np.uint8)

        self.year = 0
        self.tick = 0   # ticks within current year (4 ticks = 1 year)

    @property
    def height(self): return self.elev.shape[0]

    @property
    def width(self):  return self.elev.shape[1]

    def is_land(self, x, y):
        return (0 <= x < self.width and 0 <= y < self.height
                and self.elev[y, x] >= COAST)

    def is_sea(self, x, y):
        return (0 <= x < self.width and 0 <= y < self.height
                and self.elev[y, x] < SEA_SHALLOW)

    def biome_score(self, x, y):
        """0-1 habitability score for settlement placement."""
        if not self.is_land(x, y):
            return 0.0
        e = float(self.elev[y, x])
        if e >= MOUNTAIN:
            return 0.0
        m = float(self.moisture[y, x])
        s = float(self.soil[y, x])
        # Prefer plains/coast, penalise extremes
        elev_score  = 1.0 - abs(e - 0.50) / 0.35
        river_bonus = 0.3 if self.rivers[y, x] else 0.0
        coast_bonus = 0.2 if e < PLAINS else 0.0
        return float(np.clip(elev_score * (m + s) / 2 + river_bonus + coast_bonus, 0, 1))

    def step(self):
        """Advance world clock one tick (4 ticks = 1 year)."""
        self.tick += 1
        if self.tick >= 4:
            self.tick = 0
            self.year += 1
        # Slow soil recovery
        land = self.elev >= COAST
        self.soil[land] = np.minimum(1.0, self.soil[land] + 0.0004)
