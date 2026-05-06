#!/usr/bin/env python3
"""
STRATUM -- terrain render proof-of-concept
Run: python3 poc.py

Navigation
  Arrow keys / WASD  pan
  z / x              zoom in / out
  r                  regenerate world
  q                  quit
"""

import curses
import numpy as np

# ── World size ────────────────────────────────────────────────────
WORLD_W = 400
WORLD_H = 160

# ── Zoom levels ───────────────────────────────────────────────────
ZOOM_LEVELS   = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0]
DEFAULT_ZOOM  = 3
PAN_CELLS     = 6

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
M_ARID      = 0.22
M_DRY       = 0.40
M_MODERATE  = 0.60

# ── Color pair IDs ────────────────────────────────────────────────
C_ABYSS   = 1
C_SEA     = 2
C_SHOAL   = 3
C_COAST   = 4
C_DESERT  = 5
C_SAVANNA = 6
C_PLAINS  = 7
C_FOREST  = 8
C_HILLS   = 9
C_MOUNT   = 10
C_SNOW    = 11
C_RIVER   = 12
C_STATUS  = 13
C_OOB     = 14

# ── Braille density glyphs ────────────────────────────────────────
_B = {
    'empty':   '\u2800',
    'sparse':  '\u2802',
    'ripple':  '\u2812',
    'scatter': '\u2826',
    'medium':  '\u2836',
    'dense':   '\u283f',
    'heavy':   '\u28f6',
    'thick':   '\u28fe',
    'solid':   '\u28ff',
}


# ── Biome glyph selection ─────────────────────────────────────────

def terrain_glyph(elev, moist=0.5, river=False):
    """Return (char, colour_id, bold) for elevation + moisture."""

    if river and elev >= COAST:
        return _B['ripple'], C_RIVER, True

    # Water
    if elev < SEA_DEEP:
        ch = _B['empty'] if elev / SEA_DEEP < 0.45 else _B['sparse']
        return ch, C_ABYSS, False
    if elev < SEA_SHALLOW:
        return _B['ripple'], C_SEA, False
    if elev < COAST:
        return _B['scatter'], C_SHOAL, True

    # Low land
    if elev < PLAINS:
        if moist < M_ARID:
            return _B['scatter'], C_DESERT, True
        t = (elev - COAST) / (PLAINS - COAST)
        ch = _B['ripple'] if t < 0.4 else _B['medium']
        return ch, C_COAST, t > 0.5

    # Plains / savanna / desert
    if elev < FOREST:
        if moist < M_ARID:
            return _B['scatter'], C_DESERT, False
        if moist < M_DRY:
            t = (elev - PLAINS) / (FOREST - PLAINS)
            ch = _B['medium'] if t < 0.5 else _B['dense']
            return ch, C_SAVANNA, False
        t = (elev - PLAINS) / (FOREST - PLAINS)
        ch = _B['medium'] if t < 0.55 else _B['dense']
        return ch, C_PLAINS, False

    # Forest / arid hills
    if elev < HILLS:
        if moist < M_DRY:
            return _B['medium'], C_SAVANNA, False
        t = (elev - FOREST) / (HILLS - FOREST)
        ch = _B['dense'] if t < 0.5 else _B['thick']
        return ch, C_FOREST, False

    # Hills / upland
    if elev < MOUNTAIN:
        t  = (elev - HILLS) / (MOUNTAIN - HILLS)
        ch = _B['heavy'] if t < 0.5 else _B['thick']
        return ch, C_HILLS, t > 0.65

    # Mountain rock / snow peak
    if elev < SNOW:
        return _B['solid'], C_MOUNT, False
    return _B['solid'], C_SNOW, True


# ── Noise helpers ─────────────────────────────────────────────────

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


# ── Land mask ─────────────────────────────────────────────────────

def _land_mask(h, w, rng):
    yi, xi = np.mgrid[:h, :w]
    yn = yi / h - 0.5
    xn = xi / w - 0.5

    # Two passes of domain warp for organic coastlines
    for strength in (0.28, 0.14):
        warp_y = (_bilinear(rng.random((7, 7)), h, w) * 2 - 1) * strength
        warp_x = (_bilinear(rng.random((7, 7)), h, w) * 2 - 1) * strength
        yn = yn + warp_y
        xn = xn + warp_x

    style = rng.integers(0, 7)

    if style == 0:
        # Round-ish island
        dist = np.sqrt((yn / 0.42)**2 + (xn / 0.42)**2)

    elif style == 1:
        # Elongated continent / peninsula
        angle  = rng.uniform(0, np.pi)
        ca, sa = np.cos(angle), np.sin(angle)
        xr     =  ca * xn + sa * yn
        yr     = -sa * xn + ca * yn
        aspect = rng.uniform(2.2, 4.0)
        dist = np.sqrt((yr / 0.35)**2 + (xr / (0.35 * aspect))**2)

    elif style == 2:
        # Archipelago
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
        # Twin landmasses
        r1  = rng.uniform(0.22, 0.32)
        r2  = rng.uniform(0.16, 0.26)
        off = rng.uniform(0.15, 0.28)
        ang = rng.uniform(0, np.pi)
        dy  = np.sin(ang) * off;  dx = np.cos(ang) * off
        d1  = np.sqrt(((yn - dy) / r1)**2 + ((xn - dx) / r1)**2)
        d2  = np.sqrt(((yn + dy) / r2)**2 + ((xn + dx) / r2)**2)
        dist = np.minimum(d1, d2)

    elif style == 4:
        # Crescent via subtraction
        outer  = np.sqrt((yn / 0.44)**2 + (xn / 0.44)**2)
        oy = rng.uniform(-0.12, 0.12);  ox = rng.uniform(-0.12, 0.12)
        inner  = np.sqrt(((yn - oy) / 0.30)**2 + ((xn - ox) / 0.30)**2)
        dist   = np.where(inner < 1.0, np.maximum(outer, 2.0 - inner * 2), outer)

    elif style == 5:
        # Ragged coast flooding from one side
        edge_bias = xn + rng.uniform(-0.08, 0.08)
        dist = 1.0 - np.clip((edge_bias + 0.35) / 0.55, 0, 1)

    else:
        # Gulf: two arms of land enclosing an inland sea
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


# ── Heightmap ─────────────────────────────────────────────────────

def generate_heightmap(h, w, seed=42):
    rng  = np.random.default_rng(seed)
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

    # Sharpen peaks: push high terrain higher for more dramatic mountains
    hi_mask = hmap > 0.55
    hmap[hi_mask] = 0.55 + (hmap[hi_mask] - 0.55) * 1.6
    np.clip(hmap, 0, 1, out=hmap)

    lo, hi = hmap.min(), hmap.max()
    return (hmap - lo) / (hi - lo)


# ── Moisture map ──────────────────────────────────────────────────

def generate_moisture(hmap, rng):
    h, w     = hmap.shape
    sea_mask = hmap < SEA_SHALLOW

    # Coastal proximity: flood from sea with gentle decay so it reaches inland
    coastal = np.where(sea_mask, 1.0, 0.0).astype(np.float32)
    for _ in range(45):
        pad     = np.pad(coastal, 1, mode='edge')
        nb      = (pad[:-2,1:-1] + pad[2:,1:-1] +
                   pad[1:-1,:-2] + pad[1:-1,2:]) / 4.0
        coastal = np.where(sea_mask, 1.0, nb * 0.97)

    # Blend: temperate baseline (0.45) + coastal bonus (up to +0.45)
    # Sea cells stay at 1.0; deep interior stays around 0.45
    moist = np.where(sea_mask, 1.0, 0.45 + coastal * 0.45).astype(np.float32)

    # Rain shadow: prevailing wind blocks moisture behind mountain ranges
    peak    = (hmap > MOUNTAIN).astype(np.float32)
    axis    = rng.integers(0, 2)   # 0 = east-west winds, 1 = north-south
    reverse = bool(rng.random() > 0.5)

    shadow = np.ones((h, w), dtype=np.float32)
    if axis == 0:
        cols    = (range(w - 1, -1, -1) if reverse else range(w))
        running = np.zeros(h, dtype=np.float32)
        for x in cols:
            running    = np.clip(running - 0.03, 0, None) + peak[:, x] * 0.45
            shadow[:, x] *= np.clip(1.0 - running * 0.65, 0.20, 1.0)
    else:
        rows    = (range(h - 1, -1, -1) if reverse else range(h))
        running = np.zeros(w, dtype=np.float32)
        for y in rows:
            running    = np.clip(running - 0.03, 0, None) + peak[y, :] * 0.45
            shadow[y, :] *= np.clip(1.0 - running * 0.65, 0.20, 1.0)

    moist *= shadow

    # Local variation
    moist += (_bilinear(rng.random((8, 8)), h, w) - 0.5) * 0.15
    return np.clip(moist, 0.0, 1.0)


# ── Rivers ────────────────────────────────────────────────────────

def generate_rivers(hmap, n=12, seed=99):
    h, w   = hmap.shape
    rng    = np.random.default_rng(seed)
    rivers = np.zeros((h, w), dtype=bool)
    dirs8  = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]

    peaks = np.argwhere(hmap > MOUNTAIN)
    if len(peaks) == 0:
        peaks = np.argwhere(hmap > HILLS)
    if len(peaks) == 0:
        return rivers

    chosen = peaks[rng.choice(len(peaks), min(n, len(peaks)), replace=False)]
    for sy, sx in chosen:
        y, x = int(sy), int(sx)
        seen = set()
        for _ in range(1000):
            if (y, x) in seen:
                break
            seen.add((y, x))
            rivers[y, x] = True
            if hmap[y, x] < SEA_SHALLOW:
                break
            best = hmap[y, x]
            dy_b = dx_b = 0
            for dy, dx in rng.permutation(dirs8):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    nh = float(hmap[ny, nx]) - rng.random() * 0.005
                    if nh < best:
                        best = nh; dy_b = dy; dx_b = dx
            if dy_b == 0 and dx_b == 0:
                break
            y += dy_b; x += dx_b
    return rivers


# ── Camera ────────────────────────────────────────────────────────

class Camera:
    def __init__(self, world_w, world_h):
        self.wx  = world_w / 2.0
        self.wy  = world_h / 2.0
        self._zi = DEFAULT_ZOOM

    @property
    def zoom(self): return ZOOM_LEVELS[self._zi]

    def zoom_in(self):  self._zi = min(len(ZOOM_LEVELS)-1, self._zi+1)
    def zoom_out(self): self._zi = max(0, self._zi-1)

    def pan(self, dx, dy):
        self.wx += dx / self.zoom
        self.wy += dy / self.zoom

    def clamp(self, ww, wh):
        self.wx = float(np.clip(self.wx, 0, ww-1))
        self.wy = float(np.clip(self.wy, 0, wh-1))

    def screen_to_world(self, sx, sy, sw, sh):
        return (self.wx + (sx - sw/2) / self.zoom,
                self.wy + (sy - sh/2) / self.zoom)

    def zoom_label(self):
        z = self.zoom
        return f'{int(z)}x' if z >= 1 else f'1/{int(1/z)}x'


# ── Colours ───────────────────────────────────────────────────────

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    for pid, fg in [
        (C_ABYSS,   curses.COLOR_BLUE),
        (C_SEA,     curses.COLOR_BLUE),
        (C_SHOAL,   curses.COLOR_CYAN),
        (C_COAST,   curses.COLOR_YELLOW),
        (C_DESERT,  curses.COLOR_YELLOW),
        (C_SAVANNA, curses.COLOR_YELLOW),
        (C_PLAINS,  curses.COLOR_GREEN),
        (C_FOREST,  curses.COLOR_GREEN),
        (C_HILLS,   curses.COLOR_YELLOW),
        (C_MOUNT,   curses.COLOR_WHITE),
        (C_SNOW,    curses.COLOR_WHITE),
        (C_RIVER,   curses.COLOR_CYAN),
        (C_STATUS,  curses.COLOR_CYAN),
        (C_OOB,     curses.COLOR_BLACK),
    ]:
        curses.init_pair(pid, fg, -1)


# ── Drawing ───────────────────────────────────────────────────────

_DIM_PAIRS  = {C_ABYSS, C_FOREST, C_SAVANNA}
_BOLD_NEVER = {C_SAVANNA, C_PLAINS, C_FOREST}

def _cell_attr(pair, bold):
    attr = curses.color_pair(pair)
    if pair in _DIM_PAIRS:
        attr |= curses.A_DIM
    elif bold:
        attr |= curses.A_BOLD
    return attr


def draw(stdscr, hmap, moist, rivers, cam, seed):
    rows, cols = stdscr.getmaxyx()
    sh, sw     = rows - 1, cols
    wh, ww     = hmap.shape
    stdscr.erase()

    cell_size = max(1.0, 1.0 / cam.zoom)

    for sy in range(sh):
        wy0 = cam.screen_to_world(0, sy, sw, sh)[1]
        iy0 = int(wy0)
        iy1 = max(iy0 + 1, int(wy0 + cell_size))

        for sx in range(sw):
            wx0 = cam.screen_to_world(sx, 0, sw, sh)[0]
            ix0 = int(wx0)
            ix1 = max(ix0 + 1, int(wx0 + cell_size))

            if ix0 >= ww or iy0 >= wh or ix1 <= 0 or iy1 <= 0:
                try:
                    stdscr.addstr(sy, sx, ' ', curses.color_pair(C_OOB))
                except curses.error:
                    pass
                continue

            ix0c = max(0, ix0);  ix1c = min(ww, ix1)
            iy0c = max(0, iy0);  iy1c = min(wh, iy1)

            ev = float(hmap [iy0c:iy1c, ix0c:ix1c].mean())
            mv = float(moist[iy0c:iy1c, ix0c:ix1c].mean())
            rv = bool(rivers[iy0c:iy1c, ix0c:ix1c].any())

            ch, pair, bold = terrain_glyph(ev, mv, rv)
            try:
                stdscr.addstr(sy, sx, ch, _cell_attr(pair, bold))
            except curses.error:
                pass

    bar = (f"  STRATUM  |  seed {seed:5d}  |  "
           f"pos {int(cam.wx):>4d},{int(cam.wy):>3d}  |  zoom {cam.zoom_label():>5s}  |  "
           f"[arrows/wasd] pan   [z/x] zoom   [r] regen   [q] quit")
    try:
        stdscr.addstr(rows-1, 0, bar[:cols-1],
                      curses.color_pair(C_STATUS) | curses.A_BOLD)
    except curses.error:
        pass

    stdscr.refresh()


# ── Main ──────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    init_colors()

    seed = 42
    rng  = np.random.default_rng(seed)
    hmap = generate_heightmap(WORLD_H, WORLD_W, seed)
    moist = generate_moisture(hmap, rng)
    rivs  = generate_rivers(hmap, seed=seed)
    cam   = Camera(WORLD_W, WORLD_H)
    draw(stdscr, hmap, moist, rivs, cam, seed)

    while True:
        key = stdscr.getch()

        if key in (ord('q'), ord('Q')):
            break
        elif key in (ord('r'), ord('R')):
            seed  = int(np.random.randint(1, 99999))
            rng   = np.random.default_rng(seed)
            hmap  = generate_heightmap(WORLD_H, WORLD_W, seed)
            moist = generate_moisture(hmap, rng)
            rivs  = generate_rivers(hmap, seed=seed)
            cam   = Camera(WORLD_W, WORLD_H)
        elif key in (ord('z'), ord('Z'), ord('+')):
            cam.zoom_in()
        elif key in (ord('x'), ord('X'), ord('-')):
            cam.zoom_out()
        elif key in (curses.KEY_UP,    ord('w'), ord('W')):
            cam.pan(0, -PAN_CELLS)
        elif key in (curses.KEY_DOWN,  ord('s'), ord('S')):
            cam.pan(0,  PAN_CELLS)
        elif key in (curses.KEY_LEFT,  ord('a'), ord('A')):
            cam.pan(-PAN_CELLS, 0)
        elif key in (curses.KEY_RIGHT, ord('d'), ord('D')):
            cam.pan( PAN_CELLS, 0)
        elif key == curses.KEY_RESIZE:
            stdscr.clear()

        cam.clamp(WORLD_W, WORLD_H)
        draw(stdscr, hmap, moist, rivs, cam, seed)


if __name__ == '__main__':
    curses.wrapper(main)
